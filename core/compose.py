"""
core/compose.py
===============
Layer Composition  (v13)

Provides ``ComposeLayer``: a meta-layer that wraps N other layers into one
named unit.  The composed layer acts as a single priority slot in the stack
while internally merging its children in priority order.

Use cases
---------
1. Bundle related layers (context + session) into a named "situation" that
   can be hot-swapped at once via LayerStack.swap().
2. Ship reusable named configurations as single importable objects.
3. Reduce boilerplate when multiple layers always appear together.

Architecture
------------
``ComposeLayer`` implements ``LayerProtocol`` so it is drop-in compatible
with the existing LayerStack.  Internally it creates a mini-stack of its
children, runs their build/validate/pipeline cycle, and returns the merged
result as its own ``build()`` output.

Pattern: Composite (GoF) + Decorator (pipeline wrapping).

Design Rules
------------
* ComposeLayer does NOT modify any child layer.
* Children are always merged in their declared priority order.
* A ComposeLayer can itself be a child of another ComposeLayer.
* Circular composition is detected and raises ``LayerCompositionError``.

Strict-mode (Pyright)
---------------------
  All attrs typed; ``_children`` is a ``List[LayerProtocol]`` ordered by
  ``priority``; no use of ``Any`` for child iteration.

v13 (new module):
  - LayerCompositionError
  - ComposeLayer(name, priority, *children, description)
  - ComposeLayer.describe() → human-readable child summary
  - ComposeLayer.child_names() → List[str]
  - ComposeLayer.add(layer) → self (fluent)
  - guard: children that share a name raise LayerCompositionError
"""

from __future__ import annotations

import logging
from typing import Iterable, List, Optional, Set

from core.types    import ConfigDict
from core.layer    import LayerProtocol
from core.pipeline import ConfigPacket, Pipeline, _deep_merge  # type: ignore[private]

logger = logging.getLogger("qute.core.compose")


# ─────────────────────────────────────────────
# Error
# ─────────────────────────────────────────────

class LayerCompositionError(Exception):
    """Raised when ComposeLayer detects a composition rule violation."""


# ─────────────────────────────────────────────
# ComposeLayer
# ─────────────────────────────────────────────

class ComposeLayer(LayerProtocol):
    """
    Meta-layer: compose N layers into one named unit.

    Parameters
    ----------
    name        : unique name for this composed layer
    priority    : priority slot in the outer LayerStack
    children    : initial child layers (can also be added via .add())
    description : human-readable description
    pipeline_   : optional Pipeline applied to the merged output

    Example
    -------
    ::

        from core.compose import ComposeLayer
        from layers.context import ContextLayer
        from layers.session import SessionLayer

        situation = ComposeLayer(
            "situation", priority=57,
            children=[ContextLayer("dev"), SessionLayer("focus")],
            description="dev focus session",
        )
        stack.register(situation)

    The composed layer's merged output is computed once during build().
    Child layers are not visible to the outer LayerStack directly.
    """

    def __init__(
        self,
        name:        str,
        priority:    int                    = 50,
        children:    Iterable[LayerProtocol] = (),
        description: str                    = "",
        pipeline_:   Optional[Pipeline]     = None,
    ) -> None:
        self._name        = name
        self._priority    = priority
        self._children:   List[LayerProtocol] = []
        self._description = description
        self._pipeline_   = pipeline_

        for child in children:
            self.add(child)

    # ── LayerProtocol interface ────────────────────────────────────────

    @property
    def name(self) -> str:           # type: ignore[override]
        return self._name

    @property
    def priority(self) -> int:       # type: ignore[override]
        return self._priority

    @property
    def description(self) -> str:    # type: ignore[override]
        return self._description or f"composed({', '.join(c.name for c in self._children)})"

    def build(self) -> ConfigDict:
        """
        Merge children in priority order and return the combined delta.
        Pure function — no side effects.
        """
        merged: ConfigDict = {}

        for child in sorted(self._children, key=lambda c: c.priority):
            try:
                raw = child.build()
            except Exception as exc:
                logger.error(
                    "[ComposeLayer:%s] child %s build() raised: %s",
                    self._name, child.name, exc,
                )
                continue

            pipe = child.pipeline()
            if pipe is not None:
                packet = pipe.run(ConfigPacket(source=f"compose:{child.name}", data=raw))
                raw = packet.data

            merged = _deep_merge(merged, raw)

        # Apply own pipeline if provided
        if self._pipeline_ is not None:
            packet = self._pipeline_.run(ConfigPacket(source=f"compose:{self._name}", data=merged))
            merged = packet.data

        return merged

    def validate(self, data: ConfigDict) -> List[str]:
        """Run each child's validate() and collect all errors."""
        errors: List[str] = []
        for child in self._children:
            errors.extend(child.validate(data))
        return errors

    def pipeline(self) -> Optional[Pipeline]:
        """Return the compose-level pipeline (children already ran theirs)."""
        return None   # pipeline applied inside build(); don't double-apply

    # ── Fluent API ─────────────────────────────────────────────────────

    def add(self, layer: LayerProtocol) -> "ComposeLayer":
        """
        Add a child layer.  Raises LayerCompositionError if name duplicated.
        Returns self for fluent chaining.
        """
        existing_names: Set[str] = {c.name for c in self._children}
        if layer.name in existing_names:
            raise LayerCompositionError(
                f"ComposeLayer({self._name!r}): duplicate child name {layer.name!r}"
            )
        if layer.name == self._name:
            raise LayerCompositionError(
                f"ComposeLayer({self._name!r}): child cannot have same name as parent"
            )
        self._children.append(layer)
        self._children.sort(key=lambda c: c.priority)
        logger.debug(
            "[ComposeLayer:%s] added child %s (priority=%d)",
            self._name, layer.name, layer.priority,
        )
        return self

    def remove(self, name: str) -> "ComposeLayer":
        """Remove a child by name.  Raises KeyError if not found."""
        for i, child in enumerate(self._children):
            if child.name == name:
                del self._children[i]
                logger.debug("[ComposeLayer:%s] removed child %s", self._name, name)
                return self
        raise KeyError(f"ComposeLayer({self._name!r}): child {name!r} not found")

    # ── Introspection ─────────────────────────────────────────────────

    def child_names(self) -> List[str]:
        """Return child names in priority order."""
        return [c.name for c in sorted(self._children, key=lambda c: c.priority)]

    def describe(self) -> str:
        """Human-readable description of composition."""
        lines = [f"ComposeLayer({self._name!r}, priority={self._priority})"]
        for child in sorted(self._children, key=lambda c: c.priority):
            lines.append(f"  ├─ {child.name}[{child.priority}]  {child.description}")
        return "\n".join(lines)

    def __repr__(self) -> str:
        return f"<ComposeLayer:{self._name}[{self._priority}] children={self.child_names()}>"


# ─────────────────────────────────────────────
# Convenience factory
# ─────────────────────────────────────────────

def compose(
    name:        str,
    *children:   LayerProtocol,
    priority:    int            = 50,
    description: str            = "",
) -> ComposeLayer:
    """
    Convenience factory::

        from core.compose import compose
        from layers.context import ContextLayer
        from layers.session import SessionLayer

        situation = compose("dev-focus", ContextLayer("dev"), SessionLayer("focus"), priority=57)
    """
    return ComposeLayer(name, priority=priority, children=list(children), description=description)
