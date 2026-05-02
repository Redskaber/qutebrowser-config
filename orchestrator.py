"""
orchestrator.py
===============
Configuration Orchestrator  (composition root)  v8

Responsibilities:
  1. Build the LayerStack
  2. Drive the Config State Machine
  3. Run the Layer Pipeline
  4. Apply resolved config to qutebrowser via ConfigApplier
  5. Emit lifecycle events via the MessageRouter
  6. Apply per-host overrides via HostPolicyRegistry
  7. Register QueryBus handlers for introspection
  8. Track config snapshots and diff-apply on hot-reload  [v8]

v8 changes:
  - reload() now uses IncrementalApplier: records a snapshot before and after
    build(), diffs the two, and calls apply_settings() only for changed/added
    keys rather than re-applying the full 227-key settings dict on every
    :config-source.  Removed keys are currently left in-place (qutebrowser
    has no public "unset" API); this matches the previous behaviour.
  - SnapshotStore is owned by the orchestrator (max_history=10).
  - Full apply() path is unchanged — incremental only fires on reload().

v7 changes (retained):
  - apply_host_policies: when HostPolicyRegistry is active, BehaviorLayer
    host_policies() are only applied for patterns NOT already covered by
    the registry.  This eliminates silent double-application of the same
    per-host rules (previously localhost was applied twice).
  - Orchestrator version bumped to v7 (was v5 — inconsistency fixed)
  - summary() now shows host registry details via registry.summary()

v6 / v5 changes (retained):
  - QueryBus handlers for GetMergedConfigQuery and GetHealthReportQuery
  - emit_health() called after HealthChecker.check()
  - ContextSwitchedEvent emitted when ContextLayer is active
  - Cleaner policy_chain presence check using len() / bool()
  - All type annotations tightened for strict-mode

Principle: single wiring point, explicit dependency injection.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional, Set

from core.layer import LayerStack
from core.lifecycle import LifecycleHook, LifecycleManager
from core.pipeline import ConfigPacket
from core.protocol import (
    ConfigErrorEvent,
    GetHealthReportQuery,
    GetMergedConfigQuery,
    HealthReportReadyEvent,
    LayerAppliedEvent,
    MessageRouter,
    Query,
)
from core.state import ConfigEvent, ConfigState, ConfigStateMachine
from core.strategy import PolicyAction, PolicyChain
from core.health import HealthChecker, HealthReport
from core.incremental import IncrementalApplier, SnapshotStore

logger = logging.getLogger("qute.orchestrator")

ConfigDict = Dict[str, Any]


# ─────────────────────────────────────────────
# Config Applier
# ─────────────────────────────────────────────

class ConfigApplier:
    """
    Translates a resolved ConfigDict into qutebrowser config API calls.

    Separated from the orchestrator so it can be replaced / mocked in tests
    without requiring a running qutebrowser instance.
    """

    def __init__(self, config_obj: Any, bindings_obj: Any) -> None:
        """
        Args:
            config_obj:   qutebrowser ``config`` object (.set / .bind)
            bindings_obj: qutebrowser ``c`` object (attribute-style access)
        """
        self._config = config_obj
        self._c      = bindings_obj

    def apply_settings(
        self,
        settings:     ConfigDict,
        policy_chain: Optional[PolicyChain] = None,
    ) -> List[str]:
        """
        Apply flat key=value settings; return list of error strings.

        If policy_chain is provided, each (key, value) pair is evaluated
        before being applied:
          - ALLOW  → applied as-is
          - MODIFY → modified_value is applied instead
          - WARN   → log warning, apply as-is
          - DENY   → skip this key entirely
        """
        errors: List[str] = []
        ctx: ConfigDict = {}

        for key, value in settings.items():
            applied_value = value

            # ── Policy gate ──────────────────────────────────────────────
            if policy_chain is not None:
                decision = policy_chain.evaluate(key, value, ctx)
                if decision.action == PolicyAction.DENY:
                    logger.debug("[Applier] DENY %s: %s", key, decision.reason)
                    continue
                elif decision.action == PolicyAction.MODIFY:
                    applied_value = decision.modified_value
                    logger.debug(
                        "[Applier] MODIFY %s: %r → %r (%s)",
                        key, value, applied_value, decision.reason,
                    )
                elif decision.action == PolicyAction.WARN:
                    logger.warning(
                        "[Applier] WARN %s = %r: %s", key, value, decision.reason
                    )

            # ── Apply ────────────────────────────────────────────────────
            try:
                self._config.set(key, applied_value)
                logger.debug("[Applier] set %s = %r", key, applied_value)
            except Exception as exc:
                msg = f"set {key}: {exc}"
                errors.append(msg)
                logger.error("[Applier] %s", msg)

        return errors

    def apply_keybindings(
        self,
        bindings:    List[tuple],  # type: ignore[type-arg]
        clear_first: bool = True,
    ) -> List[str]:
        """
        Apply keybindings.

        Args:
            bindings:    list of (key, command, mode) or (key, command) tuples.
            clear_first: reserved for future use (selective unbind).
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
        """Apply pattern-scoped settings for a single host rule."""
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

        We deliberately do NOT blanket-clear all defaults — that would break
        built-in bindings we haven't overridden.  Layers emit exactly
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

        orchestrator.build()              → assembles layers, runs pipeline
        orchestrator.apply(applier)       → writes to qutebrowser config API
        orchestrator.apply_host_policies  → pattern-scoped overrides
        orchestrator.reload(applier)      → hot-reload (re-runs build + apply)

    Introspection (via QueryBus)::

        router.ask(GetMergedConfigQuery()) → Dict[str, Any]
        router.ask(GetHealthReportQuery()) → HealthReport
    """

    def __init__(
        self,
        stack:         LayerStack,
        router:        MessageRouter,
        lifecycle:     LifecycleManager,
        fsm:           ConfigStateMachine,
        policy_chain:  Optional[PolicyChain] = None,
        host_registry: Any = None,
    ) -> None:
        self._stack         = stack
        self._router        = router
        self._lifecycle     = lifecycle
        self._fsm           = fsm
        self._policy        = policy_chain or PolicyChain()
        self._host_registry = host_registry
        self._resolved:     Optional[Dict[str, ConfigPacket]] = None
        self._applier:      Optional[ConfigApplier]           = None
        self._last_report:  Optional[HealthReport]            = None

        # v8: Snapshot store for incremental hot-reload
        self._snapshot_store      = SnapshotStore(max_history=10)
        self._incremental_applier = IncrementalApplier(self._snapshot_store)

        # Wire FSM transition observer
        self._fsm.on_transition(self._on_state_transition)

        # Wire QueryBus handlers for introspection
        self._router.queries.register(
            GetMergedConfigQuery,
            self._handle_get_merged_config,
        )
        self._router.queries.register(
            GetHealthReportQuery,
            self._handle_get_health_report,
        )

    # ── QueryBus handlers ──────────────────────────────────────────────

    def _handle_get_merged_config(self, _query: Query) -> ConfigDict:
        """Return the fully-merged settings dict."""
        if not hasattr(self._stack, "_merged"):
            return {}
        return dict(self._stack.merged)

    def _handle_get_health_report(self, _query: Query) -> Optional[HealthReport]:
        """Return the last HealthReport (or None if not yet run)."""
        return self._last_report

    # ── Phase 1: Build ─────────────────────────────────────────────────

    def build(self) -> Dict[str, ConfigPacket]:
        """
        Resolve all layers into a merged config.

        FSM transitions: IDLE → LOADING → VALIDATING → APPLYING (ready for apply)
        """
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

        # Emit context info if ContextLayer is active
        self._maybe_emit_context_event()

        return self._resolved

    def _maybe_emit_context_event(self) -> None:
        """Emit ContextSwitchedEvent if a ContextLayer is registered."""
        try:
            from layers.context import ContextLayer
            from core.protocol import ContextSwitchedEvent
            layer = self._stack.get("context")
            if isinstance(layer, ContextLayer):
                self._router.emit(ContextSwitchedEvent(
                    old_context="default",
                    new_context=layer.active_mode.value,
                ))
        except ImportError:
            pass

    # ── Phase 2: Apply ─────────────────────────────────────────────────

    def apply(self, applier: ConfigApplier) -> List[str]:
        """
        Write the resolved config to qutebrowser.

        Must be called after build().
        FSM exits to ACTIVE on success or ERROR on failure.
        """
        if self._resolved is None:
            raise RuntimeError("call build() before apply()")

        self._applier = applier
        all_errors: List[str] = []

        try:
            self._lifecycle.run(LifecycleHook.PRE_APPLY)

            merged = self._stack.merged

            # 1. Settings — policy chain evaluated per-key if populated
            settings     = merged.get("settings", {})
            policy_chain = self._policy if bool(self._policy._policies) else None
            all_errors.extend(applier.apply_settings(settings, policy_chain))

            # 2. Keybindings (accumulated across all layers)
            keybindings = merged.get("keybindings", [])
            all_errors.extend(applier.apply_keybindings(keybindings))

            # 3. Aliases
            aliases = merged.get("aliases", {})
            all_errors.extend(applier.apply_aliases(aliases))

            # 4. Per-layer applied events
            for layer_name, packet in self._resolved.items():
                self._router.emit(LayerAppliedEvent(
                    layer_name=layer_name,
                    key_count=len(packet.data.get("settings", packet.data)),
                ))

            # 5. Health checks — validate resolved settings
            checker           = HealthChecker.default()
            health_report     = checker.check(settings)
            self._last_report = health_report

            if not health_report.ok:
                logger.warning(
                    "[Orchestrator] health check: %s", health_report.summary()
                )
            else:
                logger.debug("[Orchestrator] health check: all checks passed")

            # Emit health event for subscribers
            self._router.emit_health(
                ok            = health_report.ok,
                error_count   = len(health_report.errors),
                warning_count = len(health_report.warnings),
                info_count    = len(health_report.infos),
            )

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
        Apply per-host configuration overrides.

        Sources (applied in order):
          1. HostPolicyRegistry (from policies/host.py) — structured, queryable
          2. BehaviorLayer.host_policies() — only patterns NOT already in registry

        v7 deduplication fix:
          Previously BehaviorLayer and HostPolicyRegistry both emitted rules for
          the same patterns (e.g. localhost, *.google.com), causing config.set()
          to be called twice for the same key/pattern.  Now BehaviorLayer rules are
          skipped for any pattern already covered by the registry.
        """
        all_errors: List[str] = []
        rule_count = 0

        # Track patterns applied by HostPolicyRegistry so we can skip duplicates
        registry_patterns: Set[str] = set()

        # ── Source 1: HostPolicyRegistry ──────────────────────────────────
        if self._host_registry is not None:
            for rule in self._host_registry.active():
                errors = applier.apply_host_policy(rule.pattern, rule.settings)
                all_errors.extend(errors)
                if not errors:
                    logger.debug(
                        "[Orchestrator] host-registry: %s  (%s)",
                        rule.pattern, rule.description,
                    )
                registry_patterns.add(rule.pattern)
                rule_count += 1

        # ── Source 2: BehaviorLayer.host_policies() ───────────────────────
        # Only apply patterns not already handled by HostPolicyRegistry.
        from layers.behavior import BehaviorLayer
        behavior = self._stack.get("behavior")
        if isinstance(behavior, BehaviorLayer):
            for policy in behavior.host_policies():
                if policy.pattern in registry_patterns:
                    logger.debug(
                        "[Orchestrator] skip duplicate BehaviorLayer rule: %s"
                        " (already in HostPolicyRegistry)",
                        policy.pattern,
                    )
                    continue
                errors = applier.apply_host_policy(policy.pattern, policy.settings)
                all_errors.extend(errors)
                if not errors:
                    logger.info(
                        "[Orchestrator] host-policy (behavior): %s  (%s)",
                        policy.pattern, policy.description,
                    )
                rule_count += 1

        logger.info(
            "[Orchestrator] host policies applied: %d rules, %d error(s)",
            rule_count, len(all_errors),
        )
        return all_errors

    # ── Hot Reload ─────────────────────────────────────────────────────

    def reload(self, applier: Optional[ConfigApplier] = None) -> List[str]:
        """
        Hot-reload: re-build and diff-apply only changed settings (v8).

        On the first call (no previous snapshot), falls back to full apply().
        On subsequent calls, only changed/added keys are re-applied via
        IncrementalApplier — unchanged keys are skipped for performance.

        The FSM transitions:  ACTIVE → RELOADING → VALIDATING → APPLYING → ACTIVE
        """
        self._fsm.send(ConfigEvent.RELOAD)
        self._lifecycle.run(LifecycleHook.PRE_RELOAD)

        _applier = applier or self._applier
        if _applier is None:
            logger.warning("[Orchestrator] reload() called without applier — skipping apply")
            return []

        # Snapshot the current settings before rebuilding
        current_settings: ConfigDict = {}
        if self._resolved is not None:
            current_settings = dict(self._stack.merged.get("settings", {}))
        self._incremental_applier.record(current_settings, label="pre-reload")

        # Rebuild layers
        self.build()

        # Snapshot the new settings
        new_settings: ConfigDict = dict(self._stack.merged.get("settings", {}))
        self._incremental_applier.record(new_settings, label="post-reload")

        # Compute delta
        changes = self._incremental_applier.compute_delta()

        errors: List[str] = []

        if not changes:
            logger.info("[Orchestrator] reload: no settings changed — nothing to apply")
        else:
            # Incremental apply: only changed/added keys
            inc_errors = self._incremental_applier.apply_delta(
                changes,
                apply_fn=lambda k, v: _applier.apply_settings({k: v}, None),
            )
            errors.extend(inc_errors)
            logger.info(
                "[Orchestrator] incremental reload: %d change(s), %d error(s)",
                len([c for c in changes if c.kind.name != "SAME"]),
                len(inc_errors),
            )

        # Always re-apply keybindings and aliases (not tracked incrementally)
        merged = self._stack.merged
        errors.extend(_applier.apply_keybindings(merged.get("keybindings", [])))
        errors.extend(_applier.apply_aliases(merged.get("aliases", {})))

        self._lifecycle.run(LifecycleHook.POST_RELOAD)
        return errors

    # ── Introspection ──────────────────────────────────────────────────

    def summary(self) -> str:
        merged  = self._stack.merged if self._resolved else {}
        n_sets  = len(merged.get("settings", {}))
        n_binds = len(merged.get("keybindings", []))
        n_alias = len(merged.get("aliases", {}))
        n_hosts = (
            len(self._host_registry) if self._host_registry is not None else 0
        )

        lines = [
            "─" * 60,
            "ConfigOrchestrator Summary (v8)",
            "─" * 60,
            self._stack.summary(),
            f"\nFSM: {self._fsm}",
        ]
        if self._resolved:
            lines.append(
                f"\nMerged: {n_sets} settings  "
                f"{n_binds} keybindings  {n_alias} aliases"
            )
        if n_hosts:
            reg_summary = (
                self._host_registry.summary()
                if hasattr(self._host_registry, "summary")
                else str(n_hosts)
            )
            lines.append(f"Host rules: {reg_summary}")
        if self._last_report is not None:
            status = "✓ healthy" if self._last_report.ok else "✗ has errors"
            lines.append(f"Health: {status}  ({self._last_report.summary().splitlines()[0]})")
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
