"""
core/event_filter.py
====================
Event Bus Middleware / Filter Chain  (v13)

Adds composable middleware to the ``EventBus`` without modifying it.

Problem (v12 and earlier)
--------------------------
``EventBus`` is a direct pub/sub bus — every subscriber receives every
published event of its type.  There is no way to:

  - Throttle noisy events (e.g. MetricsEvent firing on every key)
  - Log all events to a structured audit channel without coupling
  - Deduplicate identical events within a time window
  - Route events based on payload content (e.g. only errors)
  - Mock/replace the bus in integration tests without monkey-patching

Solution (v13)
--------------
``EventFilter`` wraps an ``EventBus`` and intercepts ``publish()`` calls
through a **middleware chain** (Chain of Responsibility).  Each middleware
can:

  * pass the event downstream unchanged         → ``next(event)``
  * transform the event before passing           → ``next(transformed)``
  * block the event entirely                     → (do nothing)
  * produce a side-effect (log, audit, metric)   → call side-effect then ``next``
  * buffer the event for batch dispatch

Architecture
------------
::

    producer.publish(event)
        ↓
    EventFilter.publish(event)
        ↓
    MiddlewareChain[0] → … → MiddlewareChain[N] → EventBus.publish(event)

``EventFilter`` is a drop-in replacement for ``EventBus`` (same interface).
``MessageRouter`` can be constructed with an ``EventFilter`` instead of the
raw ``EventBus`` — or the filter can wrap an existing bus post-construction.

Patterns
--------
  Chain of Responsibility (middleware chain)
  Decorator (EventFilter wraps EventBus)
  Strategy (each Middleware is a strategy)

Built-in Middleware
-------------------
  ``LoggingMiddleware``    — structured log every event at DEBUG
  ``DedupeMiddleware``     — suppress duplicate events within a TTL window
  ``ThrottleMiddleware``   — rate-limit a specific event type (N per second)
  ``FilterMiddleware``     — allow only events matching a predicate
  ``AuditMiddleware``      — record events to AuditLog (zero coupling)

Strict-mode (Pyright)
---------------------
  Middleware is a ``Protocol`` (structural typing) for maximum flexibility.
  ``EventFilter.publish()`` returns ``int`` (subscriber count, same as EventBus).

v13 (new module):
  - ``Middleware`` Protocol
  - ``MiddlewareChain``
  - ``EventFilter(EventBus)``
  - LoggingMiddleware, DedupeMiddleware, ThrottleMiddleware,
    FilterMiddleware, AuditMiddleware
  - ``build_default_filter()`` factory for drop-in wiring
"""

from __future__ import annotations

import logging
import time
import threading
from collections import defaultdict
from typing import Callable, DefaultDict, Dict, List, Optional, Type

from core.protocol import Event, EventBus, EventHandler

logger = logging.getLogger("qute.event_filter")

# Next-function type: consumes event and returns subscriber count
NextFn = Callable[[Event], int]


# ─────────────────────────────────────────────
# Middleware Protocol (structural typing)
# ─────────────────────────────────────────────

class Middleware:
    """
    Base class for EventBus middleware.

    Subclass and override ``__call__``.  Each middleware receives the event
    and a ``next`` function.  Call ``next(event)`` to pass the event further;
    return without calling ``next`` to block the event.
    """

    def __call__(self, event: Event, next_fn: NextFn) -> int:
        """
        Process *event*.

        Parameters
        ----------
        event   : the event being published
        next_fn : call this to pass the event to the next middleware / bus

        Returns
        -------
        int — subscriber count returned by next_fn (or 0 if blocked)
        """
        return next_fn(event)

    @property
    def name(self) -> str:
        return type(self).__name__


# ─────────────────────────────────────────────
# Middleware Chain
# ─────────────────────────────────────────────

