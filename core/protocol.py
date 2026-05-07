"""
core/protocol.py
================
Inter-Module Communication Protocol  (v17)

Architecture:
  Publisher → EventBus → [Subscriber, ...]
  Command → CommandBus → Handler
  Query → QueryBus → Handler → Result

Principles:
  - Dependency Inversion: modules communicate via protocol, not direct refs
  - Open/Closed: new message types without modifying bus
  - Single Responsibility: bus only routes, handlers only handle
  - Boundary Explicit: cross-module calls must go through protocol

Pattern: Event-Driven Architecture + CQRS (Command/Query Separation)

v17 additions (this file):
  - ContextSwitchedEvent gains a ``source`` field (default "startup"),
    mirroring SessionChangedEvent.  Now also tracks ``old_context`` accurately
    (orchestrator uses _active_context tracker, as v16 did for session/network).
  - GetActiveContextQuery()
    → returns the current context mode name string (mirrors GetActiveSessionQuery).
  - MessageRouter.emit_context_changed()  helper  [v17]
    → convenience wrapper for ContextSwitchedEvent emission.

v15 additions (retained):
  - SessionChangedEvent(old_session, new_session, source)
  - NetworkModeChangedEvent(old_mode, new_mode, proxy, source)
  - HotSwapCompletedEvent(operation, layer_name, changes, errors, duration_ms)
  - GetActiveNetworkQuery(), GetHotSwapStatusQuery(), GetActiveSessionQuery()
  - MessageRouter.emit_session_changed(), emit_network_changed(),
    emit_hot_swap_completed()

v12 additions (retained):
  - GetMetricsSummaryQuery(last_n)

v9 additions (retained):
  - ConfigReloadedEvent, SnapshotTakenEvent, LayerConflictEvent
  - PolicyDeniedEvent, MetricsEvent
  - GetSnapshotQuery, GetLayerDiffQuery, GetLayerNamesQuery
  - MessageRouter helper emitters

v5–v8 additions (retained):
  - ContextSwitchedEvent, HealthReportReadyEvent
  - GetHealthReportQuery, GetMergedConfigQuery
  - MessageRouter.emit_health()

Strict-mode notes (Pyright):
  - All dataclass fields have explicit types and defaults.
  - Callable aliases use concrete signatures.
  - No bare Callable usage anywhere.
"""

from __future__ import annotations

import logging
import threading
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Type, TypeVar
from uuid import uuid4

logger = logging.getLogger("qute.protocol")
T = TypeVar("T")


# ─────────────────────────────────────────────
# Message Types
# ─────────────────────────────────────────────

@dataclass(frozen=True)
class Message:
    """Base message: immutable, carries identity and payload."""
    id:     str = field(default_factory=lambda: str(uuid4())[:8])
    source: str = "unknown"

    def topic(self) -> str:
        return type(self).__name__


@dataclass(frozen=True)
class Event(Message):
    """
    Something that happened (past tense).
    Published after the fact; zero or many subscribers.
    """
    pass


@dataclass(frozen=True)
class Command(Message):
    """
    Intent to change something (imperative).
    Exactly one handler; may fail.
    """
    pass


@dataclass(frozen=True)
class Query(Message):
    """
    Request for information.
    Exactly one handler; returns a value.
    """
    pass


# ─────────────────────────────────────────────
# Concrete Events
# ─────────────────────────────────────────────

@dataclass(frozen=True)
class LayerAppliedEvent(Event):
    """Emitted when a single layer's settings have been applied."""
    layer_name: str = ""
    key_count:  int = 0


@dataclass(frozen=True)
class ConfigErrorEvent(Event):
    """Emitted on any config error (build, validate, or apply phase)."""
    error_msg:  str = ""
    layer_name: str = ""


@dataclass(frozen=True)
class ThemeChangedEvent(Event):
    """Emitted when the active theme changes."""
    theme_name: str = ""


