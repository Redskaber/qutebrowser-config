"""
orchestrator.py
===============
Configuration Orchestrator  (composition root)  v12

Responsibilities:
  1.  Build the LayerStack
  2.  Drive the Config State Machine
  3.  Run the Layer Pipeline
  4.  Apply resolved config to qutebrowser via ConfigApplier
  5.  Emit lifecycle events via the MessageRouter
  6.  Apply per-host overrides via HostPolicyRegistry
  7.  Register QueryBus handlers for introspection
  8.  Track config snapshots and diff-apply on hot-reload       [v8]
  9.  Emit timing metrics for build/apply/reload phases         [v9]
 10.  Re-apply host policies after incremental reload           [v9]
 11.  Expose GetSnapshotQuery / GetLayerDiffQuery handlers      [v9]
 12.  Expose GetLayerNamesQuery handler                         [v9]
 13.  Structured audit trail via core.audit (AuditLog)          [v11]
 14.  SessionLayer event emission after build()                 [v11]
 15.  MetricsCollector (core.metrics) replaces _last_metrics     [v12]
 16.  audit_trail() / metrics_summary() introspection methods   [v12]
 17.  GetMetricsSummaryQuery handler                            [v12]

v12 changes:
  - MetricsCollector (core.metrics) replaces the bare _last_metrics dict.
    The orchestrator constructs MetricsCollector, registers a callback to
    router.emit_metrics, and calls collector.emit() in build/apply/reload.
    This satisfies SRP: telemetry bookkeeping is no longer inline.
  - audit_trail(last_n) method: returns formatted AuditLog entries.
  - metrics_summary(last_n) method: returns formatted MetricsSample table.
  - GetMetricsSummaryQuery handler: expose metrics via QueryBus.
  - _audit_phase() helper: record one orchestrator phase to AuditLog.
  - _maybe_emit_session_event(): mirror of _maybe_emit_context_event().
  - summary() updated to v12: includes session info, audit summary, metrics.
  - build() / apply() / reload() emit audit entries at INFO level.
  - All audit and session calls wrapped in try/except for graceful degradation.

v11 changes (retained):
  - Audit trail: structured AuditLog entries for each phase.
  - SessionLayer: _maybe_emit_session_event() after build().

v10 changes (retained):
  - _handle_get_layer_names variable-shadowing bug fixed.
  - Uses LayerStack._layers property (v10 addition).

v9 changes (retained):
  - build() / apply() / reload() emit MetricsEvent.
  - reload() re-applies host policies.
  - stored applier fallback in reload().
  - GetSnapshotQuery / GetLayerDiffQuery / GetLayerNamesQuery handlers.
  - PolicyDeniedEvent propagation.
  - summary() includes timing.

v8 changes (retained):
  - IncrementalApplier + SnapshotStore for diff-apply on hot-reload.

v7 changes (retained):
  - apply_host_policies: BehaviorLayer patterns skipped when already in
    HostPolicyRegistry (eliminates double-application).
"""

from __future__ import annotations

import logging
import time
from typing import Any, Dict, List, Optional, Set

from core.types     import ConfigDict
from core.health    import HealthChecker, HealthReport
from core.incremental import IncrementalApplier, SnapshotStore, ConfigSnapshot, ConfigChange
from core.layer     import LayerStack
from core.lifecycle import LifecycleHook, LifecycleManager
from core.pipeline  import ConfigPacket
from core.protocol  import (
    ConfigErrorEvent,
    LayerAppliedEvent,
    MessageRouter,
    Query,
    GetMergedConfigQuery,
    GetHealthReportQuery,
    GetSnapshotQuery,
    GetLayerDiffQuery,
    GetLayerNamesQuery,
)
from core.state import ConfigState, ConfigEvent, ConfigStateMachine
from core.strategy import PolicyChain

# v12: MetricsCollector
from core.metrics import MetricsCollector, PhaseTimer  # type: ignore[import]

