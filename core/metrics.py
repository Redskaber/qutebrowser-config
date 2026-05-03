"""
core/metrics.py
===============
Configuration Metrics & Telemetry  (v12)

Extracts the timing/metrics responsibility from ConfigOrchestrator into a
dedicated, composable module following the Single Responsibility Principle.

Architecture
------------
Previously, ``orchestrator.py`` maintained a bare ``_last_metrics: Dict[str, float]``
dict and directly called ``router.emit_metrics(...)`` inline.  That scattered
telemetry concerns across the orchestration logic.

v12 centralises this into:

  MetricsSample   — immutable snapshot of one phase's metrics
  MetricsCollector — accumulates samples; queryable; emits via callback
  PhaseTimer      — context-manager for convenient wall-clock timing

Pattern: Memento (MetricsSample), Strategy (emit callback), Context Manager.

Integration
-----------
``ConfigOrchestrator`` constructs a ``MetricsCollector`` and calls::

    with self._metrics.time("build") as t:
        ...build logic...
    self._metrics.record("build", t.elapsed_ms, key_count=n)

Or, for one-liner use with the phase helper::

    self._metrics.emit("apply", duration_ms=42.1, key_count=15)

The collector emits via its registered callback (``on_emit``) which maps to
``router.emit_metrics(...)`` — keeping the orchestrator free of telemetry
plumbing.

Zero-import policy
------------------
``core/metrics.py`` does NOT import from any other project module.
All coupling to MessageRouter happens through the callback injection.

Strict-mode (Pyright)
---------------------
  - All fields typed.
  - MetricsSample is a frozen dataclass.
  - PhaseTimer.__exit__ typed for exception suppression.
  - EmitCallback = Callable[[str, float, int], None]

v12 (new module):
  - MetricsSample: frozen dataclass (phase, duration_ms, key_count, timestamp)
  - MetricsCollector: record(), get(), summary(), last_n(), all_phases(),
                      clear(), on_emit(), emit()
  - PhaseTimer: context-manager wrapper for perf_counter timing
  - get_metrics_collector() / reset_metrics_collector(): module-level singleton
  - metrics_time() convenience context manager
"""

from __future__ import annotations

import logging
import threading
from collections import deque
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Callable, Deque, Dict, Iterator, List, Optional

logger = logging.getLogger("qute.metrics")


# ─────────────────────────────────────────────
# Emit Callback Type
# ─────────────────────────────────────────────

EmitCallback = Callable[[str, float, int], None]
"""Signature: (phase: str, duration_ms: float, key_count: int) → None"""


# ─────────────────────────────────────────────
# MetricsSample
# ─────────────────────────────────────────────

@dataclass(frozen=True)
class MetricsSample:
    """
    Immutable record of one phase's performance metrics.

    Fields
    ------
    phase       : Phase identifier — "build" | "apply" | "reload" | "host_policies"
    duration_ms : Wall-clock duration of the phase in milliseconds
    key_count   : Number of config keys processed in this phase
    timestamp   : UTC datetime when this sample was recorded
    meta        : Optional extra key/value context (e.g. layer_count, error_count)
    """
    phase:       str
    duration_ms: float
    key_count:   int
    timestamp:   datetime       = field(default_factory=lambda: datetime.now(timezone.utc), compare=False)
    meta:        Dict[str, Any] = field(default_factory=dict[str, Any], compare=False)

    def __str__(self) -> str:
        ts = self.timestamp.strftime("%H:%M:%S.%f")[:-3]
        return (
            f"[{ts}] {self.phase:20s}  "
            f"{self.duration_ms:7.1f}ms  "
            f"keys={self.key_count}"
        )


# ─────────────────────────────────────────────
# Phase Timer (context manager)
# ─────────────────────────────────────────────

class PhaseTimer:
    """
    Context manager that measures wall-clock duration of a block.

    Usage::

        timer = PhaseTimer()
        with timer:
            ... expensive work ...
        print(timer.elapsed_ms)

    Or via the module helper::

        with metrics_time() as t:
            ...
        ms = t.elapsed_ms
    """

    def __init__(self) -> None:
        self._start: float = 0.0
        self._end:   float = 0.0

    def __enter__(self) -> "PhaseTimer":
        import time
        self._start = time.perf_counter()
        return self

    def __exit__(
        self,
        exc_type: Optional[type],
        exc_val:  Optional[BaseException],
        exc_tb:   Optional[Any],
    ) -> bool:
        import time
        self._end = time.perf_counter()
        return False   # never suppress exceptions

    @property
    def elapsed_ms(self) -> float:
        """Wall-clock duration in milliseconds.  0.0 if timer not yet stopped."""
        if self._end == 0.0:
            import time
            return (time.perf_counter() - self._start) * 1000.0
        return (self._end - self._start) * 1000.0


# ─────────────────────────────────────────────
# MetricsCollector
# ─────────────────────────────────────────────

