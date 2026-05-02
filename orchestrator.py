"""
orchestrator.py
===============
Configuration Orchestrator  (composition root)  v9

Responsibilities:
  1. Build the LayerStack
  2. Drive the Config State Machine
  3. Run the Layer Pipeline
  4. Apply resolved config to qutebrowser via ConfigApplier
  5. Emit lifecycle events via the MessageRouter
  6. Apply per-host overrides via HostPolicyRegistry
  7. Register QueryBus handlers for introspection
  8. Track config snapshots and diff-apply on hot-reload  [v8]
  9. Emit timing metrics for build/apply/reload phases    [v9]
 10. Re-apply host policies after incremental reload      [v9]
 11. Expose GetSnapshotQuery / GetLayerDiffQuery handlers [v9]
 12. Expose GetLayerNamesQuery handler                    [v9]

v9 changes:
  - build() / apply() / reload() wrapped with time.perf_counter()
    and emit MetricsEvent on completion.
  - reload() now re-applies host policies after incremental settings
    apply (previously host rules were skipped on hot-reload).
  - _applier stored before apply(); reload() no longer requires
    the applier argument when one is already stored from apply().
  - New QueryBus handlers:
      GetSnapshotQuery   → Optional[ConfigSnapshot]
      GetLayerDiffQuery  → List[ConfigChange]
      GetLayerNamesQuery → List[str]
  - PolicyChain DENY events now routed through router.emit_policy_denied().
  - apply_settings() propagates denied-key events back to router.
  - summary() includes metrics if available.
  - LifecycleHook.PRE_RELOAD emitted correctly (was missing in v8 edge case).
  - Bug fix: reload() guard for missing snapshot is now defensive — uses
    getattr instead of relying on _stack.merged before build() is called.

v8 changes (retained):
  - reload() uses IncrementalApplier: records a snapshot before and after
    build(), diffs the two, and calls apply_settings() only for changed/added
    keys rather than re-applying the full settings dict on every :config-source.
  - SnapshotStore owned by orchestrator (max_history=10).

v7 changes (retained):
  - apply_host_policies: BehaviorLayer host_policies() skipped for patterns
    already covered by HostPolicyRegistry (eliminates double-application).

Principle: single wiring point, explicit dependency injection.
"""

from __future__ import annotations

import logging
import time
from typing import Any, Dict, List, Optional, Set