@dataclass(frozen=True)
class BindingRegisteredEvent(Event):
    """Emitted when a keybinding is registered."""
    key:     str = ""
    command: str = ""
    mode:    str = "normal"


@dataclass(frozen=True)
class ContextSwitchedEvent(Event):
    """
    Emitted when the active browsing context is established or changes.

    v17: gains a ``source`` field and accurate ``old_context`` tracking,
    mirroring the v16 fix for SessionChangedEvent / NetworkModeChangedEvent.
    The orchestrator now tracks ``_active_context`` so ``old_context``
    reflects the actual previous value instead of always being ``"default"``.

    Fields:
        old_context: previous context mode name (or "default" on startup)
        new_context: newly active context mode name
        source:      "startup" | "hot_swap" | "env" | "file" | "user_override"
    """
    old_context: str = "default"
    new_context: str = "default"
    source:      str = "startup"


@dataclass(frozen=True)
class SessionChangedEvent(Event):
    """
    Emitted when the active session mode is established or changes.

    Mirrors ContextSwitchedEvent for the session subsystem.
    Emitted by orchestrator._maybe_emit_session_event() after build(),
    and by _WrappedHotSwap when the session layer is hot-swapped.

    Fields:
        old_session: previous session mode name (or "unknown" on startup)
        new_session: newly active session mode name
        source:      "startup" | "hot_swap" | "env" | "file" | "auto"
    """
    old_session: str = "unknown"
    new_session: str = "day"
    source:      str = "startup"


@dataclass(frozen=True)
class HealthReportReadyEvent(Event):
    """Emitted after HealthChecker.check() completes."""
    ok:            bool = True
    error_count:   int  = 0
    warning_count: int  = 0
    info_count:    int  = 0


@dataclass(frozen=True)
class ConfigReloadedEvent(Event):
    """
    Emitted after a successful hot-reload cycle completes.

    Fields:
        changes_count: number of keys that changed (ADDED + CHANGED + REMOVED)
        errors_count:  number of apply errors (0 = clean)
        duration_ms:   wall-clock time of the reload cycle in milliseconds
        reason:        trigger reason string
    """
    change_count: int   = 0
    error_count:  int   = 0
    duration_ms:  float = 0.0
    reason:       str   = "config-source"


@dataclass(frozen=True)
class SnapshotTakenEvent(Event):
    """
    Emitted when IncrementalApplier records a config snapshot.

    Fields:
        label:     human label passed to record(), e.g. "pre-reload"
        key_count: number of settings keys in the snapshot
        version:   snapshot store version counter
    """
    label:     str = ""
    key_count: int = 0
    version:   int = 0


@dataclass(frozen=True)
class LayerConflictEvent(Event):
    """
    Emitted when LayerStack detects a key override during merge.

    A conflict is NOT an error — it is the intended priority mechanism.
    This event is informational: useful for auditing and debugging.

    Fields:
        key:          the config key being overridden
        winner_layer: layer whose value wins (higher priority)
        loser_layer:  layer whose value is replaced (lower priority)
    """
    key:          str = ""
    winner_layer: str = ""
    loser_layer:  str = ""


@dataclass(frozen=True)
class PolicyDeniedEvent(Event):
    """
    Emitted when a PolicyChain DENY decision fires during apply.

    Fields:
        key:        the config key that was denied
        value:      the value that was rejected (repr form)
        reason:     policy denial reason string
        layer_name: layer that attempted to set this key
    """
    key:        str = ""
    value:      str = ""   # repr() of actual value
    reason:     str = ""
    layer_name: str = ""


@dataclass(frozen=True)
class MetricsEvent(Event):
    """
    Lightweight timing / sizing telemetry.

    Emitted at the end of build(), apply(), and reload() phases so that
    lifecycle hooks or external monitors can observe performance.

    Fields:
        phase:       "build" | "apply" | "reload" | "host_policies"
        duration_ms: wall-clock duration of the phase
        key_count:   number of settings processed in this phase
    """
    phase:       str   = ""
    duration_ms: float = 0.0
    key_count:   int   = 0