class MetricsCollector:
    """
    Thread-safe accumulator of MetricsSample objects.

    Maintains a capped deque of recent samples (default: 128).
    Calls a registered ``EmitCallback`` on every ``emit()`` call so that
    the orchestrator's MessageRouter integration is injected, not hard-wired.

    Usage (in orchestrator)::

        collector = MetricsCollector(capacity=64)
        collector.on_emit(lambda ph, ms, n: router.emit_metrics(ph, ms, n))

        # time a phase:
        with PhaseTimer() as t:
            ...build...
        collector.emit("build", t.elapsed_ms, key_count=n_sets)

        # query:
        collector.last_n(5)           → List[MetricsSample]
        collector.get("build")        → Optional[MetricsSample]  (latest)
        collector.summary()           → str
    """

    def __init__(self, capacity: int = 128) -> None:
        self._samples:   Deque[MetricsSample] = deque(maxlen=capacity)
        self._callbacks: List[EmitCallback]   = []
        self._lock:      threading.Lock        = threading.Lock()

    # ── Callback registration ──────────────────────────────────────────

    def on_emit(self, callback: EmitCallback) -> "MetricsCollector":
        """Register a callback invoked on every emit() call.  Returns self."""
        self._callbacks.append(callback)
        return self

    # ── Recording ─────────────────────────────────────────────────────

    def emit(
        self,
        phase:       str,
        duration_ms: float,
        key_count:   int = 0,
        **meta:      Any,
    ) -> MetricsSample:
        """
        Record a MetricsSample and invoke all registered callbacks.

        Args:
            phase       : Phase identifier string.
            duration_ms : Duration of the phase in milliseconds.
            key_count   : Number of keys/items processed.
            **meta      : Additional metadata stored in MetricsSample.meta.

        Returns:
            The newly recorded MetricsSample.
        """
        sample = MetricsSample(
            phase=phase,
            duration_ms=duration_ms,
            key_count=key_count,
            meta=dict(meta),
        )
        with self._lock:
            self._samples.append(sample)

        logger.debug("[Metrics] %s", sample)

        for cb in self._callbacks:
            try:
                cb(phase, duration_ms, key_count)
            except Exception as exc:   # pragma: no cover
                logger.warning("[Metrics] emit callback raised: %s", exc)

        return sample

    # ── Query ──────────────────────────────────────────────────────────

    def get(self, phase: str) -> Optional[MetricsSample]:
        """Return the most recent sample for *phase*, or None."""
        with self._lock:
            # Scan from newest to oldest
            for sample in reversed(self._samples):
                if sample.phase == phase:
                    return sample
        return None

    def last_n(self, n: int = 10) -> List[MetricsSample]:
        """Return the last *n* samples (newest last)."""
        with self._lock:
            items = list(self._samples)
        return items[-n:]

    def all_phases(self) -> List[str]:
        """Return unique phase names seen so far, in order of first occurrence."""
        seen: Dict[str, None] = {}  # ordered dict trick
        with self._lock:
            for s in self._samples:
                seen[s.phase] = None
        return list(seen)

    def iter_phase(self, phase: str) -> Iterator[MetricsSample]:
        """Yield all samples for *phase* in recorded order."""
        with self._lock:
            items = list(self._samples)
        for s in items:
            if s.phase == phase:
                yield s

    def clear(self) -> None:
        """Remove all stored samples."""
        with self._lock:
            self._samples.clear()
        logger.debug("[Metrics] cleared")

    def __len__(self) -> int:
        with self._lock:
            return len(self._samples)

    # ── Summary ────────────────────────────────────────────────────────

    def summary(self, last_n: int = 20) -> str:
        """
        Return a human-readable summary of the last *last_n* samples.

        Example output::

            Metrics (last 5 samples):
              [14:32:01.042] build                2.3ms  keys=47
              [14:32:01.045] apply               11.8ms  keys=47
              [14:32:01.057] host_policies        0.7ms  keys=3
              [14:32:15.100] reload               3.1ms  keys=2
        """
        samples = self.last_n(last_n)
        if not samples:
            return "Metrics: (no samples recorded)"
        lines = [f"Metrics (last {len(samples)} samples):"]
        for s in samples:
            lines.append(f"  {s}")
        return "\n".join(lines)

    def totals_by_phase(self) -> Dict[str, float]:
        """
        Return cumulative duration (ms) keyed by phase name.

        Useful for profiling across many reload cycles.
        """
        totals: Dict[str, float] = {}
        with self._lock:
            for s in self._samples:
                totals[s.phase] = totals.get(s.phase, 0.0) + s.duration_ms
        return totals


# ─────────────────────────────────────────────
# Module-level singleton
# ─────────────────────────────────────────────

_singleton_lock = threading.Lock()
_default_collector: Optional[MetricsCollector] = None


def get_metrics_collector() -> MetricsCollector:
    """
    Return the module-level MetricsCollector singleton.

    The first call creates it with default capacity (128).
    Subsequent calls always return the same instance.
    Thread-safe.
    """
    global _default_collector
    if _default_collector is None:
        with _singleton_lock:
            if _default_collector is None:
                _default_collector = MetricsCollector()
    return _default_collector


def reset_metrics_collector(capacity: int = 128) -> MetricsCollector:
    """
    Replace the module-level singleton with a fresh collector.

    Useful in tests to ensure a clean slate.
    """
    global _default_collector
    with _singleton_lock:
        _default_collector = MetricsCollector(capacity=capacity)
    return _default_collector


# ─────────────────────────────────────────────
# Convenience context manager
# ─────────────────────────────────────────────

@contextmanager
def metrics_time() -> Iterator[PhaseTimer]:
    """
    Convenience context manager that yields a running PhaseTimer.

    Usage::

        with metrics_time() as t:
            ... work ...
        collector.emit("my_phase", t.elapsed_ms)
    """
    timer = PhaseTimer()
    timer.__enter__()
    try:
        yield timer
    finally:
        timer.__exit__(None, None, None)
