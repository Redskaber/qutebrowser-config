"""
core/protocol.py
================
Inter-Module Communication Protocol

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

Strict-mode notes (Pyright):
  - Removed unused imports: ``ABC``, ``abstractmethod``, ``Enum``, ``auto``,
    ``Generic`` (none were used in this module's actual code).
  - ``EventHandler``, ``CommandHandler``, ``QueryHandler`` are explicit
    ``Callable`` aliases with concrete signatures.
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
    id: str = field(default_factory=lambda: str(uuid4())[:8])
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
    layer_name: str = ""
    key_count: int = 0


@dataclass(frozen=True)
class ConfigErrorEvent(Event):
    error_msg: str = ""
    layer_name: str = ""


@dataclass(frozen=True)
class ThemeChangedEvent(Event):
    theme_name: str = ""


@dataclass(frozen=True)
class BindingRegisteredEvent(Event):
    key: str = ""
    command: str = ""
    mode: str = "normal"


# ─────────────────────────────────────────────
# Concrete Commands
# ─────────────────────────────────────────────
@dataclass(frozen=True)
class ApplyLayerCommand(Command):
    layer_name: str = ""
    priority: int = 50


@dataclass(frozen=True)
class ReloadConfigCommand(Command):
    reason: str = "manual"


@dataclass(frozen=True)
class SetOptionCommand(Command):
    key: str = ""
    value: Any = None


# ─────────────────────────────────────────────
# Concrete Queries
# ─────────────────────────────────────────────
@dataclass(frozen=True)
class GetOptionQuery(Query):
    key: str = ""
    default: Any = None


@dataclass(frozen=True)
class ListLayersQuery(Query):
    pass


# ─────────────────────────────────────────────
# Event Bus (Pub/Sub)
# ─────────────────────────────────────────────
EventHandler   = Callable[[Event], None]
CommandHandler = Callable[[Command], Optional[Any]]
QueryHandler   = Callable[[Query], Any]


class EventBus:
    """
    Thread-safe publish/subscribe bus.

    Usage::

        bus = EventBus()
        bus.subscribe(LayerAppliedEvent, lambda e: print(e))
        bus.publish(LayerAppliedEvent(layer_name="base"))
    """

    def __init__(self) -> None:
        self._subscribers: Dict[str, List[EventHandler]] = {}
        self._lock = threading.RLock()
        self._wildcard: List[EventHandler] = []

    def subscribe(
        self,
        event_type: Type[Event],
        handler: EventHandler,
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
        """Subscribe to every event."""
        with self._lock:
            self._wildcard.append(handler)
        return self

    def publish(self, event: Event) -> int:
        """Publish event; returns count of handlers invoked."""
        topic = event.topic()
        with self._lock:
            handlers = list(self._subscribers.get(topic, []))
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

    def unsubscribe(self, event_type: Type[Event], handler: EventHandler) -> None:
        topic = event_type.__name__
        with self._lock:
            handlers = self._subscribers.get(topic, [])
            if handler in handlers:
                handlers.remove(handler)


# ─────────────────────────────────────────────
# Command Bus
# ─────────────────────────────────────────────
class CommandBus:
    """
    Routes Commands to exactly one registered handler.
    Fails loudly if no handler or multiple handlers.
    """

    def __init__(self) -> None:
        self._handlers: Dict[str, CommandHandler] = {}

    def register(self, command_type: Type[Command], handler: CommandHandler) -> None:
        topic = command_type.__name__
        if topic in self._handlers:
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

    def ask(self, query: Query) -> Any:
        topic = query.topic()
        handler = self._handlers.get(topic)
        if handler is None:
            raise LookupError(f"QueryBus: no handler for {topic}")
        return handler(query)


# ─────────────────────────────────────────────
# Message Router (aggregate facade)
# ─────────────────────────────────────────────
class MessageRouter:
    """
    Unified entry point for all inter-module communication.
    Modules receive this; they don't know about each other.
    """

    def __init__(self) -> None:
        self.events   = EventBus()
        self.commands = CommandBus()
        self.queries  = QueryBus()

    def emit(self, event: Event) -> int:
        return self.events.publish(event)

    def send(self, command: Command) -> Optional[Any]:
        return self.commands.dispatch(command)

    def ask(self, query: Query) -> Any:
        return self.queries.ask(query)


