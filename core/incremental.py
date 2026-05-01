"""
core/incremental.py
===================
Incremental Configuration Engine

Concept:
  Instead of full re-apply on every change, compute a delta (diff)
  between old and new config and apply only changed keys.

Architecture:
  ConfigSnapshot → Differ → Delta → IncrementalApplier → qutebrowser

Benefits:
  - Fast hot-reload (only changed keys re-applied)
  - Audit trail of what changed and when
  - Rollback to previous snapshots
  - Conflict detection between layers

Patterns: Memento (snapshots), Command (delta ops), Observer (change events)
"""

from __future__ import annotations

import copy
import logging
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum, auto
from typing import Any, Callable, Dict, List, Optional

logger = logging.getLogger("qute.incremental")

ConfigDict = Dict[str, Any]


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
# Snapshot (Memento pattern)
# ─────────────────────────────────────────────
@dataclass
class ConfigSnapshot:
    """Immutable point-in-time config state."""
    data:      ConfigDict
    timestamp: datetime = field(default_factory=datetime.now)
    label:     str = ""
    version:   int = 0

    def __post_init__(self):
        # Deep-copy to ensure true immutability
        object.__setattr__(self, "data", copy.deepcopy(self.data))

    def keys(self) -> set[str]:
        return set(self.data.keys())

    def get(self, key: str, default: Any = None) -> Any:
        return self.data.get(key, default)

    def __repr__(self) -> str:
        return (
            f"<Snapshot v{self.version} "
            f"label={self.label!r} "
            f"keys={len(self.data)} "
            f"at={self.timestamp:%H:%M:%S}>"
        )


# ─────────────────────────────────────────────
# Differ
# ─────────────────────────────────────────────
class ConfigDiffer:
    """
    Computes the delta between two ConfigSnapshots.
    Handles flat dicts; nested dicts are compared by value equality.
    """

    @staticmethod
    def diff(
        old: ConfigSnapshot,
        new: ConfigSnapshot,
        include_same: bool = False,
    ) -> List[ConfigChange]:
        """
        Returns list of ConfigChange items.
        include_same=True also includes unchanged keys (for audit).
        """
        old_keys = old.keys()
        new_keys = new.keys()
        all_keys = old_keys | new_keys

        changes: List[ConfigChange] = []

        for key in sorted(all_keys):
            if key in new_keys and key not in old_keys:
                changes.append(ConfigChange(
                    key=key, kind=ChangeKind.ADDED,
                    new_value=new.get(key),
                ))
            elif key in old_keys and key not in new_keys:
                changes.append(ConfigChange(
                    key=key, kind=ChangeKind.REMOVED,
                    old_value=old.get(key),
                ))
            else:
                ov, nv = old.get(key), new.get(key)
                if ov != nv:
                    changes.append(ConfigChange(
                        key=key, kind=ChangeKind.CHANGED,
                        old_value=ov, new_value=nv,
                    ))
                elif include_same:
                    changes.append(ConfigChange(
                        key=key, kind=ChangeKind.SAME,
                        old_value=ov, new_value=nv,
                    ))

        return changes

    @staticmethod
    def summary(changes: List[ConfigChange]) -> str:
        added   = sum(1 for c in changes if c.kind == ChangeKind.ADDED)
        removed = sum(1 for c in changes if c.kind == ChangeKind.REMOVED)
        changed = sum(1 for c in changes if c.kind == ChangeKind.CHANGED)
        return f"+{added} -{removed} ~{changed}"


# ─────────────────────────────────────────────
# Snapshot Store (history + rollback)
# ─────────────────────────────────────────────
class SnapshotStore:
    """
    Maintains a bounded history of ConfigSnapshots.
    Supports rollback and diff between arbitrary versions.
    """

    def __init__(self, max_history: int = 20):
        self._snapshots: List[ConfigSnapshot] = []
        self._max = max_history
        self._version = 0

    def push(self, data: ConfigDict, label: str = "") -> ConfigSnapshot:
        """Create and store a new snapshot."""
        self._version += 1
        snap = ConfigSnapshot(
            data=data,
            label=label or f"v{self._version}",
            version=self._version,
        )
        self._snapshots.append(snap)
        if len(self._snapshots) > self._max:
            self._snapshots.pop(0)
        logger.debug("[SnapshotStore] pushed %s", snap)
        return snap

    def current(self) -> Optional[ConfigSnapshot]:
        return self._snapshots[-1] if self._snapshots else None

    def previous(self) -> Optional[ConfigSnapshot]:
        return self._snapshots[-2] if len(self._snapshots) >= 2 else None

    def at(self, version: int) -> Optional[ConfigSnapshot]:
        for s in self._snapshots:
            if s.version == version:
                return s
        return None

    def diff_last_two(self) -> List[ConfigChange]:
        """Diff current against previous snapshot."""
        cur = self.current()
        prev = self.previous()
        if cur is None or prev is None:
            return []
        return ConfigDiffer.diff(prev, cur)

    def history_summary(self) -> str:
        lines = ["SnapshotStore history:"]
        for s in self._snapshots:
            lines.append(f"  {s}")
        return "\n".join(lines)

    @property
    def version(self) -> int:
        return self._version

    def __len__(self) -> int:
        return len(self._snapshots)


# ─────────────────────────────────────────────
# Incremental Applier
# ─────────────────────────────────────────────
ChangeObserver = Callable[[List[ConfigChange]], None]


class IncrementalApplier:
    """
    Applies only the delta between two snapshots.
    Avoids re-applying unchanged configuration on reload.
    """

    def __init__(self, store: SnapshotStore):
        self._store = store
        self._observers: List[ChangeObserver] = []

    def on_changes(self, observer: ChangeObserver) -> "IncrementalApplier":
        self._observers.append(observer)
        return self

    def record(self, data: ConfigDict, label: str = "") -> ConfigSnapshot:
        """Record new state; returns the new snapshot."""
        return self._store.push(data, label)

    def compute_delta(self) -> List[ConfigChange]:
        """Compute what changed since last snapshot."""
        changes = self._store.diff_last_two()
        if changes:
            summary = ConfigDiffer.summary(changes)
            logger.info("[IncrementalApplier] delta: %s", summary)
        return changes

    def apply_delta(
        self,
        changes: List[ConfigChange],
        apply_fn: Callable[[str, Any], None],
        remove_fn: Optional[Callable[[str], None]] = None,
    ) -> List[str]:
        """
        Apply only changed/added keys via apply_fn(key, value).
        Removed keys handled by remove_fn(key) if provided.
        Returns list of error strings.
        """
        errors: List[str] = []
        applied = 0

        for change in changes:
            if change.kind == ChangeKind.SAME:
                continue

            try:
                if change.kind in (ChangeKind.ADDED, ChangeKind.CHANGED):
                    apply_fn(change.key, change.new_value)
                    applied += 1
                    logger.debug(
                        "[IncrementalApplier] apply %s %s = %r",
                        change.kind.name, change.key, change.new_value
                    )
                elif change.kind == ChangeKind.REMOVED and remove_fn:
                    remove_fn(change.key)
                    applied += 1
                    logger.debug(
                        "[IncrementalApplier] remove %s", change.key
                    )
            except Exception as e:
                err = f"[incremental] {change.key}: {e}"
                errors.append(err)
                logger.error(err)

        # Notify observers
        if changes:
            for obs in self._observers:
                try:
                    obs(changes)
                except Exception as e:
                    logger.error("[IncrementalApplier] observer error: %s", e)

        logger.info(
            "[IncrementalApplier] applied %d/%d changes, %d errors",
            applied, len(changes), len(errors)
        )
        return errors


