"""
orchestrator.py
===============
Configuration Orchestrator  (composition root)  v17

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
 15.  MetricsCollector (core.metrics) replaces _last_metrics    [v12]
 16.  audit_trail() / metrics_summary() introspection methods   [v12]
 17.  GetMetricsSummaryQuery handler                            [v12]
 18.  NetworkLayer event emission after build()                 [v15]
 19.  SessionChangedEvent emission (proper, not just audit)     [v15]
 20.  hot_swap property: lazy _WrappedHotSwap                   [v15]
 21.  GetActiveNetworkQuery handler                             [v15]
 22.  GetHotSwapStatusQuery handler                             [v15]
 23.  GetActiveSessionQuery handler                             [v15]
 24.  _active_session / _active_network_mode state tracking     [v16]
 25.  _WrappedHotSwap: capture HotSwapResult; propagate changes [v16]
 26.  _active_context state tracking; accurate old_context      [v17]  ← NEW
 27.  GetActiveContextQuery handler                             [v17]  ← NEW
 28.  ContextSwitchedEvent gains source field; emitted via      [v17]  ← NEW
       router.emit_context_changed() (mirrors session/network)

v17 changes:
  - _active_context: str attribute tracks the last emitted context mode.
    _maybe_emit_context_event() reads it for old_context and updates it
    after emission.  Startup emits old_context="default"; subsequent
    hot-swaps emit the actual previous value.
    Mirrors the v16 fix for _active_session / _active_network_mode.
  - _maybe_emit_context_event() upgraded to use router.emit_context_changed()
    (a convenience helper on MessageRouter, added in v17), passing source=.
    Previously it called router.emit(ContextSwitchedEvent(...)) directly with
    old_context hardcoded to "default" and no source field.
  - GetActiveContextQuery handler added (mirrors GetActiveSessionQuery).
    Returns current context mode name string; "default" if no ContextLayer.
  - _WrappedHotSwap._execute(): when layer_name == "context", emits
    _maybe_emit_context_event(source="hot_swap") after a successful swap,
    mirroring the session/network pattern.
  - summary() bumped to v17.
  - Protocol import: GetActiveContextQuery added.

v16 changes (retained):
  - _active_session: str attribute tracks the last emitted session mode.
    _maybe_emit_session_event() reads it for old_session and updates it
    after emission.  Startup emits old_session="unknown"; subsequent
    hot-swaps emit the actual previous value.
  - _active_network_mode: str attribute mirrors the above for network.
    _maybe_emit_network_event() reads / updates it similarly.
  - _WrappedHotSwap._execute(): fn() return value (HotSwapResult) is now
    captured.  result.changes (int) and result.errors are forwarded to
    HotSwapCompletedEvent and the orchestrator result dict.  Previously
    changes was always an empty list because the lambda returned None.
  - summary() bumped to v16.

v15 changes (retained):
  - _maybe_emit_session_event(): now emits SessionChangedEvent via
    router.emit_session_changed() in addition to the audit entry.
    SessionChangedEvent is a first-class protocol event (mirrors
    ContextSwitchedEvent).  source="startup" on initial build().
  - _maybe_emit_network_event(): new; emits NetworkModeChangedEvent
    when a NetworkLayer is registered.  source="startup" on build().
  - hot_swap property: lazy-constructs _WrappedHotSwap once; returns
    the same instance on subsequent accesses (cached per-instance).
  - _WrappedHotSwap: wraps LayerHotSwap (Open/Closed principle).
    Adds: orchestrator-level audit, HotSwapCompletedEvent emission,
    SessionChangedEvent/NetworkModeChangedEvent emission on relevant
    layer swaps, and _last_hot_swap_result storage.
  - _last_hot_swap_result: stores last HotSwapCompletedEvent as dict.
  - New query handlers registered in __init__:
      GetActiveNetworkQuery  → active content.proxy string
      GetHotSwapStatusQuery  → last hot-swap result dict
      GetActiveSessionQuery  → active session mode name string
  - summary() updated to v15: includes Network line, last hot-swap line.

v12 changes (retained):
  - MetricsCollector (core.metrics) replaces the bare _last_metrics dict.
  - audit_trail(last_n) / metrics_summary(last_n) methods.
  - GetMetricsSummaryQuery handler.
  - _audit_phase() helper.
  - _maybe_emit_session_event() audit entry (now ALSO emits protocol event).
  - summary() updated to v12.

v11 changes (retained):
  - Audit trail: AuditLog entries for each phase.
  - SessionLayer: _maybe_emit_session_event() after build().

v10 changes (retained):
  - _handle_get_layer_names variable-shadowing bug fixed.
  - Uses LayerStack._layers property (v10 addition).
"""

