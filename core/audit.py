"""
core/audit.py
=============
Configuration Audit System  (v11)

Records every configuration change, phase transition, and health event
into a structured, queryable audit log.  Provides:

  - AuditEntry    : immutable record of one auditable event
  - AuditLevel    : severity classification (DEBUG / INFO / WARN / ERROR)
  - AuditLog      : thread-safe, capped ring-buffer of AuditEntry objects
  - AuditFilter   : composable predicate for querying entries
  - AuditExporter : render audit log to JSON / Markdown / plain text

Architecture
------------
The audit system sits orthogonally to the pipeline: it is *not* a PipeStage
and does not transform data.  Instead, components call ``audit.record(...)``
as a side channel.  The log is consumed by:
  - ``scripts/diagnostics.py``  (CLI audit report)
  - ``orchestrator.audit_trail()`` (summary string for :config-source feedback)
  - Tests (assert specific events were recorded)

Design choices:
  - Ring buffer with configurable cap (default 512 entries) prevents unbounded
    memory growth during long browser sessions with frequent :config-source.
  - Thread-safe: uses a threading.Lock for all mutations.
  - Zero coupling: AuditLog does not import from any other project module.
  - Strict-mode: all fields typed; no bare Any where avoidable.

Patterns: Memento (each entry is an immutable record), Observer (emitter
calls record(); consumers query at their leisure), Ring Buffer.

v11 (new module):
  - AuditLevel enum: DEBUG / INFO / WARN / ERROR
  - AuditEntry frozen dataclass: timestamp, level, component, message, meta
  - AuditLog: record(), query(), last_n(), clear(), export_text(),
              export_json(), export_markdown(), summary()
  - AuditFilter: dataclass-based composable predicate; .matches(entry)
  - AuditExporter: static factory producing formatted strings
  - Global singleton: ``get_audit_log()`` / ``reset_audit_log()``
  - Module-level helpers: audit_debug(), audit_info(), audit_warn(), audit_error()
"""

from __future__ import annotations

import json
import logging
import threading
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum, auto
from typing import Any, Dict, List, Optional

logger = logging.getLogger("qute.audit")


# ─────────────────────────────────────────────
# Audit Level
# ─────────────────────────────────────────────

class AuditLevel(Enum):
    """Severity / importance of an audit entry."""
    DEBUG = auto()   # trace-level: every key applied, every stage entered
    INFO  = auto()   # normal operation: phase start/end, context switch
    WARN  = auto()   # notable: health warning, policy warn, slow apply
    ERROR = auto()   # failure: apply error, health error, FSM error

    @property
    def symbol(self) -> str:
        return {
            AuditLevel.DEBUG: "·",
            AuditLevel.INFO:  "✓",
            AuditLevel.WARN:  "⚠",
            AuditLevel.ERROR: "✗",
        }[self]

    def __le__(self, other: "AuditLevel") -> bool:
        return self.value <= other.value


# ─────────────────────────────────────────────
# Audit Entry (immutable record)
# ─────────────────────────────────────────────

@dataclass(frozen=True)
class AuditEntry:
    """
    A single immutable audit record.

    Attributes:
        ts:        UTC timestamp of the event.
        level:     Severity classification.
        component: Originating component name (e.g. "orchestrator", "health").
        message:   Human-readable description of the event.
        meta:      Optional structured key-value metadata (phase, key, count…).
        seq:       Monotonically increasing sequence number (assigned by AuditLog).
    """
    ts:        datetime
    level:     AuditLevel
    component: str
    message:   str
    meta:      Dict[str, Any] = field(default_factory=dict[str, Any])
    seq:       int            = 0

    @property
    def ts_iso(self) -> str:
        return self.ts.strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"

    @property
    def ts_short(self) -> str:
        return self.ts.strftime("%H:%M:%S.%f")[:-3]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "seq":       self.seq,
            "ts":        self.ts_iso,
            "level":     self.level.name,
            "component": self.component,
            "message":   self.message,
            "meta":      self.meta,
        }

    def __str__(self) -> str:
        meta_str = ""
        if self.meta:
            pairs = " ".join(f"{k}={v!r}" for k, v in list(self.meta.items())[:4])
            meta_str = f"  [{pairs}]"
        return (
            f"[{self.seq:04d}] {self.ts_short} "
            f"{self.level.symbol} [{self.component}] {self.message}{meta_str}"
        )