class MiddlewareChain:
    """
    Ordered list of Middleware that composes into a single call chain.

    The final node in the chain calls ``bus.publish(event)`` directly.
    """

    def __init__(self, middlewares: List[Middleware], bus: EventBus) -> None:
        self._mw  = list(middlewares)
        self._bus = bus

    def dispatch(self, event: Event) -> int:
        """Run the full chain and dispatch to bus at the end."""

        def make_next(idx: int) -> NextFn:
            if idx < len(self._mw):
                mw = self._mw[idx]
                def _next(evt: Event) -> int:
                    return mw(evt, make_next(idx + 1))
                return _next
            else:
                # Terminal: call the real bus
                return lambda evt: self._bus.publish(evt)

        return make_next(0)(event)

    def append(self, middleware: Middleware) -> "MiddlewareChain":
        """Append a middleware to the end of the chain (before the bus)."""
        self._mw.append(middleware)
        return self

    def prepend(self, middleware: Middleware) -> "MiddlewareChain":
        """Prepend a middleware to the start of the chain."""
        self._mw.insert(0, middleware)
        return self

    def describe(self) -> str:
        names = " → ".join(m.name for m in self._mw) + " → EventBus"
        return f"MiddlewareChain[{names}]"


# ─────────────────────────────────────────────
# EventFilter  (wraps EventBus)
# ─────────────────────────────────────────────

class EventFilter(EventBus):
    """
    Drop-in EventBus replacement that routes publish() through middleware.

    All ``subscribe``, ``unsubscribe_all``, etc. methods are delegated to
    the wrapped ``EventBus``.  Only ``publish()`` is intercepted.

    Usage::

        bus = EventBus()
        flt = EventFilter(bus).use(LoggingMiddleware()).use(DedupeMiddleware(ttl=0.5))
        router = MessageRouter()
        router.events = flt      # swap in
    """

    def __init__(self, bus: Optional[EventBus] = None) -> None:
        # DO NOT call super().__init__() — we delegate to wrapped bus
        self._bus: EventBus = bus if bus is not None else EventBus()
        self._chain = MiddlewareChain([], self._bus)

    # ── Middleware registration ────────────────────────────────────────

    def use(self, middleware: Middleware) -> "EventFilter":
        """Append middleware to the chain.  Returns self for fluent chaining."""
        self._chain.append(middleware)
        return self

    def prepend(self, middleware: Middleware) -> "EventFilter":
        """Prepend middleware (runs first)."""
        self._chain.prepend(middleware)
        return self

    # ── EventBus interface — delegate subscription to wrapped bus ─────

    def subscribe(self, event_type: type, handler: EventHandler) -> "EventFilter":  # type: ignore[override]
        self._bus.subscribe(event_type, handler)
        return self

    def subscribe_all(self, handler: EventHandler) -> "EventFilter":  # type: ignore[override]
        self._bus.subscribe_all(handler)
        return self

    def unsubscribe_all(self) -> None:
        self._bus.unsubscribe_all()

    # ── Core: intercepted publish ──────────────────────────────────────

    def publish(self, event: Event) -> int:
        """Publish *event* through the middleware chain."""
        return self._chain.dispatch(event)

    # ── Introspection ─────────────────────────────────────────────────

    def describe(self) -> str:
        return self._chain.describe()


# ─────────────────────────────────────────────
# Built-in Middleware
# ─────────────────────────────────────────────

class LoggingMiddleware(Middleware):
    """
    Log every event at DEBUG level before passing it downstream.

    Optionally restrict to a specific event type.
    """

    def __init__(
        self,
        event_type: Optional[Type[Event]] = None,
        level: int = logging.DEBUG,
    ) -> None:
        self._type  = event_type
        self._level = level

    @property
    def name(self) -> str:
        suffix = f"({self._type.__name__})" if self._type else ""
        return f"LoggingMiddleware{suffix}"

    def __call__(self, event: Event, next_fn: NextFn) -> int:
        if self._type is None or isinstance(event, self._type):
            logger.log(
                self._level,
                "[EventFilter] %s id=%s src=%s",
                event.topic(), event.id, event.source,
            )
        return next_fn(event)


class DedupeMiddleware(Middleware):
    """
    Suppress duplicate events of the same type within a TTL window.

    Two events are considered duplicate if their ``topic()`` is identical
    and they arrive within *ttl* seconds of each other.

    Useful to suppress rapid MetricsEvent or LayerConflictEvent bursts.
    """

    def __init__(self, ttl: float = 0.5) -> None:
        self._ttl:  float                = ttl
        self._last: Dict[str, float]     = {}
        self._lock: threading.Lock       = threading.Lock()

    @property
    def name(self) -> str:
        return f"DedupeMiddleware(ttl={self._ttl}s)"

    def __call__(self, event: Event, next_fn: NextFn) -> int:
        topic = event.topic()
        now   = time.monotonic()
        with self._lock:
            last = self._last.get(topic, 0.0)
            if now - last < self._ttl:
                logger.debug("[DedupeMiddleware] suppressed duplicate: %s", topic)
                return 0
            self._last[topic] = now
        return next_fn(event)