from __future__ import annotations

import logging
import time
from abc    import ABC, abstractmethod
from typing import Any, Dict, List, Optional, Set

from core.types       import ConfigDict
from core.health      import HealthChecker, HealthReport
from core.incremental import IncrementalApplier, SnapshotStore, ConfigSnapshot, ConfigChange
from core.layer       import LayerStack
from core.lifecycle   import LifecycleHook, LifecycleManager
from core.pipeline    import ConfigPacket
from core.protocol    import (
    ConfigErrorEvent,
    LayerAppliedEvent,
    MessageRouter,
    Query,
    GetMergedConfigQuery,
    GetHealthReportQuery,
    GetSnapshotQuery,
    GetLayerDiffQuery,
    GetLayerNamesQuery,
    GetMetricsSummaryQuery,
    # v15 queries
    GetActiveNetworkQuery,
    GetHotSwapStatusQuery,
    GetActiveSessionQuery,
    # v17 query
    GetActiveContextQuery,
)
from core.state       import ConfigState, ConfigEvent, ConfigStateMachine
from core.strategy    import PolicyChain

# v12: MetricsCollector
from core.metrics import MetricsCollector

# v11: audit integration
from core.audit import audit_info, audit_warn, audit_error, get_audit_log

# v13: hot-swap
from core.hot_swap import LayerHotSwap

logger = logging.getLogger("qute.orchestrator")


# ─────────────────────────────────────────────
# ConfigApplier (forward-declared interface)
# ─────────────────────────────────────────────