@dataclass(frozen=True)
class NetworkModeChangedEvent(Event):
    """
    Emitted when the active network/proxy mode is established or changes.

    Emitted by orchestrator after build() (source="startup") and after
    any hot-swap of the NetworkLayer (source="hot_swap").

    Fields:
        old_mode: previous NetworkMode value (or "unknown" on startup)
        new_mode: newly active NetworkMode value (e.g. "socks5", "system")
        proxy:    the resolved content.proxy value (e.g. "socks5://127.0.0.1:7897")
        source:   "startup" | "hot_swap" | "env" | "file" | "user_override"
    """
    old_mode: str = "unknown"
    new_mode: str = "system"
    proxy:    str = "system"
    source:   str = "startup"


@dataclass(frozen=True)
class HotSwapCompletedEvent(Event):
    """
    Emitted after any orchestrator-level LayerHotSwap operation.

    The orchestrator wraps LayerHotSwap in _WrappedHotSwap (Open/Closed),
    which emits this event after each swap/remove/insert operation.

    Fields:
        operation:   "swap" | "remove" | "insert"
        layer_name:  name of the layer that was operated on
        changes:     list of config-key change descriptions (informational)
        errors:      list of error strings (empty = success)
        duration_ms: wall-clock time of the hot-swap operation

    Properties:
        ok: True when errors is empty
    """
    operation:   str       = "swap"
    layer_name:  str       = ""
    changes:     List[str] = field(default_factory=list[str])
    errors:      List[str] = field(default_factory=list[str])
    duration_ms: float     = 0.0

    @property
    def ok(self) -> bool:
        """True when the hot-swap completed without errors."""
        return len(self.errors) == 0


# ─────────────────────────────────────────────
# Concrete Commands
# ─────────────────────────────────────────────

@dataclass(frozen=True)
class ApplyLayerCommand(Command):
    layer_name: str = ""
    priority:   int = 50


@dataclass(frozen=True)
class ReloadConfigCommand(Command):
    reason: str = "manual"


@dataclass(frozen=True)
class SetOptionCommand(Command):
    key:   str = ""
    value: Any = None


# ─────────────────────────────────────────────
# Concrete Queries
# ─────────────────────────────────────────────

@dataclass(frozen=True)
class GetOptionQuery(Query):
    key:     str = ""
    default: Any = None


@dataclass(frozen=True)
class ListLayersQuery(Query):
    pass


@dataclass(frozen=True)
class GetMergedConfigQuery(Query):
    """Request the fully-merged settings dict from the orchestrator."""
    pass


@dataclass(frozen=True)
class GetHealthReportQuery(Query):
    """Request the latest HealthReport from the orchestrator."""
    pass


@dataclass(frozen=True)
class GetSnapshotQuery(Query):
    """
    Request a specific config snapshot by label or index.

    Fields:
        label:  snapshot label string; None = return most recent snapshot
        index:  0-based index into snapshot history; -1 = most recent
    """
    label: Optional[str] = None
    index: int           = -1


@dataclass(frozen=True)
class GetLayerDiffQuery(Query):
    """
    Request the diff between two snapshot labels.

    Returns: List[ConfigChange] — may be empty if snapshots are identical
    or labels are not found.

    Fields:
        label_a: earlier snapshot label  (e.g. "pre-reload")
        label_b: later snapshot label    (e.g. "post-reload")
    """
    label_a: str = ""
    label_b: str = ""


@dataclass(frozen=True)
class GetLayerNamesQuery(Query):
    """
    Request the ordered list of registered layer names from the stack.

    Returns: List[str] ordered by priority (lowest first).
    """
    pass


@dataclass(frozen=True)
class GetMetricsSummaryQuery(Query):
    """
    Request a formatted metrics summary string from the orchestrator.

    Returns: str — human-readable table of recent MetricsSample records.
    Added in v12.
    """
    last_n: int = 20


