"""
core/state.py
=============
Configuration Lifecycle State Machine

Architecture:
  IDLE → LOADING → VALIDATING → APPLYING → ACTIVE
                ↘               ↘          ↘
               ERROR           ERROR      ERROR
                 ↓               ↓
             RELOADING ──────────┘

State transitions are purely data-driven (TRANSITIONS table).
No state mutation outside of send(). Observers are notified after
every transition; entry/exit actions run synchronously.

Principles:
  - Explicit over implicit: every valid transition is declared
  - Single source of truth: TRANSITIONS dict owns all valid paths
  - Observer pattern: zero coupling between FSM and its consumers
  - Separation of concerns: lifecycle hooks live in lifecycle.py

NOTE: LifecycleHook and LifecycleManager are defined in lifecycle.py.
      Import them from there — NOT from this module.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Any, Callable, Dict, List, Optional, Set, Tuple

logger = logging.getLogger("qute.state")


# ─────────────────────────────────────────────
# State Definitions
# ─────────────────────────────────────────────

class ConfigState(Enum):
    """All valid states in the configuration lifecycle."""
    IDLE       = auto()   # initial; nothing loaded
    LOADING    = auto()   # reading layer sources
    VALIDATING = auto()   # running validation pipeline
    APPLYING   = auto()   # writing to qutebrowser config API
    ACTIVE     = auto()   # fully applied; browser is running
    ERROR      = auto()   # one or more fatal errors; partial state
    RELOADING  = auto()   # hot-reload requested; transitioning back


class ConfigEvent(Enum):
    """Events that drive state transitions."""
    START_LOAD    = auto()   # begin loading layers
    LOAD_DONE     = auto()   # all layers built successfully
    LOAD_FAILED   = auto()   # layer build raised an exception
    VALIDATE_DONE = auto()   # validation passed
    VALIDATE_FAIL = auto()   # validation found fatal errors
    APPLY_DONE    = auto()   # all settings applied to qutebrowser
    APPLY_FAIL    = auto()   # apply encountered errors
    RELOAD        = auto()   # hot-reload requested (from ACTIVE or ERROR)
    RESET         = auto()   # manual reset back to IDLE


# ─────────────────────────────────────────────
# Transition Table  (single source of truth)
# ─────────────────────────────────────────────

# (from_state, event) → to_state
#
# Design notes:
#   • APPLY_START was removed — apply() enters APPLYING via build()'s VALIDATE_DONE.
#     Sending APPLY_START from apply() when already in APPLYING was the bug that
#     produced the spurious "no transition" warning in the log.
#   • RELOADING + START_LOAD → LOADING allows build() to be called directly
#     after reload() triggers the RELOAD event.
#   • IDLE + RELOAD → LOADING is a convenience path for manual/test invocations.

TRANSITIONS: Dict[Tuple[ConfigState, ConfigEvent], ConfigState] = {
    # ── Normal happy path ──────────────────────────────────────────────
    (ConfigState.IDLE,       ConfigEvent.START_LOAD):    ConfigState.LOADING,
    (ConfigState.LOADING,    ConfigEvent.LOAD_DONE):     ConfigState.VALIDATING,
    (ConfigState.VALIDATING, ConfigEvent.VALIDATE_DONE): ConfigState.APPLYING,
    (ConfigState.APPLYING,   ConfigEvent.APPLY_DONE):    ConfigState.ACTIVE,

    # ── Error paths ────────────────────────────────────────────────────
    (ConfigState.LOADING,    ConfigEvent.LOAD_FAILED):   ConfigState.ERROR,
    (ConfigState.VALIDATING, ConfigEvent.VALIDATE_FAIL): ConfigState.ERROR,
    (ConfigState.APPLYING,   ConfigEvent.APPLY_FAIL):    ConfigState.ERROR,

    # ── Hot-reload paths ───────────────────────────────────────────────
    (ConfigState.ACTIVE,     ConfigEvent.RELOAD):        ConfigState.RELOADING,
    (ConfigState.ERROR,      ConfigEvent.RELOAD):        ConfigState.RELOADING,
    (ConfigState.RELOADING,  ConfigEvent.START_LOAD):    ConfigState.LOADING,

    # ── Convenience / recovery ─────────────────────────────────────────
    # Allow RELOAD from IDLE for testing and manual invocation.
    (ConfigState.IDLE,       ConfigEvent.RELOAD):        ConfigState.LOADING,

    # Global reset — bring any terminal state back to IDLE.
    (ConfigState.ERROR,      ConfigEvent.RESET):         ConfigState.IDLE,
    (ConfigState.ACTIVE,     ConfigEvent.RESET):         ConfigState.IDLE,
    (ConfigState.RELOADING,  ConfigEvent.RESET):         ConfigState.IDLE,
}


# ─────────────────────────────────────────────
# State Context  (mutable payload per lifecycle)
# ─────────────────────────────────────────────

@dataclass
class StateContext:
    """Mutable context carried alongside the FSM state."""
    current:          ConfigState = ConfigState.IDLE
    previous:         Optional[ConfigState] = None
    errors:           List[str] = field(default_factory=list)
    warnings:         List[str] = field(default_factory=list)
    metadata:         Dict[str, Any] = field(default_factory=dict)
    transition_count: int = 0


# ─────────────────────────────────────────────
# Observer type aliases
# ─────────────────────────────────────────────

StateObserver = Callable[[ConfigState, ConfigState, ConfigEvent], None]
# signature: (from_state, to_state, triggering_event) → None

EntryAction  = Callable[["StateContext"], None]
ExitAction   = Callable[["StateContext"], None]


# ─────────────────────────────────────────────
# State Machine
# ─────────────────────────────────────────────

class ConfigStateMachine:
    """
    Finite State Machine for the configuration lifecycle.

    Usage::

        fsm = ConfigStateMachine()
        fsm.on_transition(lambda f, t, e: print(f"{f.name} → {t.name}"))
        fsm.on_enter(ConfigState.LOADING, lambda ctx: print("loading…"))

        ok = fsm.send(ConfigEvent.START_LOAD)   # True
        ok = fsm.send(ConfigEvent.VALIDATE_DONE) # False — wrong state
    """

    def __init__(self) -> None:
        self._context = StateContext()
        self._observers: List[StateObserver] = []
        self._entry_actions: Dict[ConfigState, List[EntryAction]] = {}
        self._exit_actions:  Dict[ConfigState, List[ExitAction]] = {}

    # ── Public interface ───────────────────────────────────────────────

    @property
    def state(self) -> ConfigState:
        return self._context.current

    @property
    def context(self) -> StateContext:
        return self._context

    def send(self, event: ConfigEvent, **payload) -> bool:
        """
        Fire an event against the current state.

        Returns ``True`` if a transition occurred, ``False`` if the
        (state, event) pair has no defined target (invalid in current state).
        Additional ``payload`` keyword arguments are merged into
        ``context.metadata`` for observers/entry-actions to inspect.
        """
        key = (self._context.current, event)
        next_state = TRANSITIONS.get(key)

        if next_state is None:
            logger.warning(
                "[FSM] ignored — no transition from %s on %s",
                self._context.current.name, event.name,
            )
            return False

        from_state = self._context.current

        # ── Exit actions ───────────────────────────────────────────────
        for action in self._exit_actions.get(from_state, []):
            self._safe_call(action, self._context, label=f"exit/{from_state.name}")

        # ── Transition ────────────────────────────────────────────────
        self._context.previous         = from_state
        self._context.current          = next_state
        self._context.transition_count += 1
        self._context.metadata.update(payload)

        logger.info(
            "[FSM] %s + %s → %s  (transition #%d)",
            from_state.name, event.name,
            next_state.name, self._context.transition_count,
        )

        # ── Entry actions ──────────────────────────────────────────────
        for action in self._entry_actions.get(next_state, []):
            self._safe_call(action, self._context, label=f"entry/{next_state.name}")

        # ── Observers ─────────────────────────────────────────────────
        for obs in self._observers:
            self._safe_call(
                lambda o=obs: o(from_state, next_state, event),
                label="observer",
            )

        return True

    def on_transition(self, observer: StateObserver) -> "ConfigStateMachine":
        """Register a transition observer (called after every transition)."""
        self._observers.append(observer)
        return self

    def on_enter(self, state: ConfigState, action: EntryAction) -> "ConfigStateMachine":
        """Register an entry action for a specific state."""
        self._entry_actions.setdefault(state, []).append(action)
        return self

    def on_exit(self, state: ConfigState, action: ExitAction) -> "ConfigStateMachine":
        """Register an exit action for a specific state."""
        self._exit_actions.setdefault(state, []).append(action)
        return self

    def is_in(self, *states: ConfigState) -> bool:
        """Return True if current state is one of the given states."""
        return self._context.current in states

    def add_error(self, msg: str) -> None:
        self._context.errors.append(msg)

    def add_warning(self, msg: str) -> None:
        self._context.warnings.append(msg)

    # ── Helpers ────────────────────────────────────────────────────────

    @staticmethod
    def _safe_call(fn: Callable, *args, label: str = "handler") -> None:
        try:
            fn(*args)
        except Exception as exc:
            logger.error("[FSM] %s raised: %s", label, exc)

    def __repr__(self) -> str:
        return (
            f"<FSM state={self._context.current.name} "
            f"transitions={self._context.transition_count}>"
        )
