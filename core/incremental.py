"""
core/incremental.py
===================
Incremental Configuration Engine  (v9.1)

Concept:
  Instead of full re-apply on every change, compute a delta (diff)
  between old and new config and apply only changed keys.

Architecture:
  ConfigSnapshot → ConfigDiffer → [ConfigChange] → IncrementalApplier → qutebrowser

Benefits:
  - Fast hot-reload (only changed keys re-applied)
  - Audit trail of what changed and when
  - Rollback to previous snapshots
  - Observer notifications on each applied delta

Patterns: Memento (snapshots), Command (delta ops), Observer (change events)

v9 changes:
  - apply_delta() type signature corrected: apply_fn returns List[str] (errors)
  - IncrementalApplier.apply_delta() accumulates errors from apply_fn return values
  - SnapshotStore.snapshots property added (was private _snapshots)
  - SnapshotStore.find(label) added for label-based lookup
  - ConfigDiffer exposed at module level
  - rollback(steps) added to IncrementalApplier

v9.1 changes (bug-fix / API completion):
  - ConfigDiffer.diff() now accepts ConfigDict OR ConfigSnapshot for old/new.
  - ConfigDiffer.diff() gains include_same: bool = False parameter.
    Default behaviour: SAME entries are excluded (only ADDED/CHANGED/REMOVED).
  - ConfigDiffer.summary(changes) static method added for human-readable output.
  - SnapshotStore.push() — alias for record() (preferred API going forward).
  - SnapshotStore.current() — alias for latest().
  - SnapshotStore.at(version) — lookup snapshot by version number.
  - SnapshotStore.version property — current version counter.
  - SnapshotStore.diff_last_two() — convenience helper.
  - IncrementalApplier.on_changes(observer) — register change observer.
  - IncrementalApplier.apply_delta() now accepts (key,val)→None callables as
    well as (key,val)→List[str]; exceptions are caught and recorded as errors.
  - compute_delta() excludes SAME entries (only actionable changes returned).
"""

from __future__ import annotations

import copy
import logging
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum, auto
from typing import Any, Callable, List, Optional, Union

from core.types import ConfigDict

logger = logging.getLogger("qute.incremental")

# Legacy type alias kept for callers that reference it explicitly.
# v9.1: apply_delta() now also accepts (key,val)→None; use Callable[..., Any].
ApplyFn = Callable[[str, Any], List[str]]


# ─────────────────────────────────────────────
# Change Types
# ─────────────────────────────────────────────

class ChangeKind(Enum):
    ADDED   = auto()   # key exists in new, not in old
    REMOVED = auto()   # key exists in old, not in new
    CHANGED = auto()   # key exists in both, value differs
    SAME    = auto()   # key exists in both, value identical


@dataclass(frozen=True)
class ConfigChange:
    """A single key-level change between two config snapshots."""
    key:       str
    kind:      ChangeKind
    old_value: Any = None
    new_value: Any = None

    def __str__(self) -> str:
        if self.kind == ChangeKind.ADDED:
            return f"+ {self.key} = {self.new_value!r}"
        elif self.kind == ChangeKind.REMOVED:
            return f"- {self.key}"
        elif self.kind == ChangeKind.CHANGED:
            return f"~ {self.key}: {self.old_value!r} → {self.new_value!r}"
        return f"  {self.key} (unchanged)"


# ─────────────────────────────────────────────
# Snapshot  (Memento pattern)
# ─────────────────────────────────────────────

@dataclass
class ConfigSnapshot:
    """Immutable point-in-time config state."""
    data:      ConfigDict
    timestamp: datetime = field(default_factory=datetime.now)
    label:     str      = ""
    version:   int      = 0

    def __post_init__(self) -> None:
        # Deep-copy on creation to ensure true immutability
        object.__setattr__(self, "data", copy.deepcopy(self.data))

    def keys(self) -> "set[str]":
        return set(self.data.keys())

    def get(self, key: str, default: Any = None) -> Any:
        return self.data.get(key, default)

    def __repr__(self) -> str:
        return (
            f"ConfigSnapshot(label={self.label!r}, "
            f"keys={len(self.data)}, "
            f"version={self.version}, "
            f"ts={self.timestamp.strftime('%H:%M:%S')})"
        )


# ─────────────────────────────────────────────
# Differ
# ─────────────────────────────────────────────

