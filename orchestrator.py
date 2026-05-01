"""
orchestrator.py
===============
Configuration Orchestrator  (composition root)

Responsibilities:
  1. Build the LayerStack
  2. Drive the Config State Machine
  3. Run the Layer Pipeline
  4. Apply resolved config to qutebrowser via ConfigApplier
  5. Emit lifecycle events via the MessageRouter

This is the *only* file with knowledge of the full system.
All other modules are purely functional; dependencies flow inward.

Principle: single wiring point, explicit dependency injection.

Fix applied vs original:
  Removed the spurious ``fsm.send(ConfigEvent.APPLY_START)`` call at the
  top of ``apply()``.  The FSM enters APPLYING state during ``build()``
  (via VALIDATING → VALIDATE_DONE → APPLYING).  Sending APPLY_START from
  inside APPLYING had no defined transition and always emitted a WARNING.
  The correct semantic is: APPLYING is the "apply in progress" state, and
  APPLY_DONE / APPLY_FAIL drive the exit.

  Also improved summary() to log the number of *settings keys* (not just
  the 3 top-level category keys) and the count of keybindings and aliases.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from core.layer import LayerStack
from core.lifecycle import LifecycleHook, LifecycleManager
from core.pipeline import ConfigPacket, LogStage, Pipeline
from core.protocol import (
    ConfigErrorEvent,
    LayerAppliedEvent,
    MessageRouter,
    ThemeChangedEvent,
)
from core.state import ConfigEvent, ConfigState, ConfigStateMachine
from core.strategy import PolicyChain, RangePolicy, TypeEnforcePolicy

logger = logging.getLogger("qute.orchestrator")

ConfigDict = Dict[str, Any]


# ─────────────────────────────────────────────
# Config Applier
# ─────────────────────────────────────────────

class ConfigApplier:
    """
    Translates a resolved ``ConfigDict`` into qutebrowser config API calls.

    Separated from the orchestrator so it can be replaced / mocked in tests
    without requiring a running qutebrowser instance.
    """

    def __init__(self, config_obj, bindings_obj):
        """
        Args:
            config_obj:   qutebrowser ``config`` object (provides .set/.bind)
            bindings_obj: qutebrowser ``c`` object (attribute-style access)
        """
        self._config = config_obj
        self._c      = bindings_obj

    def apply_settings(self, settings: ConfigDict) -> List[str]:
        """Apply flat key=value settings; return list of error strings."""
        errors: List[str] = []
        for key, value in settings.items():
            try:
                self._config.set(key, value)
                logger.debug("[Applier] set %s = %r", key, value)
            except Exception as exc:
                msg = f"set {key}: {exc}"
                errors.append(msg)
                logger.error("[Applier] %s", msg)
        return errors

    def apply_keybindings(
        self,
        bindings: List[tuple],
        clear_first: bool = True,
    ) -> List[str]:
        """
        Apply keybindings.

        Args:
            bindings:    list of ``(key, command, mode)`` or ``(key, command)`` tuples.
            clear_first: if True, call ``_clear_defaults()`` before binding.
        """
        errors: List[str] = []
        if clear_first:
            self._clear_defaults()

        for binding in bindings:
            if len(binding) == 3:
                key, command, mode = binding
            elif len(binding) == 2:
                key, command = binding
                mode = "normal"
            else:
                errors.append(f"invalid binding tuple: {binding}")
                continue

            try:
                self._config.bind(key, command, mode=mode)
                logger.debug("[Applier] bind %s → %r (%s)", key, command, mode)
            except Exception as exc:
                msg = f"bind {key} [{mode}]: {exc}"
                errors.append(msg)
                logger.error("[Applier] %s", msg)

        return errors

    def apply_aliases(self, aliases: ConfigDict) -> List[str]:
        errors: List[str] = []
        for alias, command in aliases.items():
            try:
                self._c.aliases[alias] = command
                logger.debug("[Applier] alias :%s → %r", alias, command)
            except Exception as exc:
                msg = f"alias {alias}: {exc}"
                errors.append(msg)
                logger.error("[Applier] %s", msg)
        return errors

    def apply_host_policy(self, pattern: str, settings: ConfigDict) -> List[str]:
        errors: List[str] = []
        for key, value in settings.items():
            try:
                self._config.set(key, value, pattern=pattern)
                logger.debug("[Applier] host-set %s  %s = %r", pattern, key, value)
            except Exception as exc:
                msg = f"host-set {pattern}/{key}: {exc}"
                errors.append(msg)
                logger.error("[Applier] %s", msg)
        return errors

    def _clear_defaults(self) -> None:
        """
        Unbind qutebrowser default keybindings we intend to override.

        We deliberately do NOT blanket-clear all defaults here — that would
        break built-in bindings we haven't overridden.  Layers emit exactly
        the bindings they want; qutebrowser merges them on top of defaults.
        """
        pass


# ─────────────────────────────────────────────
# Orchestrator
# ─────────────────────────────────────────────

class ConfigOrchestrator:
    """
    Main orchestration engine.

    Lifecycle::

        orchestrator.build()   → assembles layers, runs pipeline
        orchestrator.apply()   → writes to qutebrowser config API
        orchestrator.reload()  → hot-reload (re-runs build + apply)
    """

    def __init__(
        self,
        stack:        LayerStack,
        router:       MessageRouter,
        lifecycle:    LifecycleManager,
        fsm:          ConfigStateMachine,
        policy_chain: Optional[PolicyChain] = None,
    ) -> None:
        self._stack     = stack
        self._router    = router
        self._lifecycle = lifecycle
        self._fsm       = fsm
        self._policy    = policy_chain or PolicyChain()
        self._resolved: Optional[Dict[str, ConfigPacket]] = None
        self._applier:  Optional[ConfigApplier] = None

        # Wire FSM transition log observer
        self._fsm.on_transition(self._on_state_transition)

    # ── Phase 1: Build ─────────────────────────────────────────────────

    def build(self) -> Dict[str, ConfigPacket]:
        """
        Resolve all layers into a merged config.

        FSM path: IDLE → LOADING → VALIDATING → APPLYING
        """
        logger.info("[Orchestrator] build() starting")
        self._fsm.send(ConfigEvent.START_LOAD)

        try:
            self._lifecycle.run(LifecycleHook.PRE_INIT)
            self._resolved = self._stack.resolve()
            self._fsm.send(ConfigEvent.LOAD_DONE)
        except Exception as exc:
            logger.exception("[Orchestrator] build() failed")
            self._fsm.send(ConfigEvent.LOAD_FAILED)
            self._router.emit(ConfigErrorEvent(error_msg=str(exc), layer_name="stack"))
            raise

        self._fsm.send(ConfigEvent.VALIDATE_DONE)
        self._lifecycle.run(LifecycleHook.POST_INIT)

        merged  = self._stack.merged
        n_sets  = len(merged.get("settings", {}))
        n_binds = len(merged.get("keybindings", []))
        n_alias = len(merged.get("aliases", {}))
        logger.info(
            "[Orchestrator] build() complete: %d layers  "
            "settings=%d  bindings=%d  aliases=%d",
            len(self._resolved), n_sets, n_binds, n_alias,
        )
        return self._resolved

    # ── Phase 2: Apply ─────────────────────────────────────────────────

    def apply(self, applier: ConfigApplier) -> List[str]:
        """
        Write the resolved config to qutebrowser.

        Must be called after ``build()``.  The FSM is expected to already be
        in the APPLYING state (set by ``build()`` via VALIDATE_DONE).
        FSM exits to ACTIVE on success or ERROR on failure.

        NOTE: APPLY_START is intentionally NOT sent here.  The FSM enters
        APPLYING during build(); sending APPLY_START from inside APPLYING
        had no defined transition and produced a spurious WARNING in the log.
        """
        if self._resolved is None:
            raise RuntimeError("call build() before apply()")

        self._applier = applier
        all_errors: List[str] = []

        try:
            self._lifecycle.run(LifecycleHook.PRE_APPLY)

            merged = self._stack.merged

            # 1. Flat settings (key → value)
            settings = merged.get("settings", {})
            all_errors.extend(applier.apply_settings(settings))

            # 2. Keybindings (accumulated across all layers)
            keybindings = merged.get("keybindings", [])
            all_errors.extend(applier.apply_keybindings(keybindings))

            # 3. Aliases
            aliases = merged.get("aliases", {})
            all_errors.extend(applier.apply_aliases(aliases))

            # 4. Per-layer events (for subscribers / logging)
            for layer_name, packet in self._resolved.items():
                self._router.emit(LayerAppliedEvent(
                    layer_name=layer_name,
                    key_count=len(packet.data.get("settings", packet.data)),
                ))

            self._lifecycle.run(LifecycleHook.POST_APPLY)

            if all_errors:
                self._fsm.send(ConfigEvent.APPLY_FAIL)
                for err in all_errors:
                    self._router.emit(ConfigErrorEvent(error_msg=err))
            else:
                self._fsm.send(ConfigEvent.APPLY_DONE)

        except Exception as exc:
            logger.exception("[Orchestrator] apply() failed")
            self._fsm.send(ConfigEvent.APPLY_FAIL)
            all_errors.append(str(exc))

        logger.info("[Orchestrator] apply() done: %d error(s)", len(all_errors))
        return all_errors

    # ── Phase 3: Host Policies ─────────────────────────────────────────

    def apply_host_policies(self, applier: ConfigApplier) -> List[str]:
        """
        Apply per-host configuration overrides from BehaviorLayer.
        Called after the main ``apply()`` pass.
        """
        from layers.behavior import BehaviorLayer

        behavior = self._stack.get("behavior")
        if not isinstance(behavior, BehaviorLayer):
            return []

        all_errors: List[str] = []
        for policy in behavior.host_policies():
            errors = applier.apply_host_policy(policy.pattern, policy.settings)
            all_errors.extend(errors)
            if not errors:
                logger.info(
                    "[Orchestrator] host-policy applied: %s  (%s)",
                    policy.pattern, policy.description,
                )
        return all_errors

    # ── Hot reload ─────────────────────────────────────────────────────

    def reload(self, applier: Optional[ConfigApplier] = None) -> List[str]:
        """Hot-reload: re-build and re-apply the full config."""
        self._fsm.send(ConfigEvent.RELOAD)
        self._lifecycle.run(LifecycleHook.PRE_RELOAD)
        self.build()
        errors = self.apply(applier or self._applier)
        self._lifecycle.run(LifecycleHook.POST_RELOAD)
        return errors

    # ── Introspection ──────────────────────────────────────────────────

    def summary(self) -> str:
        merged  = self._stack.merged if self._resolved else {}
        n_sets  = len(merged.get("settings", {}))
        n_binds = len(merged.get("keybindings", []))
        n_alias = len(merged.get("aliases", {}))

        lines = [
            "─" * 60,
            "ConfigOrchestrator Summary",
            "─" * 60,
            self._stack.summary(),
            f"\nFSM: {self._fsm}",
        ]
        if self._resolved:
            lines.append(
                f"\nMerged: {n_sets} settings  "
                f"{n_binds} keybindings  {n_alias} aliases"
            )
        return "\n".join(lines)

    # ── Private ────────────────────────────────────────────────────────

    def _on_state_transition(
        self,
        from_state: ConfigState,
        to_state:   ConfigState,
        event:      ConfigEvent,
    ) -> None:
        logger.info(
            "[Orchestrator/FSM] %s → %s  (event=%s)",
            from_state.name, to_state.name, event.name,
        )