@dataclass(frozen=True)
class GetActiveNetworkQuery(Query):
    """
    Request the currently active network proxy string.

    Returns: str — the resolved content.proxy value
    (e.g. "system", "none", "socks5://127.0.0.1:7897").

    Added in v14/v15.
    """
    pass


@dataclass(frozen=True)
class GetHotSwapStatusQuery(Query):
    """
    Request the result of the last hot-swap operation.

    Returns: Dict[str, Any] with keys:
        operation   str
        layer_name  str
        ok          bool
        errors      List[str]
        duration_ms float

    Returns {} if no hot-swap has been performed yet.

    Added in v14/v15.
    """
    pass


@dataclass(frozen=True)
class GetActiveSessionQuery(Query):
    """
    Request the currently active session mode name.

    Returns: str — session mode value (e.g. "day", "night", "focus"),
    or "unknown" if no SessionLayer is registered.

    Added in v15.
    """
    pass


@dataclass(frozen=True)
class GetActiveContextQuery(Query):
    """
    Request the currently active context mode name.

    Returns: str — context mode value (e.g. "default", "work", "research"),
    or "default" if no ContextLayer is registered.

    Mirrors GetActiveSessionQuery for the context subsystem.

    Added in v17.
    """
    pass


# ─────────────────────────────────────────────
# Bus Handler Types
# ─────────────────────────────────────────────

EventHandler   = Callable[[Event],   None]
CommandHandler = Callable[[Command], Optional[Any]]
QueryHandler   = Callable[[Query],   Any]


# ─────────────────────────────────────────────
# Event Bus (Pub/Sub)
# ─────────────────────────────────────────────

class EventBus:
    """
    Thread-safe publish/subscribe bus.

    Usage::

        bus = EventBus()
        bus.subscribe(LayerAppliedEvent, lambda e: print(e))
        bus.publish(LayerAppliedEvent(layer_name="base"))

    v9: unsubscribe_all() clears wildcard handlers for test isolation.
    """

    def __init__(self) -> None:
        self._subscribers: Dict[str, List[EventHandler]] = {}
        self._wildcard:    List[EventHandler]             = []
        self._lock = threading.RLock()

    def subscribe(
        self,
        event_type: Type[Event],
        handler:    EventHandler,
    ) -> "EventBus":
        topic = event_type.__name__
        with self._lock:
            self._subscribers.setdefault(topic, []).append(handler)
        logger.debug(
            "[EventBus] subscribed: %s → %s",
            topic,
            getattr(handler, "__name__", repr(handler)),
        )
        return self

    def subscribe_all(self, handler: EventHandler) -> "EventBus":
        """Subscribe to every event (wildcard)."""
        with self._lock:
            self._wildcard.append(handler)
        return self

    def unsubscribe(self, event_type: Type[Event], handler: EventHandler) -> None:
        topic = event_type.__name__
        with self._lock:
            handlers = self._subscribers.get(topic, [])
            if handler in handlers:
                handlers.remove(handler)

    def unsubscribe_all(self) -> None:
        """
        Clear ALL subscribers including wildcards.
        Useful in test teardown to prevent cross-test interference.
        """
        with self._lock:
            self._subscribers.clear()
            self._wildcard.clear()
        logger.debug("[EventBus] all subscribers cleared")

    def publish(self, event: Event) -> int:
        """
        Publish event to all typed subscribers + wildcards.
        Returns count of handlers successfully invoked.
        Exceptions in handlers are caught and logged — they never propagate.
        """
        topic = event.topic()
        with self._lock:
            handlers  = list(self._subscribers.get(topic, []))
            wildcards = list(self._wildcard)

        count = 0
        for handler in handlers + wildcards:
            try:
                handler(event)
                count += 1
            except Exception as exc:
                logger.error("[EventBus] handler error for %s: %s", topic, exc)
        logger.debug("[EventBus] published %s → %d handlers", topic, count)
        return count