class ConfigDiffer:
    """
    Computes the diff between two config dicts or ConfigSnapshots.

    v9:   exposed as a standalone class for direct use by orchestrator.
    v9.1: diff() accepts ConfigDict or ConfigSnapshot (duck-typed);
          include_same parameter controls whether SAME entries are returned;
          summary() static method for human-readable change summaries.
    """

    @staticmethod
    def diff(
        old:          "Union[ConfigDict, ConfigSnapshot]",
        new:          "Union[ConfigDict, ConfigSnapshot]",
        include_same: bool = False,
    ) -> List[ConfigChange]:
        """
        Compute element-wise diff between two configs.

        Args:
            old:          Old config state — ConfigDict or ConfigSnapshot.
            new:          New config state — ConfigDict or ConfigSnapshot.
            include_same: If True, SAME entries are included in the result.
                          Default False — only ADDED, CHANGED, and REMOVED
                          are returned (the actionable set).

        Returns:
            Sorted list of ConfigChange entries (by key name).
        """
        old_data: ConfigDict = old.data if isinstance(old, ConfigSnapshot) else old
        new_data: ConfigDict = new.data if isinstance(new, ConfigSnapshot) else new

        changes: List[ConfigChange] = []
        all_keys = set(old_data.keys()) | set(new_data.keys())

        for key in sorted(all_keys):
            in_old = key in old_data
            in_new = key in new_data

            if in_old and in_new:
                if old_data[key] != new_data[key]:
                    changes.append(ConfigChange(
                        key=key, kind=ChangeKind.CHANGED,
                        old_value=old_data[key], new_value=new_data[key],
                    ))
                elif include_same:
                    changes.append(ConfigChange(
                        key=key, kind=ChangeKind.SAME,
                        old_value=old_data[key], new_value=new_data[key],
                    ))
            elif in_new:
                changes.append(ConfigChange(
                    key=key, kind=ChangeKind.ADDED,
                    new_value=new_data[key],
                ))
            else:
                changes.append(ConfigChange(
                    key=key, kind=ChangeKind.REMOVED,
                    old_value=old_data[key],
                ))

        return changes

    @staticmethod
    def summary(changes: List[ConfigChange]) -> str:
        """
        Produce a compact human-readable summary of a change list.

        Example output::

            +2 added  ~1 changed  -1 removed

        Each kind is only shown when count > 0.
        Returns ``"(no changes)"`` for an empty list.
        """
        added   = sum(1 for c in changes if c.kind == ChangeKind.ADDED)
        changed = sum(1 for c in changes if c.kind == ChangeKind.CHANGED)
        removed = sum(1 for c in changes if c.kind == ChangeKind.REMOVED)
        same    = sum(1 for c in changes if c.kind == ChangeKind.SAME)

        parts: List[str] = []
        if added:   parts.append(f"+{added} added")
        if changed: parts.append(f"~{changed} changed")
        if removed: parts.append(f"-{removed} removed")
        if same:    parts.append(f"={same} same")
        return "  ".join(parts) if parts else "(no changes)"


# ─────────────────────────────────────────────
# Snapshot Store
# ─────────────────────────────────────────────