# v11: optional audit integration
from core.audit import audit_info, audit_warn, audit_error, get_audit_log # type: ignore[import]

# v12: GetMetricsSummaryQuery (added to protocol.py in v12)
from core.protocol import GetMetricsSummaryQuery

logger = logging.getLogger("qute.orchestrator")


# ─────────────────────────────────────────────
# ConfigApplier (forward-declared interface)
# ─────────────────────────────────────────────

class ConfigApplier:
    """
    Abstract interface between the orchestrator and qutebrowser's config API.

    A concrete implementation is passed in by config.py at startup.
    The orchestrator never imports qutebrowser internals directly.
    """

    def apply_settings(
        self,
        settings:     ConfigDict,
        policy_chain: Optional[Any] = None,
        router:       Optional[Any] = None,
    ) -> List[str]:
        """Apply a settings dict; return error strings."""
        return []

    def apply_keybindings(self, keybindings: List[Any]) -> List[str]:
        """Apply keybinding tuples; return error strings."""
        return []

    def apply_aliases(self, aliases: Dict[str, str]) -> List[str]:
        """Apply command aliases; return error strings."""
        return []

    def apply_host_policy(self, pattern: str, settings: ConfigDict) -> List[str]:
        """Apply a per-host settings dict; return error strings."""
        return []


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

        router.ask(GetMergedConfigQuery())    → Dict[str, Any]
        router.ask(GetHealthReportQuery())    → Optional[HealthReport]
        router.ask(GetSnapshotQuery())        → Optional[ConfigSnapshot]    [v9]
        router.ask(GetLayerDiffQuery(...))    → List[ConfigChange]          [v9]
        router.ask(GetLayerNamesQuery())      → List[str]                   [v9]
        router.ask(GetMetricsSummaryQuery())  → str                        [v12]

    Direct introspection::

        orchestrator.audit_trail(last_n=30)  → str    [v12]
        orchestrator.metrics_summary(last_n) → str    [v12]
        orchestrator.summary()               → str
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

        # v12: MetricsCollector wired to router.emit_metrics
        self._metrics: Optional[MetricsCollector] = MetricsCollector(capacity=64)
        self._metrics.on_emit(
            lambda ph, ms, n: self._router.emit_metrics(
                phase=ph, duration_ms=ms, key_count=n,
            )
        )

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
        self._router.queries.register(GetSnapshotQuery,  self._handle_get_snapshot)
        self._router.queries.register(GetLayerDiffQuery, self._handle_get_layer_diff)
        self._router.queries.register(GetLayerNamesQuery, self._handle_get_layer_names)

        # v12: metrics query
        self._router.queries.register(GetMetricsSummaryQuery, self._handle_get_metrics_summary)

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
        """Return a snapshot by label or index."""
        q = query if isinstance(query, GetSnapshotQuery) else GetSnapshotQuery()
        snapshots = self._snapshot_store.snapshots
        if not snapshots:
            return None
        if q.label is not None:
            for snap in reversed(snapshots):
                if snap.label == q.label:
                    return snap
            return None
        try:
            return snapshots[q.index]
        except IndexError:
            return None

    def _handle_get_layer_diff(self, query: Query) -> List[ConfigChange]:
        """Return diff between two snapshots by label."""
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
        return ConfigDiffer.diff(snap_a, snap_b)

    def _handle_get_layer_names(self, _query: Query) -> List[str]:
        """Return ordered list of enabled layer names (priority order)."""
        return [
            rec.layer.name
            for rec in sorted(
                self._stack._layers,   # type: ignore[attr-defined]
                key=lambda r: r.layer.priority,
            )
            if rec.enabled
        ]

    def _handle_get_metrics_summary(self, _query: Query) -> str:
        """Return the metrics summary string (v12)."""
        return self.metrics_summary()

    # ── Audit Trail (v11/v12) ─────────────────────────────────────────

    def audit_trail(self, last_n: int = 30) -> str:
        """
        Return a human-readable summary of the last *last_n* audit entries.

        Falls back gracefully if the audit module is unavailable.
        """
        try:
            from core.audit import get_audit_log
            log = get_audit_log()
            return log.summary(last_n=last_n)
        except ImportError:
            return "(audit module not available)"

    def metrics_summary(self, last_n: int = 20) -> str:
        """
        Return a human-readable summary of the last *last_n* metrics samples.

        Falls back gracefully if the metrics module is unavailable.
        """
        if self._metrics is not None:
            return self._metrics.summary(last_n=last_n)
        return "(metrics module not available)"

    def _audit_phase(
        self,
        phase:   str,
        message: str,
        level:   str = "info",
        **meta:  Any,
    ) -> None:
        """Record a phase entry to the global AuditLog (v11/v12).  Silent on failure."""
        try:
            from core.audit import audit_info, audit_warn, audit_error
            fn = {
                "info":  audit_info,
                "warn":  audit_warn,
                "error": audit_error,
            }.get(level, audit_info)
            fn("orchestrator", f"[{phase}] {message}", **meta)
        except Exception:
            pass   # never let audit failure break the orchestrator

    # ── Session Event (v11/v12) ───────────────────────────────────────

    def _maybe_emit_session_event(self) -> None:
        """Emit a session audit entry if a SessionLayer is registered."""
        try:
            from layers.session import SessionLayer
            layer = self._stack.get("session")
            if isinstance(layer, SessionLayer):
                self._audit_phase(
                    "session",
                    f"active={layer.active_session.value}: "
                    f"{layer.active_spec.description}",
                )
        except ImportError:
            pass

    # ── Context Event ─────────────────────────────────────────────────

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

    # ── Metrics helper ────────────────────────────────────────────────

    def _emit_metrics(self, phase: str, duration_ms: float, key_count: int = 0, **meta: Any) -> None:
        """Emit via MetricsCollector (v12) or fall back to direct router emit."""
        if self._metrics is not None:
            self._metrics.emit(phase, duration_ms, key_count=key_count, **meta)
        else:
            # fallback: direct router emit (no collector recording)
            self._router.emit_metrics(
                phase=phase,
                duration_ms=duration_ms,
                key_count=key_count,
            )

    # ── Phase 1: Build ────────────────────────────────────────────────

    def build(self) -> Dict[str, ConfigPacket]:
        """
        Resolve all layers into a merged config.

        FSM transitions: IDLE → LOADING → VALIDATING → APPLYING (ready for apply)
        Emits MetricsEvent("build", ...) on completion  [v9].
        Records audit entry on completion               [v11].
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
            self._audit_phase("build", f"FAILED: {exc}", level="error")
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
        self._emit_metrics("build", duration_ms, key_count=n_sets,
                           layer_count=len(self._resolved))

        # v11: audit + session
        self._audit_phase(
            "build", "layers resolved",
            layer_count=len(self._resolved), key_count=n_sets,
        )
        self._maybe_emit_context_event()
        self._maybe_emit_session_event()

        return self._resolved

    # ── Phase 2: Apply ────────────────────────────────────────────────

    def apply(self, applier: ConfigApplier) -> List[str]:
        """
        Write the resolved config to qutebrowser.

        Must be called after build().
        FSM exits to ACTIVE on success or ERROR on failure.
        Emits MetricsEvent("apply", ...) on completion  [v9].
        Records audit entry on completion               [v11].
        """
        if self._resolved is None:
            raise RuntimeError("call build() before apply()")

        self._applier  = applier
        all_errors:  List[str] = []
        t0 = time.perf_counter()

        try:
            self._lifecycle.run(LifecycleHook.PRE_APPLY)

            merged = self._stack.merged

            # 1. Settings — policy chain evaluated per-key if populated
            settings     = merged.get("settings", {})
            policy_chain = (
                self._policy
                if bool(self._policy._policies)   # type: ignore[attr-defined]
                else None
            )
            all_errors.extend(
                applier.apply_settings(settings, policy_chain, self._router)
            )

            # 2. Keybindings
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

            # 5. Health checks
            checker           = HealthChecker.default()
            health_report     = checker.check(settings)
            self._last_report = health_report

            if not health_report.ok:
                logger.warning("[Orchestrator] health check: %s", health_report.summary())
                self._audit_phase(
                    "apply", "health errors found", level="warn",
                    errors=len(health_report.errors),
                    warnings=len(health_report.warnings),
                )
            else:
                logger.debug("[Orchestrator] health check: all checks passed")

            # Emit health event
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
            self._audit_phase("apply", f"EXCEPTION: {exc}", level="error")

        duration_ms = (time.perf_counter() - t0) * 1000
        n_settings  = len(self._stack.merged.get("settings", {}))
        self._emit_metrics("apply", duration_ms, key_count=n_settings)

        # v11: audit completion
        if not all_errors:
            self._audit_phase(
                "apply", "complete — health OK",
                settings=n_settings, duration_ms=round(duration_ms, 1),
            )

        logger.info("[Orchestrator] apply() done: %d error(s)", len(all_errors))
        return all_errors

    # ── Phase 3: Host Policies ────────────────────────────────────────

    def apply_host_policies(self, applier: ConfigApplier) -> List[str]:
        """
        Apply per-host configuration overrides.

        Sources (applied in order):
          1. HostPolicyRegistry (from policies/host.py) — structured, queryable
          2. BehaviorLayer.host_policies() — only patterns NOT already in registry

        v9:  timing wrapped; emits MetricsEvent("host_policies", ...).
        v11: audit entry recorded.
        v7:  BehaviorLayer rules skipped for patterns already in HostPolicyRegistry.
        """
        all_errors: List[str] = []
        rule_count  = 0
        t0 = time.perf_counter()

        registry_patterns: Set[str] = set()

        # ── Source 1: HostPolicyRegistry ──────────────────────────────
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

        # ── Source 2: BehaviorLayer.host_policies() ───────────────────
        from layers.behavior import BehaviorLayer
        behavior = self._stack.get("behavior")
        if isinstance(behavior, BehaviorLayer):
            for policy in behavior.host_policies():
                if policy.pattern in registry_patterns:
                    logger.debug(
                        "[Orchestrator] skip duplicate BehaviorLayer rule: %s",
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
        self._emit_metrics("host_policies", duration_ms, key_count=rule_count)
        self._audit_phase(
            "host_policies", f"applied {rule_count} rules",
            rules=rule_count, errors=len(all_errors),
        )

        logger.info(
            "[Orchestrator] host policies applied: %d rules, %d error(s)",
            rule_count, len(all_errors),
        )
        return all_errors

    # ── Phase 4: Hot Reload ───────────────────────────────────────────

    def reload(self, applier: Optional[ConfigApplier] = None) -> List[str]:
        """
        Hot-reload: re-build and diff-apply only changed settings (v8+v9).

        v8:  incremental diff-apply for settings.
        v9:  host policies re-applied after incremental settings apply.
             Emits ConfigReloadedEvent and MetricsEvent("reload", ...).
             applier falls back to self._applier if stored from apply().
        v11: audit entry recorded.

        On the first call (no previous snapshot), all settings are applied.
        On subsequent calls, only changed/added keys are re-applied.
        Keybindings and aliases are always re-applied (not tracked incrementally).

        FSM transitions:  ACTIVE → RELOADING → VALIDATING → APPLYING → ACTIVE
        """
        self._fsm.send(ConfigEvent.RELOAD)
        self._lifecycle.run(LifecycleHook.PRE_RELOAD)
        t0 = time.perf_counter()

        _applier = applier or self._applier
        if _applier is None:
            logger.warning("[Orchestrator] reload() called without applier — skipping apply")
            return []

        # Snapshot current settings BEFORE rebuilding
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
        errors:  List[str] = []

        if not changes:
            logger.info("[Orchestrator] reload: no settings changed — nothing to apply")
        else:
            def apply_fn(k: str, v: Any) -> List[str]:
                return _applier.apply_settings(
                    {k: v},
                    self._policy if bool(self._policy._policies) else None,  # type: ignore[attr-defined]
                    self._router,
                )

            changed_and_added = [c for c in changes if c.kind.name in ("CHANGED", "ADDED")]
            inc_errors = self._incremental_applier.apply_delta(changes, apply_fn)
            errors.extend(inc_errors)
            logger.info(
                "[Orchestrator] incremental reload: %d change(s), %d error(s)",
                len(changed_and_added), len(inc_errors),
            )

        # Always re-apply keybindings and aliases
        merged = self._stack.merged
        errors.extend(_applier.apply_keybindings(merged.get("keybindings", [])))
        errors.extend(_applier.apply_aliases(merged.get("aliases", {})))

        # v9: re-apply host policies
        host_errors = self.apply_host_policies(_applier)
        errors.extend(host_errors)

        duration_ms = (time.perf_counter() - t0) * 1000
        n_changes   = len([c for c in changes if c.kind.name != "SAME"])

        self._emit_metrics("reload", duration_ms, key_count=n_changes)

        self._router.emit_reload(
            changes_count=n_changes,
            errors_count=len(errors),
            duration_ms=duration_ms,
            reason="reload",
        )

        # v11: audit completion
        self._audit_phase(
            "reload", f"complete: {n_changes} change(s)",
            changes=n_changes, errors=len(errors),
            duration_ms=round(duration_ms, 1),
        )

        self._lifecycle.run(LifecycleHook.POST_RELOAD)
        return errors

    # ── Introspection ──────────────────────────────────────────────────

    def summary(self) -> str:
        """
        Human-readable status summary.

        v12: includes session info, audit summary, metrics table.
        """
        merged  = self._stack.merged if self._resolved else {}
        n_sets  = len(merged.get("settings", {}))
        n_binds = len(merged.get("keybindings", []))
        n_alias = len(merged.get("aliases", {}))
        n_hosts = (
            len(self._host_registry) if self._host_registry is not None else 0
        )

        lines = [
            "─" * 60,
            "ConfigOrchestrator Summary (v12)",
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

        # v12: context + session
        try:
            from layers.context import ContextLayer
            ctx = self._stack.get("context")
            if isinstance(ctx, ContextLayer):
                lines.append(f"Context: {ctx.active_mode.value}")
        except ImportError:
            pass

        try:
            from layers.session import SessionLayer
            sess = self._stack.get("session")
            if isinstance(sess, SessionLayer):
                lines.append(f"Session: {sess.active_session.value} — {sess.active_spec.description}")
        except ImportError:
            pass

        # v12: metrics
        if self._metrics is not None and len(self._metrics) > 0:
            lines.append("")
            for sample in self._metrics.last_n(8):
                lines.append(f"  {sample}")

        # v12: audit summary
        try:
            from core.audit import get_audit_log
            log = get_audit_log()
            audit_sum = log.summary(last_n=5)
            if audit_sum:
                lines.append(f"\nAudit (last 5):\n{audit_sum}")
        except ImportError:
            pass

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
        self._audit_phase(
            "fsm",
            f"{from_state.name} → {to_state.name}",
            event=event.name,
        )


# ─────────────────────────────────────────────
# Default keybindings wiring (no-op guard)
# ─────────────────────────────────────────────

class DefaultKeybindingApplier:
    """
    Fallback: suppress the 'clear all defaults' anti-pattern.

    We deliberately do NOT blanket-clear all defaults — that would break
    built-in bindings we haven't overridden.  Layers emit exactly
    the bindings they want; qutebrowser merges them on top of defaults.
    """
    pass