from core.layer import LayerStack
from core.lifecycle import LifecycleHook, LifecycleManager
from core.pipeline import ConfigPacket
from core.protocol import (
    ConfigErrorEvent,
    GetHealthReportQuery,
    GetLayerDiffQuery,
    GetLayerNamesQuery,
    GetMergedConfigQuery,
    GetSnapshotQuery,
    HealthReportReadyEvent,
    LayerAppliedEvent,
    MessageRouter,
    Query,
)
from core.state import ConfigEvent, ConfigState, ConfigStateMachine
from core.strategy import PolicyAction, PolicyChain
from core.health import HealthChecker, HealthReport
from core.incremental import ConfigChange, ConfigSnapshot, IncrementalApplier, SnapshotStore

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
        router:       Optional[MessageRouter] = None,
    ) -> List[str]:
        """
        Apply flat key=value settings; return list of error strings.

        If policy_chain is provided, each (key, value) pair is evaluated:
          - ALLOW  → applied as-is
          - MODIFY → modified_value is applied instead
          - WARN   → log warning, apply as-is
          - DENY   → skip key; optionally emit PolicyDeniedEvent via router

        v9: router parameter added so DENY decisions can be observed
        externally without the applier knowing about protocol details.
        """
        errors: List[str] = []
        ctx: ConfigDict   = {}

        for key, value in settings.items():
            applied_value = value

            # ── Policy gate ──────────────────────────────────────────────
            if policy_chain is not None:
                decision = policy_chain.evaluate(key, value, ctx)
                if decision.action == PolicyAction.DENY:
                    logger.debug("[Applier] DENY %s: %s", key, decision.reason)
                    if router is not None:
                        router.emit_policy_denied(
                            key=key,
                            value=value,
                            reason=decision.reason or "policy denied",
                        )
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
            clear_first: reserved for future selective-unbind support.
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

        router.ask(GetMergedConfigQuery())  → Dict[str, Any]
        router.ask(GetHealthReportQuery())  → Optional[HealthReport]
        router.ask(GetSnapshotQuery())      → Optional[ConfigSnapshot]    [v9]
        router.ask(GetLayerDiffQuery(...))  → List[ConfigChange]          [v9]
        router.ask(GetLayerNamesQuery())    → List[str]                   [v9]
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

        # v9: last metrics for summary()
        self._last_metrics: Dict[str, float] = {}

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
        # v9: additional introspection queries
        self._router.queries.register(
            GetSnapshotQuery,
            self._handle_get_snapshot,
        )
        self._router.queries.register(
            GetLayerDiffQuery,
            self._handle_get_layer_diff,
        )
        self._router.queries.register(
            GetLayerNamesQuery,
            self._handle_get_layer_names,
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

    def _handle_get_snapshot(self, query: Query) -> Optional[ConfigSnapshot]:
        """Return a snapshot by label or index (v9)."""
        q = query if isinstance(query, GetSnapshotQuery) else GetSnapshotQuery()
        snapshots = self._snapshot_store.snapshots
        if not snapshots:
            return None
        if q.label is not None:
            for snap in reversed(snapshots):
                if snap.label == q.label:
                    return snap
            return None
        # index-based: -1 = most recent
        try:
            return snapshots[q.index]
        except IndexError:
            return None

    def _handle_get_layer_diff(self, query: Query) -> List[ConfigChange]:
        """Return diff between two snapshots by label (v9)."""
        q = query if isinstance(query, GetLayerDiffQuery) else GetLayerDiffQuery()
        snapshots = self._snapshot_store.snapshots
        snap_a: Optional[ConfigSnapshot] = None
        snap_b: Optional[ConfigSnapshot] = None
        for snap in snapshots:
            if snap.label == q.label_a:
                snap_a = snap
            if snap.label == q.label_b:
                snap_b = snap
        if snap_a is None or snap_b is None:
            return []
        from core.incremental import ConfigDiffer
        return ConfigDiffer.diff(snap_a.data, snap_b.data)

    def _handle_get_layer_names(self, _query: Query) -> List[str]:
        """Return ordered list of layer names (v9)."""
        return [
            layer.name
            for layer in sorted(
                self._stack._layers,
                key=lambda rec: rec.layer.priority,
            )
            if rec.enabled
        ]

    # ── Phase 1: Build ─────────────────────────────────────────────────

    def build(self) -> Dict[str, ConfigPacket]:
        """
        Resolve all layers into a merged config.

        FSM transitions: IDLE → LOADING → VALIDATING → APPLYING (ready for apply)
        Emits MetricsEvent("build", ...) on completion.  [v9]
        """
        self._fsm.send(ConfigEvent.START_LOAD)
        t0 = time.perf_counter()

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

        duration_ms = (time.perf_counter() - t0) * 1000
        self._last_metrics["build_ms"] = duration_ms
        self._router.emit_metrics(
            phase="build",
            duration_ms=duration_ms,
            key_count=n_sets,
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
        Emits MetricsEvent("apply", ...) on completion.  [v9]
        """
        if self._resolved is None:
            raise RuntimeError("call build() before apply()")

        self._applier = applier
        all_errors: List[str] = []
        t0 = time.perf_counter()

        try:
            self._lifecycle.run(LifecycleHook.PRE_APPLY)

            merged = self._stack.merged

            # 1. Settings — policy chain evaluated per-key if populated
            settings     = merged.get("settings", {})
            policy_chain = self._policy if bool(self._policy._policies) else None
            all_errors.extend(
                applier.apply_settings(settings, policy_chain, self._router)
            )

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

        # v9: emit apply metrics
        duration_ms = (time.perf_counter() - t0) * 1000
        self._last_metrics["apply_ms"] = duration_ms
        self._router.emit_metrics(
            phase="apply",
            duration_ms=duration_ms,
            key_count=len(self._stack.merged.get("settings", {})),
        )

        logger.info("[Orchestrator] apply() done: %d error(s)", len(all_errors))
        return all_errors

    # ── Phase 3: Host Policies ─────────────────────────────────────────

    def apply_host_policies(self, applier: ConfigApplier) -> List[str]:
        """
        Apply per-host configuration overrides.

        Sources (applied in order):
          1. HostPolicyRegistry (from policies/host.py) — structured, queryable
          2. BehaviorLayer.host_policies() — only patterns NOT already in registry

        v9: timing wrapped; emits MetricsEvent("host_policies", ...).
        v7: BehaviorLayer rules skipped for patterns already in HostPolicyRegistry.
        """
        all_errors: List[str] = []
        rule_count = 0
        t0 = time.perf_counter()

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

        duration_ms = (time.perf_counter() - t0) * 1000
        self._last_metrics["host_policies_ms"] = duration_ms
        self._router.emit_metrics(
            phase="host_policies",
            duration_ms=duration_ms,
            key_count=rule_count,
        )

        logger.info(
            "[Orchestrator] host policies applied: %d rules, %d error(s)",
            rule_count, len(all_errors),
        )
        return all_errors

    # ── Hot Reload ─────────────────────────────────────────────────────

    def reload(self, applier: Optional[ConfigApplier] = None) -> List[str]:
        """
        Hot-reload: re-build and diff-apply only changed settings (v8+v9).

        v8: incremental diff-apply for settings.
        v9: host policies re-applied after incremental settings apply.
            Emits ConfigReloadedEvent and MetricsEvent("reload", ...).
            applier falls back to self._applier if stored from apply().

        On the first call (no previous snapshot), all settings are applied.
        On subsequent calls, only changed/added keys are re-applied.
        Keybindings and aliases are always re-applied (not tracked incrementally).

        FSM transitions:  ACTIVE → RELOADING → VALIDATING → APPLYING → ACTIVE
        """
        self._fsm.send(ConfigEvent.RELOAD)
        self._lifecycle.run(LifecycleHook.PRE_RELOAD)
        t0 = time.perf_counter()

        # v9: fall back to stored applier from apply()
        _applier = applier or self._applier
        if _applier is None:
            logger.warning("[Orchestrator] reload() called without applier — skipping apply")
            return []

        # Snapshot current settings BEFORE rebuilding
        # v9 fix: guard against _stack.merged being unavailable before first build()
        current_settings: ConfigDict = {}
        try:
            current_settings = dict(self._stack.merged.get("settings", {}))
        except AttributeError:
            pass

        self._incremental_applier.record(current_settings, label="pre-reload")
        self._router.emit_snapshot(
            label="pre-reload",
            key_count=len(current_settings),
            version=len(self._snapshot_store.snapshots),
        )

        # Rebuild layers
        self.build()

        # Snapshot new settings AFTER rebuild
        new_settings: ConfigDict = dict(self._stack.merged.get("settings", {}))
        self._incremental_applier.record(new_settings, label="post-reload")
        self._router.emit_snapshot(
            label="post-reload",
            key_count=len(new_settings),
            version=len(self._snapshot_store.snapshots),
        )

        # Compute delta
        changes = self._incremental_applier.compute_delta()
        errors: List[str] = []

        if not changes:
            logger.info("[Orchestrator] reload: no settings changed — nothing to apply")
        else:
            # Incremental apply: only changed/added keys
            changed_and_added = [
                c for c in changes if c.kind.name in ("CHANGED", "ADDED")
            ]
            inc_errors = self._incremental_applier.apply_delta(
                changes,
                apply_fn=lambda k, v: _applier.apply_settings(
                    {k: v},
                    self._policy if bool(self._policy._policies) else None,
                    self._router,
                ),
            )
            errors.extend(inc_errors)
            logger.info(
                "[Orchestrator] incremental reload: %d change(s), %d error(s)",
                len(changed_and_added),
                len(inc_errors),
            )

        # Always re-apply keybindings and aliases (not tracked incrementally)
        merged = self._stack.merged
        errors.extend(_applier.apply_keybindings(merged.get("keybindings", [])))
        errors.extend(_applier.apply_aliases(merged.get("aliases", {})))

        # v9: re-apply host policies after reload
        host_errors = self.apply_host_policies(_applier)
        errors.extend(host_errors)

        duration_ms = (time.perf_counter() - t0) * 1000
        self._last_metrics["reload_ms"] = duration_ms

        # v9: emit reload completion events
        n_changes = len([c for c in changes if c.kind.name != "SAME"])
        self._router.emit_reload(
            changes_count=n_changes,
            errors_count=len(errors),
            duration_ms=duration_ms,
            reason="reload",
        )
        self._router.emit_metrics(
            phase="reload",
            duration_ms=duration_ms,
            key_count=n_changes,
        )

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
            "ConfigOrchestrator Summary (v9)",
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
            lines.append(
                f"Health: {status}  ({self._last_report.summary().splitlines()[0]})"
            )
        # v9: timing metrics
        if self._last_metrics:
            parts = []
            for phase in ("build", "apply", "host_policies", "reload"):
                key = f"{phase}_ms"
                if key in self._last_metrics:
                    parts.append(f"{phase}={self._last_metrics[key]:.1f}ms")
            if parts:
                lines.append(f"Timing: {', '.join(parts)}")
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