class ThrottleMiddleware(Middleware):
    """
    Rate-limit a specific event type to at most ``max_per_sec`` events/second.

    Excess events are silently dropped (not queued).
    Set ``event_type=None`` to throttle ALL event types globally.
    """

    def __init__(
        self,
        max_per_sec: float,
        event_type:  Optional[Type[Event]] = None,
    ) -> None:
        self._max_per_sec = max(0.001, max_per_sec)
        self._min_gap     = 1.0 / self._max_per_sec
        self._event_type  = event_type
        self._last: DefaultDict[str, float] = defaultdict(float)
        self._lock: threading.Lock          = threading.Lock()

    @property
    def name(self) -> str:
        t = self._event_type.__name__ if self._event_type else "ALL"
        return f"ThrottleMiddleware({t} ≤{self._max_per_sec}/s)"

    def __call__(self, event: Event, next_fn: NextFn) -> int:
        if self._event_type is not None and not isinstance(event, self._event_type):
            return next_fn(event)
        topic = event.topic()
        now   = time.monotonic()
        with self._lock:
            if now - self._last[topic] < self._min_gap:
                return 0
            self._last[topic] = now
        return next_fn(event)


class FilterMiddleware(Middleware):
    """
    Allow only events matching *predicate*.

    Events that return False are silently dropped.

    Example — only allow health/error events::

        flt.use(FilterMiddleware(
            lambda e: e.topic() in {"HealthReportReadyEvent", "ConfigErrorEvent"}
        ))
    """

    def __init__(self, predicate: Callable[[Event], bool], label: str = "") -> None:
        self._predicate = predicate
        self._label     = label

    @property
    def name(self) -> str:
        return f"FilterMiddleware({self._label or '...'})"

    def __call__(self, event: Event, next_fn: NextFn) -> int:
        if not self._predicate(event):
            return 0
        return next_fn(event)


class AuditMiddleware(Middleware):
    """
    Record every event to the global AuditLog at DEBUG level.

    Zero coupling: imports AuditLog lazily to avoid circular imports.
    """

    def __init__(self, component: str = "event_bus") -> None:
        self._component = component

    @property
    def name(self) -> str:
        return "AuditMiddleware"

    def __call__(self, event: Event, next_fn: NextFn) -> int:
        try:
            from core.audit import audit_debug
            audit_debug(self._component, f"event:{event.topic()}", id=event.id)
        except Exception:
            pass
        return next_fn(event)


class CountingMiddleware(Middleware):
    """
    Count events by topic.  Useful for testing and diagnostics.
    Mutable state is thread-safe.
    """

    def __init__(self) -> None:
        self._counts: DefaultDict[str, int] = defaultdict(int)
        self._lock:   threading.Lock        = threading.Lock()

    @property
    def name(self) -> str:
        return "CountingMiddleware"

    def __call__(self, event: Event, next_fn: NextFn) -> int:
        with self._lock:
            self._counts[event.topic()] += 1
        return next_fn(event)

    def count(self, topic: str) -> int:
        """Return how many events of *topic* have been seen."""
        with self._lock:
            return self._counts[topic]

    def total(self) -> int:
        """Total events across all topics."""
        with self._lock:
            return sum(self._counts.values())

    def reset(self) -> None:
        with self._lock:
            self._counts.clear()

    def summary(self) -> str:
        with self._lock:
            lines = ["CountingMiddleware:"]
            for topic, count in sorted(self._counts.items()):
                lines.append(f"  {topic}: {count}")
            return "\n".join(lines)


# ─────────────────────────────────────────────
# Default Factory
# ─────────────────────────────────────────────

def build_default_filter(bus: Optional[EventBus] = None) -> EventFilter:
    """
    Build a production-ready EventFilter with sensible defaults:

    1. AuditMiddleware    — record all events to AuditLog at DEBUG
    2. LoggingMiddleware  — log at DEBUG
    3. DedupeMiddleware   — suppress duplicate MetricsEvents within 100ms

    Usage::

        from core.event_filter import build_default_filter
        router.events = build_default_filter(router.events)
    """
    flt = EventFilter(bus or EventBus())
    flt.use(AuditMiddleware())
    flt.use(LoggingMiddleware())
    flt.use(DedupeMiddleware(ttl=0.1))
    return flt