# ─────────────────────────────────────────────
# Audit Filter (composable predicate)
# ─────────────────────────────────────────────

@dataclass
class AuditFilter:
    """
    Composable filter for querying audit entries.

    All set fields are ANDed together; unset fields (None) are wildcards.

    Example::

        f = AuditFilter(level_min=AuditLevel.WARN, component="health")
        errors = log.query(f)
    """
    level_min:  Optional[AuditLevel] = None   # inclusive lower bound
    level_max:  Optional[AuditLevel] = None   # inclusive upper bound
    component:  Optional[str]        = None   # exact match
    message_contains: Optional[str] = None   # substring match
    since_seq:  Optional[int]        = None   # seq >= this value

    def matches(self, entry: AuditEntry) -> bool:
        if self.level_min is not None and entry.level.value < self.level_min.value:
            return False
        if self.level_max is not None and entry.level.value > self.level_max.value:
            return False
        if self.component is not None and entry.component != self.component:
            return False
        if self.message_contains is not None and self.message_contains not in entry.message:
            return False
        if self.since_seq is not None and entry.seq < self.since_seq:
            return False
        return True

    @classmethod
    def errors_and_warnings(cls) -> "AuditFilter":
        return cls(level_min=AuditLevel.WARN)

    @classmethod
    def errors_only(cls) -> "AuditFilter":
        return cls(level_min=AuditLevel.ERROR)

    @classmethod
    def component_filter(cls, component: str) -> "AuditFilter":
        return cls(component=component)

    @classmethod
    def since(cls, seq: int) -> "AuditFilter":
        return cls(since_seq=seq)


# ─────────────────────────────────────────────
# Audit Log (ring buffer, thread-safe)
# ─────────────────────────────────────────────

