"""
core/hot_swap.py
================
Layer Hot-Swap Engine  (v13)

Provides ``LayerHotSwap``: an orchestration helper that replaces a live
layer in a ``LayerStack`` and re-applies only the changed keys without
restarting qutebrowser.

Problem (v12 and earlier)
--------------------------
The ``ConfigOrchestrator.reload()`` method rebuilds the *entire* layer stack
and diff-applies changed settings.  This works, but has two limitations:

  1. All layers rebuild — even unchanged ones.
  2. Context/session switching always triggers a full :config-source
     (which reloads the entire config.py), because there is no way to
     surgically replace one layer and apply only its delta.

Solution (v13)
--------------
``LayerHotSwap`` wraps a ``LayerStack`` and ``ConfigApplier`` and exposes::

    hot_swap.swap(name, new_layer)   → List[str]   (errors)
    hot_swap.remove(name)            → List[str]
    hot_swap.insert(new_layer)       → List[str]

Each operation:
  1. Records a snapshot of the current merged config.
  2. Performs the structural change on the stack.
  3. Re-resolves the stack.
  4. Diffs the new merged config against the snapshot.
  5. Applies ONLY the changed keys via ``ConfigApplier``.
  6. Emits a ``LayerSwappedEvent`` via the ``MessageRouter``.

Integration
-----------
``ConfigOrchestrator`` gains a ``hot_swap`` property (v13) that returns a
lazily-constructed ``LayerHotSwap``.  Context/session switching will use
this instead of the full :config-source cycle.

Patterns
--------
  Command (each swap is a reversible command)
  Memento (snapshot before swap for diff)
  Strategy (apply_fn injected, not hard-coded)

Strict-mode (Pyright)
---------------------
  All return types annotated; ``ConfigApplier`` referenced via forward
  string type to avoid circular import (``orchestrator.py`` also imports
  ``hot_swap.py``).

v13 (new module):
  - LayerSwappedEvent (new protocol event)
  - HotSwapResult dataclass
  - LayerHotSwap class
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from typing import Any, Callable, List, Optional, TYPE_CHECKING

from core.types     import ConfigDict
from core.layer     import LayerProtocol, LayerStack
from core.incremental import ConfigDiffer, ConfigSnapshot

if TYPE_CHECKING:
    from core.protocol import MessageRouter

logger = logging.getLogger("qute.hot_swap")


# ─────────────────────────────────────────────
# Result type
# ─────────────────────────────────────────────

@dataclass(frozen=True)
class HotSwapResult:
    """
    Result of a hot-swap operation.

    Fields
    ------
    operation : "swap" | "remove" | "insert"
    layer_name: name of the affected layer
    changes   : number of keys changed in the diff
    errors    : list of apply errors (empty = success)
    duration_ms: wall-clock time of the operation
    """
    operation:   str
    layer_name:  str
    changes:     int
    errors:      List[str]
    duration_ms: float

    @property
    def ok(self) -> bool:
        return len(self.errors) == 0

    def __str__(self) -> str:
        status = "OK" if self.ok else f"ERRORS({len(self.errors)})"
        return (
            f"HotSwap[{self.operation}:{self.layer_name}] "
            f"changes={self.changes} {status} {self.duration_ms:.1f}ms"
        )


# ─────────────────────────────────────────────
# ApplyFn type alias
# ─────────────────────────────────────────────

ApplyFn = Callable[[str, Any], List[str]]
"""
Signature: (key: str, value: Any) → List[str] (errors)