class SnapshotStore:
    """
    Ring-buffer store of config snapshots.

    v9:   snapshots property, find(label) lookup.
    v9.1: push() / current() aliases; at(version) lookup; version property;
          diff_last_two() convenience helper.

    Ring-buffer semantics: when the store exceeds max_history entries the
    oldest snapshot is evicted.  Evicted snapshots cannot be retrieved via
    at() or find().
    """

    def __init__(self, max_history: int = 10) -> None:
        self._snapshots:  List[ConfigSnapshot] = []
        self._max_history = max_history
        self._version     = 0

    # ── Properties ────────────────────────────────────────────────────

    @property
    def version(self) -> int:
        """Monotonically increasing snapshot version counter."""
        return self._version

    @property
    def snapshots(self) -> List[ConfigSnapshot]:
        """Read-only list of stored snapshots, oldest first."""
        return list(self._snapshots)

    # ── Internal ──────────────────────────────────────────────────────

    def _store(self, data: ConfigDict, label: str) -> ConfigSnapshot:
        if not data:
            logger.debug("[SnapshotStore] recording empty snapshot (label=%r)", label)

        self._version += 1
        snapshot = ConfigSnapshot(data=data, label=label, version=self._version)
        self._snapshots.append(snapshot)

        if len(self._snapshots) > self._max_history:
            evicted = self._snapshots.pop(0)
            logger.debug(
                "[SnapshotStore] evicted: %r (version=%d)",
                evicted.label, evicted.version,
            )

        logger.debug(
            "[SnapshotStore] recorded: label=%r  keys=%d  version=%d",
            label, len(data), self._version,
        )
        return snapshot

    # ── Public API ────────────────────────────────────────────────────

    def record(self, data: ConfigDict, label: str = "") -> ConfigSnapshot:
        """Record a new snapshot and return it."""
        return self._store(data, label)

    def push(self, data: ConfigDict, label: str = "") -> ConfigSnapshot:
        """Alias for record() — preferred in application code."""
        return self._store(data, label)

    def find(self, label: str) -> Optional[ConfigSnapshot]:
        """Return the most recent snapshot with *label*, or None."""
        for snap in reversed(self._snapshots):
            if snap.label == label:
                return snap
        return None

    def current(self) -> Optional[ConfigSnapshot]:
        """Return the most recently recorded snapshot (alias for latest())."""
        return self._snapshots[-1] if self._snapshots else None

    def latest(self) -> Optional[ConfigSnapshot]:
        """Return the most recently recorded snapshot."""
        return self._snapshots[-1] if self._snapshots else None

    def previous(self) -> Optional[ConfigSnapshot]:
        """Return the second-most-recently recorded snapshot."""
        return self._snapshots[-2] if len(self._snapshots) >= 2 else None

    def at(self, version: int) -> Optional[ConfigSnapshot]:
        """
        Return the snapshot with the given *version* number, or None.

        Only snapshots still within the ring buffer are accessible; evicted
        snapshots cannot be retrieved.
        """
        for snap in self._snapshots:
            if snap.version == version:
                return snap
        return None

    def diff_last_two(self) -> List[ConfigChange]:
        """
        Diff the two most recent snapshots.

        Returns an empty list if fewer than two snapshots exist.
        SAME entries are excluded (only actionable ADDED/CHANGED/REMOVED).
        """
        latest = self.current()
        prev   = self.previous()
        if latest is None or prev is None:
            return []
        return ConfigDiffer.diff(prev, latest)

    def clear(self) -> None:
        """Remove all stored snapshots.  Useful in tests."""
        self._snapshots.clear()
        logger.debug("[SnapshotStore] cleared")

    def __len__(self) -> int:
        return len(self._snapshots)

    def __repr__(self) -> str:
        return f"SnapshotStore(count={len(self._snapshots)}, max={self._max_history})"


# ─────────────────────────────────────────────
# Incremental Applier
# ─────────────────────────────────────────────