class AuditLog:
    """
    Thread-safe ring buffer of AuditEntry objects.

    When the buffer reaches ``capacity``, the oldest entries are evicted
    (FIFO) to keep memory bounded.  The sequence counter never resets —
    seq numbers are globally monotonic for the session lifetime.

    Usage::

        log = AuditLog(capacity=512)
        log.record(AuditLevel.INFO, "orchestrator", "build() started", phase="build")
        entries = log.query(AuditFilter.errors_and_warnings())
    """

    def __init__(self, capacity: int = 512) -> None:
        self._capacity  = max(1, capacity)
        self._entries:  List[AuditEntry] = []
        self._seq:      int              = 0
        self._lock:     threading.Lock   = threading.Lock()

    # ── Mutation ──────────────────────────────────────────────────────

    def record(
        self,
        level:     AuditLevel,
        component: str,
        message:   str,
        **meta:    Any,
    ) -> AuditEntry:
        """
        Record an event.  Returns the created entry.

        Keyword arguments beyond level/component/message are stored as ``meta``.

        Example::
            log.record(AuditLevel.INFO, "orchestrator", "build complete",
                       duration_ms=12.3, key_count=87)
        """
        with self._lock:
            self._seq += 1
            entry = AuditEntry(
                ts        = datetime.now(tz=timezone.utc),
                level     = level,
                component = component,
                message   = message,
                meta      = dict(meta),
                seq       = self._seq,
            )
            self._entries.append(entry)
            # Evict oldest if over capacity
            if len(self._entries) > self._capacity:
                self._entries = self._entries[-self._capacity:]

        logger.debug("[Audit] %s", entry)
        return entry

    def clear(self) -> None:
        """Remove all entries (does not reset seq counter)."""
        with self._lock:
            self._entries.clear()

    # ── Query ─────────────────────────────────────────────────────────

    def query(
        self,
        flt: Optional[AuditFilter] = None,
    ) -> List[AuditEntry]:
        """Return entries matching *flt* (all entries if flt is None)."""
        with self._lock:
            entries = list(self._entries)
        if flt is None:
            return entries
        return [e for e in entries if flt.matches(e)]

    def last_n(self, n: int, flt: Optional[AuditFilter] = None) -> List[AuditEntry]:
        """Return the last *n* entries, optionally filtered."""
        entries = self.query(flt)
        return entries[-n:]

    def errors(self) -> List[AuditEntry]:
        return self.query(AuditFilter.errors_only())

    def warnings_and_above(self) -> List[AuditEntry]:
        return self.query(AuditFilter.errors_and_warnings())

    @property
    def seq(self) -> int:
        """Current sequence counter (last assigned seq number)."""
        with self._lock:
            return self._seq

    @property
    def size(self) -> int:
        with self._lock:
            return len(self._entries)

    # ── Export ────────────────────────────────────────────────────────

    def summary(self, last_n: int = 20) -> str:
        """One-line summary + recent entries table."""
        entries = self.last_n(last_n)
        counts  = self._level_counts()
        header  = (
            f"AuditLog: {self.size} entries  "
            f"[errors={counts['ERROR']} warnings={counts['WARN']} "
            f"info={counts['INFO']}]"
        )
        lines = [header]
        if entries:
            lines.append("")
            for e in entries:
                lines.append(f"  {e}")
        return "\n".join(lines)

    def export_text(self, flt: Optional[AuditFilter] = None) -> str:
        """Plain-text export, one entry per line."""
        return "\n".join(str(e) for e in self.query(flt))

    def export_json(self, flt: Optional[AuditFilter] = None) -> str:
        """JSON array export."""
        return json.dumps([e.to_dict() for e in self.query(flt)], indent=2)

    def export_markdown(self, flt: Optional[AuditFilter] = None) -> str:
        """Markdown table export."""
        entries = self.query(flt)
        if not entries:
            return "_No audit entries._\n"
        lines = [
            "| Seq | Time | Level | Component | Message |",
            "| --- | ---- | ----- | --------- | ------- |",
        ]
        for e in entries:
            msg = e.message.replace("|", "\\|")[:80]
            lines.append(
                f"| {e.seq} | {e.ts_short} | {e.level.symbol} {e.level.name} "
                f"| `{e.component}` | {msg} |"
            )
        return "\n".join(lines)

    # ── Private ───────────────────────────────────────────────────────

    def _level_counts(self) -> Dict[str, int]:
        with self._lock:
            entries = list(self._entries)
        counts: Dict[str, int] = {lvl.name: 0 for lvl in AuditLevel}
        for e in entries:
            counts[e.level.name] = counts.get(e.level.name, 0) + 1
        return counts

    def __len__(self) -> int:
        return self.size

    def __repr__(self) -> str:
        return f"AuditLog(size={self.size}, seq={self.seq}, cap={self._capacity})"


# ─────────────────────────────────────────────
# Global Singleton
# ─────────────────────────────────────────────

_global_log: Optional[AuditLog] = None
_global_lock: threading.Lock = threading.Lock()


def get_audit_log(capacity: int = 512) -> AuditLog:
    """
    Return the process-wide singleton AuditLog.
    Created on first call; subsequent calls return the same instance.
    Thread-safe.
    """
    global _global_log
    with _global_lock:
        if _global_log is None:
            _global_log = AuditLog(capacity=capacity)
    return _global_log


def reset_audit_log(capacity: int = 512) -> AuditLog:
    """
    Replace the global singleton with a fresh AuditLog.
    Primarily for tests that need a clean slate.
    """
    global _global_log
    with _global_lock:
        _global_log = AuditLog(capacity=capacity)
    return _global_log


# ─────────────────────────────────────────────
# Module-level convenience helpers
# ─────────────────────────────────────────────

def audit_debug(component: str, message: str, **meta: Any) -> None:
    get_audit_log().record(AuditLevel.DEBUG, component, message, **meta)


def audit_info(component: str, message: str, **meta: Any) -> None:
    get_audit_log().record(AuditLevel.INFO, component, message, **meta)


def audit_warn(component: str, message: str, **meta: Any) -> None:
    get_audit_log().record(AuditLevel.WARN, component, message, **meta)


def audit_error(component: str, message: str, **meta: Any) -> None:
    get_audit_log().record(AuditLevel.ERROR, component, message, **meta)


__all__ = [
    "AuditLevel",
    "AuditEntry",
    "AuditFilter",
    "AuditLog",
    "get_audit_log",
    "reset_audit_log",
    "audit_debug",
    "audit_info",
    "audit_warn",
    "audit_error",
]