class ConfigApplier(ABC):
    """
    Abstract interface between the orchestrator and qutebrowser's config API.

    A concrete implementation is passed in by config.py at startup.
    The orchestrator never imports qutebrowser internals directly.
    """

    @abstractmethod
    def apply_settings(
        self,
        settings:     ConfigDict,
        policy_chain: Optional[Any] = None,
        router:       Optional[Any] = None,
    ) -> List[str]:
        """Apply a settings dict; return error strings."""
        ...

    @abstractmethod
    def apply_keybindings(self, keybindings: List[Any]) -> List[str]:
        """Apply keybinding tuples; return error strings."""
        ...

    @abstractmethod
    def apply_aliases(self, aliases: Dict[str, str]) -> List[str]:
        """Apply command aliases; return error strings."""
        ...

    @abstractmethod
    def apply_host_policy(self, pattern: str, settings: ConfigDict) -> List[str]:
        """Apply a per-host settings dict; return error strings."""
        ...


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

        router.ask(GetMergedConfigQuery())      → Dict[str, Any]
        router.ask(GetHealthReportQuery())      → Optional[HealthReport]
        router.ask(GetSnapshotQuery())          → Optional[ConfigSnapshot]    [v9]
        router.ask(GetLayerDiffQuery(...))      → List[ConfigChange]          [v9]
        router.ask(GetLayerNamesQuery())        → List[str]                   [v9]
        router.ask(GetMetricsSummaryQuery())    → str                        [v12]
        router.ask(GetActiveNetworkQuery())     → str                        [v15]
        router.ask(GetHotSwapStatusQuery())     → Dict[str, Any]             [v15]
        router.ask(GetActiveSessionQuery())     → str                        [v15]

    Direct introspection::

        orchestrator.audit_trail(last_n=30)  → str    [v12]
        orchestrator.metrics_summary(last_n) → str    [v12]
        orchestrator.summary()               → str

    Hot-swap (v15)::

        orchestrator.hot_swap.swap(name, new_layer)   → None
        orchestrator.hot_swap.remove(name)            → None
        orchestrator.hot_swap.insert(new_layer)       → None
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

        # v15: hot-swap wrapper (lazy-init)
        self._hot_swap_wrapper: Optional["_WrappedHotSwap"] = None

        # v15: last hot-swap result for introspection
        self._last_hot_swap_result: Dict[str, Any] = {}

        # v16: track active session/network for accurate old_* in events
        self._active_session:      str = "unknown"
        self._active_network_mode: str = "unknown"

        # v17: track active context for accurate old_context in ContextSwitchedEvent
        self._active_context: str = "default"

        # v8: Snapshot store for incremental hot-reload
        self._snapshot_store      = SnapshotStore(max_history=10)
        self._incremental_applier = IncrementalApplier(self._snapshot_store)

        # v12: MetricsCollector wired to router.emit_metrics
        self._metrics: Optional[MetricsCollector] = MetricsCollector(capacity=64)

        def _on_metrics_emit(phase: str, duration_ms: float, key_count: int) -> None:
            self._router.emit_metrics(phase=phase, duration_ms=duration_ms, key_count=key_count)

        self._metrics.on_emit(_on_metrics_emit)

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
        self._router.queries.register(GetSnapshotQuery,   self._handle_get_snapshot)
        self._router.queries.register(GetLayerDiffQuery,  self._handle_get_layer_diff)
        self._router.queries.register(GetLayerNamesQuery, self._handle_get_layer_names)

        # v12: metrics query
        self._router.queries.register(GetMetricsSummaryQuery, self._handle_get_metrics_summary)

        # v15: new queries
        self._router.queries.register(GetActiveNetworkQuery,  self._handle_get_active_network)
        self._router.queries.register(GetHotSwapStatusQuery,  self._handle_get_hot_swap_status)
        self._router.queries.register(GetActiveSessionQuery,  self._handle_get_active_session)

        # v17: context query
        self._router.queries.register(GetActiveContextQuery,  self._handle_get_active_context)

    # ── hot_swap property (v15) ────────────────────────────────────────

    @property
    def hot_swap(self) -> "_WrappedHotSwap":
        """
        Lazy-initialised hot-swap controller for this orchestrator.

        Wraps LayerHotSwap with orchestrator-level audit, event emission,
        and result storage (Open/Closed principle — LayerHotSwap is
        not modified).

        Usage::

            orchestrator.hot_swap.swap("network", new_network_layer)
            orchestrator.hot_swap.remove("context")
            orchestrator.hot_swap.insert(new_layer)

        Raises RuntimeError if LayerHotSwap is not available (import error).
        """
        if self._hot_swap_wrapper is None:
            self._hot_swap_wrapper = _WrappedHotSwap(self)
        return self._hot_swap_wrapper

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
                self._stack._layers, # type: ignore[protect]
                key=lambda r: r.layer.priority,
            )
            if rec.enabled
        ]

    def _handle_get_metrics_summary(self, _query: Query) -> str:
        """Return the metrics summary string (v12)."""
        return self.metrics_summary()

    def _handle_get_active_network(self, _query: Query) -> str:
        """
        Return the currently active content.proxy string.  ← v15

        Inspects the resolved merged settings first, then the NetworkLayer
        directly as fallback.  Returns "system" if NetworkLayer is absent.
        """
        # 1. Resolved merged settings (most authoritative)
        if self._resolved is not None:
            merged = self._stack.merged
            proxy = merged.get("settings", {}).get("content.proxy")
            if proxy is not None:
                return str(proxy)

        # 2. NetworkLayer active spec
        try:
            from layers.network import NetworkLayer
            layer = self._stack.get("network")
            if isinstance(layer, NetworkLayer):
                return layer.active_spec.proxy
        except ImportError:
            pass

        return "system"

    def _handle_get_hot_swap_status(self, _query: Query) -> Dict[str, Any]:
        """
        Return the last hot-swap result as a Dict[str, Any].  ← v15

        Keys: operation, layer_name, ok, errors, duration_ms.
        Returns {} if no hot-swap has been performed yet.
        """
        return dict(self._last_hot_swap_result)

    def _handle_get_active_session(self, _query: Query) -> str:
        """
        Return the current session mode name string.  ← v15

        Returns "unknown" if no SessionLayer is registered.
        """
        try:
            from layers.session import SessionLayer
            layer = self._stack.get("session")
            if isinstance(layer, SessionLayer):
                return layer.active_session.value
        except ImportError:
            pass
        return "unknown"

    def _handle_get_active_context(self, _query: Query) -> str:
        """
        Return the current context mode name string.  ← v17

        Mirrors _handle_get_active_session for the context subsystem.
        Returns "default" if no ContextLayer is registered.
        """
        try:
            from layers.context import ContextLayer
            layer = self._stack.get("context")
            if isinstance(layer, ContextLayer):
                return layer.active_mode.value
        except ImportError:
            pass
        return "default"

    # ── Audit Trail (v11/v12) ─────────────────────────────────────────

    def audit_trail(self, last_n: int = 30) -> str:
        """
        Return a human-readable summary of the last *last_n* audit entries.

        Falls back gracefully if the audit module is unavailable.
        """
        try:
            log = get_audit_log()
            return log.summary(last_n=last_n)
        except Exception:
            return "(audit log unavailable)"

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
            fn = {
                "info":  audit_info,
                "warn":  audit_warn,
                "error": audit_error,
            }.get(level, audit_info)
            fn("orchestrator", f"[{phase}] {message}", **meta)
        except Exception:
            pass   # never let audit failure break the orchestrator

    # ── Session Event (v15: now emits proper protocol event) ──────────

    def _maybe_emit_session_event(self, source: str = "startup") -> None:
        """
        Emit SessionChangedEvent and audit entry if a SessionLayer is registered.

        v15: upgrades from audit-only to full protocol event emission.
        v16: tracks _active_session so old_session reflects the actual
             previous value instead of always being "unknown".
        Subscribable by config.py via router.events.subscribe(SessionChangedEvent, ...).
        """
        try:
            from layers.session import SessionLayer
            layer = self._stack.get("session")
            if isinstance(layer, SessionLayer):
                mode_name = layer.active_session.value
                self._router.emit_session_changed(
                    old_session=self._active_session,
                    new_session=mode_name,
                    source=source,
                )
                self._active_session = mode_name   # v16: update tracker
                self._audit_phase(
                    "session",
                    f"active={mode_name}: {layer.active_spec.description}",
                )
        except ImportError:
            pass

    # ── Context Event (v17: accurate old_context + source field) ─────────

    def _maybe_emit_context_event(self, source: str = "startup") -> None:
        """
        Emit ContextSwitchedEvent if a ContextLayer is registered.

        v17: upgraded from hardcoded old_context="default" to proper tracking
        via _active_context, mirroring the v16 fix for session/network.
        Now uses router.emit_context_changed() convenience helper (v17).
        source parameter added to ContextSwitchedEvent.
        """
        try:
            from layers.context import ContextLayer
            layer = self._stack.get("context")
            if isinstance(layer, ContextLayer):
                mode_name = layer.active_mode.value
                self._router.emit_context_changed(
                    old_context=self._active_context,
                    new_context=mode_name,
                    source=source,
                )
                self._active_context = mode_name   # v17: update tracker
        except ImportError:
            pass

    # ── Network Event (v15) ───────────────────────────────────────────

    def _maybe_emit_network_event(self, source: str = "startup") -> None:
        """
        Emit NetworkModeChangedEvent if a NetworkLayer is registered.  ← v15

        v16: tracks _active_network_mode so old_mode reflects the actual
             previous value instead of always being "unknown".
        Called after build() and after hot-swap of the network layer.
        """
        try:
            from layers.network import NetworkLayer
            layer = self._stack.get("network")
            if isinstance(layer, NetworkLayer):
                mode_name = layer.active_mode.value
                self._router.emit_network_changed(
                    old_mode=self._active_network_mode,
                    new_mode=mode_name,
                    proxy=layer.active_spec.proxy,
                    source=source,
                )
                self._active_network_mode = mode_name   # v16: update tracker
                self._audit_phase(
                    "network",
                    f"active={mode_name}: {layer.active_spec.description}",
                )
        except ImportError:
            pass

    # ── Metrics helper ─────────────────────────────────────────────────

    def _emit_metrics(
        self,
        phase:      str,
        duration_ms: float,
        key_count:  int = 0,
        **meta:     Any,
    ) -> None:
        """Emit via MetricsCollector (v12) or fall back to direct router emit."""
        if self._metrics is not None:
            self._metrics.emit(phase, duration_ms, key_count=key_count, **meta)
        else:
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
        Emits SessionChangedEvent if SessionLayer present [v15].
        Emits NetworkModeChangedEvent if NetworkLayer present [v15].
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

        self._audit_phase(
            "build", "layers resolved",
            layer_count=len(self._resolved), key_count=n_sets,
        )
        self._maybe_emit_context_event(source="startup")
        self._maybe_emit_session_event(source="startup")   # v15: full event
        self._maybe_emit_network_event(source="startup")   # v15: new

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
            policy_chain = self._policy if bool(self._policy) else None
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
                    self._policy if bool(self._policy) else None,
                    self._router,
                )

            inc_errors = self._incremental_applier.apply_delta(changes, apply_fn)
            errors.extend(inc_errors)
            changed_count = len([c for c in changes if c.kind.name in ("CHANGED", "ADDED")])
            logger.info(
                "[Orchestrator] incremental reload: %d change(s), %d error(s)",
                changed_count, len(inc_errors),
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

        v15: includes Network line, last hot-swap line.
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
            "ConfigOrchestrator Summary (v17)",
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

        # Context
        try:
            from layers.context import ContextLayer
            ctx = self._stack.get("context")
            if isinstance(ctx, ContextLayer):
                lines.append(f"Context: {ctx.active_mode.value}")
        except ImportError:
            pass

        # Session
        try:
            from layers.session import SessionLayer
            sess = self._stack.get("session")
            if isinstance(sess, SessionLayer):
                lines.append(f"Session: {sess.active_session.value} — {sess.active_spec.description}")
        except ImportError:
            pass

        # v15: Network
        try:
            from layers.network import NetworkLayer
            net = self._stack.get("network")
            if isinstance(net, NetworkLayer):
                lines.append(f"Network: {net.active_mode.value} — proxy={net.active_spec.proxy}")
        except ImportError:
            pass

        # v15: Last hot-swap
        if self._last_hot_swap_result:
            hs = self._last_hot_swap_result
            status = "✓" if hs.get("ok") else "✗"
            lines.append(
                f"HotSwap: {status} {hs.get('operation','?')} "
                f"layer={hs.get('layer_name','?')}  "
                f"{hs.get('duration_ms', 0):.1f}ms"
            )

        # v12: metrics
        if self._metrics is not None and len(self._metrics) > 0:
            lines.append("")
            for sample in self._metrics.last_n(8):
                lines.append(f"  {sample}")

        # v12: audit summary
        try:
            log = get_audit_log()
            audit_sum = log.summary(last_n=5)
            if audit_sum:
                lines.append(f"\nAudit (last 5):\n{audit_sum}")
        except Exception:
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
# _WrappedHotSwap  (v15)
# ─────────────────────────────────────────────

class _WrappedHotSwap:
    """
    Orchestrator-level wrapper around LayerHotSwap.

    Applies Open/Closed principle: extends LayerHotSwap without modifying it.
    Adds:
      - Audit entries for each operation
      - HotSwapCompletedEvent emission
      - SessionChangedEvent emission when session layer is swapped
      - NetworkModeChangedEvent emission when network layer is swapped
      - _last_hot_swap_result storage on the orchestrator

    Instantiated lazily via orchestrator.hot_swap property.

    v16 fix: _execute() now captures the HotSwapResult returned by
    LayerHotSwap operations and propagates result.changes and result.errors
    to the event and the stored result dict.  Previously changes was
    always an empty list because the lambda did not forward the return value.
    """

    def __init__(self, orchestrator: ConfigOrchestrator) -> None:
        self._orc  = orchestrator

        # Build a lazy apply_fn that delegates to the stored applier.
        # The applier may not exist yet at construction time (hot_swap
        # can be accessed before apply() is called in tests), so we
        # dereference self._orc._applier at call-time, not at init-time.
        def _lazy_apply_fn(key: str, value: Any) -> List[str]:
            applier = orchestrator._applier # type: ignore[protect]
            if applier is None:
                return []
            return applier.apply_settings({key: value})

        self._impl = LayerHotSwap(
            stack    = orchestrator._stack, # type: ignore[protect]
            apply_fn = _lazy_apply_fn,
            router   = orchestrator._router, # type: ignore[protect]
        )

    def swap(self, name: str, new_layer: Any) -> None:
        """Replace the named layer and re-apply via stored applier."""
        self._execute("swap", name, lambda: self._impl.swap(name, new_layer))

    def remove(self, name: str) -> None:
        """Remove the named layer and re-apply via stored applier."""
        self._execute("remove", name, lambda: self._impl.remove(name))

    def insert(self, new_layer: Any) -> None:
        """Insert a new layer (by its .name attribute) and re-apply."""
        self._execute("insert", getattr(new_layer, "name", "?"), lambda: self._impl.insert(new_layer))

    def _execute(self, operation: str, layer_name: str, fn: Any) -> None:
        """
        Execute a hot-swap operation with audit, metrics, and event emission.

        v16 fix: captures the HotSwapResult returned by LayerHotSwap.swap/
        remove/insert and forwards result.changes (int) and result.errors
        to the HotSwapCompletedEvent and the stored result dict.
        """
        import time as _time
        from core.hot_swap import HotSwapResult as _HotSwapResult
        t0 = _time.perf_counter()
        errors: List[str] = []
        n_changes: int = 0

        try:
            result_obj: Any = fn()
            # LayerHotSwap operations return HotSwapResult
            if isinstance(result_obj, _HotSwapResult):
                n_changes = result_obj.changes
                errors    = list(result_obj.errors)
        except Exception as exc:
            errors.append(str(exc))
            logger.error("[HotSwap] %s(%s) failed: %s", operation, layer_name, exc)

        duration_ms = (_time.perf_counter() - t0) * 1000
        ok = len(errors) == 0

        # Build descriptive changes list for HotSwapCompletedEvent
        changes_desc: List[str] = [f"{n_changes} key(s) changed"] if n_changes else []

        # Store result on orchestrator
        result: Dict[str, Any] = {
            "operation":   operation,
            "layer_name":  layer_name,
            "ok":          ok,
            "changes":     n_changes,
            "errors":      errors,
            "duration_ms": round(duration_ms, 2),
        }
        self._orc._last_hot_swap_result = result # type: ignore[protect]

        # Audit
        self._orc._audit_phase( # type: ignore[protect]
            "hot_swap",
            f"{operation}({layer_name}) {'ok' if ok else 'FAILED'}  changes={n_changes}",
            level="info" if ok else "error",
            duration_ms=round(duration_ms, 1),
            changes=n_changes,
            errors=len(errors),
        )

        # Emit HotSwapCompletedEvent
        self._orc._router.emit_hot_swap_completed( # type: ignore[protect]
            operation=operation,
            layer_name=layer_name,
            changes=changes_desc,
            errors=errors,
            duration_ms=duration_ms,
        )

        # Emit layer-specific follow-up events
        if ok:
            if layer_name == "session":
                self._orc._maybe_emit_session_event(source="hot_swap") # type: ignore[protect]
            if layer_name == "network":
                self._orc._maybe_emit_network_event(source="hot_swap") # type: ignore[protect]
            if layer_name == "context":
                self._orc._maybe_emit_context_event(source="hot_swap")  # v17  # type: ignore[protect]

        logger.info(
            "[HotSwap] %s(%s) %s  changes=%d  %.1fms",
            operation, layer_name, "✓" if ok else "✗", n_changes, duration_ms,
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