# ─────────────────────────────────────────────
# Command Bus
# ─────────────────────────────────────────────

class CommandBus:
    """
    Routes Commands to exactly one registered handler.
    Fails loudly if no handler or (by default) multiple handlers.

    v9: allow_replace=True bypasses the duplicate-handler guard.
    This is ONLY for test overrides; production code should leave it False.
    """

    def __init__(self, allow_replace: bool = False) -> None:
        self._handlers:     Dict[str, CommandHandler] = {}
        self._allow_replace = allow_replace

    def register(
        self,
        command_type:  Type[Command],
        handler:       CommandHandler,
        allow_replace: Optional[bool] = None,
    ) -> None:
        topic = command_type.__name__
        _allow = allow_replace if allow_replace is not None else self._allow_replace
        if topic in self._handlers and not _allow:
            raise ValueError(f"CommandBus: duplicate handler for {topic}")
        self._handlers[topic] = handler
        logger.debug(
            "[CommandBus] registered: %s → %s",
            topic,
            getattr(handler, "__name__", repr(handler)),
        )

    def dispatch(self, command: Command) -> Optional[Any]:
        topic = command.topic()
        handler = self._handlers.get(topic)
        if handler is None:
            raise LookupError(f"CommandBus: no handler for {topic}")
        try:
            result = handler(command)
            logger.debug("[CommandBus] dispatched %s → ok", topic)
            return result
        except Exception as exc:
            logger.error("[CommandBus] handler error for %s: %s", topic, exc)
            raise


# ─────────────────────────────────────────────
# Query Bus
# ─────────────────────────────────────────────

class QueryBus:
    """Routes Queries to exactly one handler; returns result."""

    def __init__(self) -> None:
        self._handlers: Dict[str, QueryHandler] = {}

    def register(self, query_type: Type[Query], handler: QueryHandler) -> None:
        topic = query_type.__name__
        self._handlers[topic] = handler
        logger.debug(
            "[QueryBus] registered: %s → %s",
            topic,
            getattr(handler, "__name__", repr(handler)),
        )

    def ask(self, query: Query) -> Any:
        topic = query.topic()
        handler = self._handlers.get(topic)
        if handler is None:
            raise LookupError(f"QueryBus: no handler for {topic}")
        return handler(query)

    def has(self, query_type: Type[Query]) -> bool:
        """Return True if a handler is registered for this query type."""
        return query_type.__name__ in self._handlers


# ─────────────────────────────────────────────
# Message Router (aggregate facade)
# ─────────────────────────────────────────────