class IncrementalApplier:
    """
    Computes config deltas and applies only changed keys.

    Typical usage::

        store   = SnapshotStore()
        applier = IncrementalApplier(store)

        applier.record(old_settings, "before")
        # ... rebuild layers ...
        applier.record(new_settings, "after")

        changes = applier.compute_delta()
        errors  = applier.apply_delta(changes, apply_fn)

    v9 changes:
      - apply_delta() apply_fn corrected to return List[str] (errors)
      - apply_delta() accumulates ALL errors from all key applications
      - rollback(steps) added

    v9.1 changes:
      - apply_delta() accepts (key, val) → None OR (key, val) → List[str];
        exceptions in apply_fn are caught and recorded as error strings.
      - on_changes(observer): register a Callable[[List[ConfigChange]], None]
        called after each successful apply_delta().
      - compute_delta() excludes SAME entries (only actionable changes).
    """

    def __init__(self, store: SnapshotStore) -> None:
        self._store     = store
        self._observers: List[Callable[[List[ConfigChange]], None]] = []

    # ── Observer registration ──────────────────────────────────────────

    def on_changes(self, observer: Callable[[List[ConfigChange]], None]) -> None:
        """
        Register a callback invoked after each apply_delta() call.

        The observer receives the list of successfully applied changes
        (ADDED + CHANGED only; REMOVED and SAME are never passed).
        """
        self._observers.append(observer)

    # ── Snapshot management ───────────────────────────────────────────

    def record(self, data: ConfigDict, label: str = "") -> ConfigSnapshot:
        """Record a new snapshot into the store."""
        return self._store.record(data, label=label)

    # ── Delta computation ─────────────────────────────────────────────

    def compute_delta(self) -> List[ConfigChange]:
        """
        Diff the two most recent snapshots.

        If fewer than two snapshots exist, all keys in the latest snapshot
        are returned as ADDED (first-run: apply everything).

        SAME entries are never included — only actionable changes are returned.
        """
        latest   = self._store.latest()
        previous = self._store.previous()

        if latest is None:
            return []

        if previous is None:
            # First snapshot: treat every key as ADDED
            return [
                ConfigChange(key=k, kind=ChangeKind.ADDED, new_value=v)
                for k, v in latest.data.items()
            ]

        return ConfigDiffer.diff(previous.data, latest.data, include_same=False)

    # ── Delta application ─────────────────────────────────────────────

    def apply_delta(
        self,
        changes:  List[ConfigChange],
        apply_fn: ApplyFn,
    ) -> List[str]:
        """
        Apply ADDED and CHANGED keys via *apply_fn*.

        REMOVED keys are skipped — qutebrowser has no public config.unset() API.
        SAME keys are skipped.

        Args:
            changes:  List from compute_delta().
            apply_fn: ``(key: str, value: Any) → Optional[List[str]]``
                      Returns a list of error strings (may be empty or None).
                      Exceptions are caught and recorded as errors.

        Returns:
            All error strings accumulated across all apply_fn calls.
        """
        all_errors:      List[str]         = []
        applied_changes: List[ConfigChange] = []

        for change in changes:
            if change.kind in (ChangeKind.ADDED, ChangeKind.CHANGED):
                if change.new_value is None:
                    continue
                try:
                    result: List[str] = apply_fn(change.key, change.new_value)
                    if isinstance(result, list) and result: # type: ignore[runtime]
                        all_errors.extend(result)
                        logger.warning(
                            "[IncrementalApplier] %s %s: %d error(s)",
                            change.kind.name, change.key, len(result),
                        )
                    else:
                        logger.debug(
                            "[IncrementalApplier] %s %s = %r",
                            change.kind.name, change.key, change.new_value,
                        )
                        applied_changes.append(change)
                except Exception as exc:
                    err = f"{change.kind.name} {change.key}: {exc}"
                    all_errors.append(err)
                    logger.warning("[IncrementalApplier] %s", err)

            elif change.kind == ChangeKind.REMOVED:
                logger.debug(
                    "[IncrementalApplier] REMOVED %s (skipped — no unset API)",
                    change.key,
                )
            # SAME: skip entirely

        # Notify observers
        if applied_changes:
            for obs in self._observers:
                try:
                    obs(applied_changes)
                except Exception as exc:
                    logger.warning(
                        "[IncrementalApplier] observer raised: %s", exc
                    )

        return all_errors

    # ── Rollback ──────────────────────────────────────────────────────

    def rollback(
        self,
        steps:    int,
        apply_fn: Callable[..., Any],
    ) -> List[str]:
        """
        Roll back to a previous snapshot by re-applying its values.

        ``steps=1`` targets the snapshot before the current one.
        Best-effort: removed keys cannot be un-set in qutebrowser.

        Args:
            steps:    How many snapshots to go back (1 = previous).
            apply_fn: ``(key, value) → Optional[List[str]]``

        Returns:
            Error strings from all apply_fn calls.
        """
        snapshots = self._store.snapshots
        if len(snapshots) < steps + 1:
            logger.warning(
                "[IncrementalApplier] rollback(%d) requested "
                "but only %d snapshot(s) available",
                steps, len(snapshots),
            )
            return [f"rollback({steps}): insufficient snapshot history"]

        target  = snapshots[-(steps + 1)]
        current = self._store.latest()

        if current is None:
            return ["rollback: no current snapshot"]

        diff = ConfigDiffer.diff(current, target)
        logger.info(
            "[IncrementalApplier] rolling back to label=%r (version=%d)",
            target.label, target.version,
        )
        return self.apply_delta(diff, apply_fn)

    # ── Diagnostics ───────────────────────────────────────────────────

    def summary(self) -> str:
        """Human-readable applier status for logging."""
        latest = self._store.latest()
        prev   = self._store.previous()
        if latest is None:
            return "IncrementalApplier(no snapshots)"
        if prev is None:
            return f"IncrementalApplier(1 snapshot: {latest!r})"
        diff   = ConfigDiffer.diff(prev, latest)
        return (
            f"IncrementalApplier("
            f"prev={prev!r}, "
            f"latest={latest!r}, "
            f"diff={ConfigDiffer.summary(diff)})"
        )