Injected from ConfigApplier.apply_settings.
"""


# ─────────────────────────────────────────────
# LayerHotSwap
# ─────────────────────────────────────────────

class LayerHotSwap:
    """
    Surgical layer replacement that applies only changed keys.

    Parameters
    ----------
    stack     : the live LayerStack to mutate
    apply_fn  : called for each changed/added key; returns error list
    router    : optional MessageRouter to emit LayerSwappedEvent
    """

    def __init__(
        self,
        stack:    LayerStack,
        apply_fn: ApplyFn,
        router:   Optional["MessageRouter"] = None,
    ) -> None:
        self._stack    = stack
        self._apply_fn = apply_fn
        self._router   = router

    # ── Public API ─────────────────────────────────────────────────────

    def swap(
        self,
        name:      str,
        new_layer: LayerProtocol,
    ) -> HotSwapResult:
        """
        Replace the layer named *name* with *new_layer*.

        If *name* is not found in the stack, behaves as ``insert``.
        """
        return self._execute("swap", name, new_layer=new_layer)

    def remove(self, name: str) -> HotSwapResult:
        """Disable the layer named *name* and re-apply the diff."""
        return self._execute("remove", name)

    def insert(self, new_layer: LayerProtocol) -> HotSwapResult:
        """Insert *new_layer* and apply the diff."""
        return self._execute("insert", new_layer.name, new_layer=new_layer)

    # ── Internal ───────────────────────────────────────────────────────

    def _execute(
        self,
        operation: str,
        name:      str,
        new_layer: Optional[LayerProtocol] = None,
    ) -> HotSwapResult:
        t0 = time.perf_counter()
        errors: List[str] = []

        # 1. Snapshot BEFORE
        before: ConfigDict = {}
        try:
            before = dict(self._stack.merged.get("settings", {}))
        except RuntimeError:
            pass  # stack not yet resolved; diff will see all as additions

        # 2. Apply structural change to stack
        try:
            if operation == "swap":
                self._do_swap(name, new_layer)
            elif operation == "remove":
                self._do_remove(name)
            elif operation == "insert":
                if new_layer is None:
                    raise ValueError("insert requires new_layer")
                self._stack.register(new_layer)
        except Exception as exc:
            logger.error("[HotSwap] %s(%s) structural change failed: %s", operation, name, exc)
            errors.append(str(exc))
            return HotSwapResult(
                operation=operation, layer_name=name,
                changes=0, errors=errors,
                duration_ms=(time.perf_counter() - t0) * 1000,
            )

        # 3. Re-resolve stack
        try:
            self._stack.resolve()
        except Exception as exc:
            logger.error("[HotSwap] re-resolve failed: %s", exc)
            errors.append(f"re-resolve: {exc}")

        # 4. Snapshot AFTER
        after: ConfigDict = {}
        try:
            after = dict(self._stack.merged.get("settings", {}))
        except RuntimeError:
            pass

        # 5. Diff
        changes = ConfigDiffer.diff(
            ConfigSnapshot(data=before, label="before"),
            ConfigSnapshot(data=after,  label="after"),
        )
        changed_keys = [c for c in changes if c.kind.name in ("CHANGED", "ADDED")]

        # 6. Apply delta
        for change in changed_keys:
            errs = self._apply_fn(change.key, change.new_value)
            errors.extend(errs)

        n_changes = len(changed_keys)
        duration_ms = (time.perf_counter() - t0) * 1000

        logger.info(
            "[HotSwap] %s(%s): %d change(s) applied, %d error(s)  %.1fms",
            operation, name, n_changes, len(errors), duration_ms,
        )

        # 7. Emit event
        if self._router is not None:
            try:
                from core.hot_swap_events import LayerSwappedEvent
                self._router.emit(LayerSwappedEvent(
                    operation=operation,
                    layer_name=name,
                    changes=n_changes,
                    errors=len(errors),
                ))
            except Exception:
                pass

        return HotSwapResult(
            operation=operation,
            layer_name=name,
            changes=n_changes,
            errors=errors,
            duration_ms=duration_ms,
        )

    def _do_swap(self, name: str, new_layer: Optional[LayerProtocol]) -> None:
        """Replace existing layer or insert if not found."""
        if new_layer is None:
            raise ValueError("swap requires new_layer")
        # Try to find and replace in-place
        for record in self._stack._layers: # type: ignore[private]
            if record.layer.name == name:
                record.layer = new_layer   # type: ignore[misc]
                self._stack._layers.sort(key=lambda r: r.layer.priority)  # type: ignore[protect]
                logger.debug("[HotSwap] swapped layer %s", name)
                return
        # Not found: insert
        logger.debug("[HotSwap] layer %s not found, inserting", name)
        self._stack.register(new_layer)

    def _do_remove(self, name: str) -> None:
        """Disable a layer by name."""
        try:
            self._stack.disable(name)
        except KeyError:
            raise KeyError(f"hot_swap.remove: layer {name!r} not found in stack")