class MessageRouter:
    """
    Unified entry point for all inter-module communication.
    Modules receive this; they don't know about each other.

    Three buses:
      events   — fire-and-forget pub/sub (EventBus)
      commands — imperative, exactly-one-handler (CommandBus)
      queries  — request/response, exactly-one-handler (QueryBus)

    Convenience emitters:
      emit_health()             → HealthReportReadyEvent      [v5]
      emit_reload()             → ConfigReloadedEvent         [v9]
      emit_snapshot()           → SnapshotTakenEvent          [v9]
      emit_conflict()           → LayerConflictEvent          [v9]
      emit_policy_denied()      → PolicyDeniedEvent           [v9]
      emit_metrics()            → MetricsEvent                [v9]
      emit_session_changed()    → SessionChangedEvent         [v15]
      emit_network_changed()    → NetworkModeChangedEvent     [v15]
      emit_hot_swap_completed() → HotSwapCompletedEvent       [v15]
      emit_context_changed()    → ContextSwitchedEvent        [v17]
    """

    def __init__(self) -> None:
        self.events   = EventBus()
        self.commands = CommandBus()
        self.queries  = QueryBus()

    # ── Generic dispatch ────────────────────────────────────────────────

    def emit(self, event: Event) -> int:
        """Publish an event to all subscribers."""
        return self.events.publish(event)

    def send(self, command: Command) -> Optional[Any]:
        """Dispatch a command to its registered handler."""
        return self.commands.dispatch(command)

    def ask(self, query: Query) -> Any:
        """Ask a query; returns the handler's response."""
        return self.queries.ask(query)

    # ── Convenience emitters (v5) ────────────────────────────────────────

    def emit_health(
        self,
        ok:            bool,
        error_count:   int,
        warning_count: int,
        info_count:    int = 0,
    ) -> None:
        """Emit a HealthReportReadyEvent."""
        self.emit(HealthReportReadyEvent(
            ok=ok,
            error_count=error_count,
            warning_count=warning_count,
            info_count=info_count,
        ))

    def emit_reload(
        self,
        changes_count: int,
        errors_count:  int,
        duration_ms:   float,
        reason:        str,
    ) -> None:
        """Emit a ConfigReloadedEvent after a hot-reload cycle."""
        self.emit(ConfigReloadedEvent(
            change_count=changes_count,
            error_count=errors_count,
            duration_ms=duration_ms,
            reason=reason,
        ))

    def emit_snapshot(
        self,
        label:     str,
        key_count: int,
        version:   int,
    ) -> None:
        """Emit a SnapshotTakenEvent when a config snapshot is recorded."""
        self.emit(SnapshotTakenEvent(
            label=label,
            key_count=key_count,
            version=version,
        ))

    def emit_conflict(
        self,
        key:          str,
        winner_layer: str,
        loser_layer:  str,
    ) -> None:
        """Emit a LayerConflictEvent for a key override during merge."""
        self.emit(LayerConflictEvent(
            key=key,
            winner_layer=winner_layer,
            loser_layer=loser_layer,
        ))

    def emit_policy_denied(
        self,
        key:        str,
        value:      Any,
        reason:     str,
        layer_name: str = "",
    ) -> None:
        """Emit a PolicyDeniedEvent when a DENY decision fires."""
        self.emit(PolicyDeniedEvent(
            key=key,
            value=repr(value),
            reason=reason,
            layer_name=layer_name,
        ))

    def emit_metrics(
        self,
        phase:       str,
        duration_ms: float,
        key_count:   int,
    ) -> None:
        """Emit a MetricsEvent for a build/apply/reload phase."""
        self.emit(MetricsEvent(
            phase=phase,
            duration_ms=duration_ms,
            key_count=key_count,
        ))

    def emit_session_changed(
        self,
        old_session: str,
        new_session: str,
        source:      str = "startup",
    ) -> None:
        """Emit a SessionChangedEvent when session mode is established or changes.  ← v15"""
        self.emit(SessionChangedEvent(
            old_session=old_session,
            new_session=new_session,
            source=source,
        ))

    def emit_network_changed(
        self,
        old_mode: str,
        new_mode: str,
        proxy:    str,
        source:   str = "startup",
    ) -> None:
        """Emit a NetworkModeChangedEvent when the proxy/network mode changes.  ← v15"""
        self.emit(NetworkModeChangedEvent(
            old_mode=old_mode,
            new_mode=new_mode,
            proxy=proxy,
            source=source,
        ))

    def emit_hot_swap_completed(
        self,
        operation:   str,
        layer_name:  str,
        changes:     List[str],
        errors:      List[str],
        duration_ms: float,
    ) -> None:
        """Emit a HotSwapCompletedEvent after an orchestrator-level hot-swap.  ← v15"""
        self.emit(HotSwapCompletedEvent(
            operation=operation,
            layer_name=layer_name,
            changes=changes,
            errors=errors,
            duration_ms=duration_ms,
        ))

    def emit_context_changed(
        self,
        old_context: str,
        new_context: str,
        source:      str = "startup",
    ) -> None:
        """Emit a ContextSwitchedEvent when context mode is established or changes.  ← v17"""
        self.emit(ContextSwitchedEvent(
            old_context=old_context,
            new_context=new_context,
            source=source,
        ))
