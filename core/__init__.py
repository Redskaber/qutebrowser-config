"""
core/__init__.py
================
Public API surface for the ``core`` architecture package.  v12

Import from here for stable, versioned access to core types.
Internal implementation details live in the individual modules.

v12 additions:
  - ``core.metrics``: MetricsCollector, MetricsSample, PhaseTimer,
    get_metrics_collector, reset_metrics_collector, metrics_time exported.
  - ``core.audit``: AuditLevel, AuditEntry, AuditFilter, AuditLog,
    get_audit_log, reset_audit_log, audit_debug/info/warn/error exported.
  - ``core.pipeline`` v12 stages: TeeStage, RetryStage, CompositeStage.
  - ``core.protocol`` v12 query: GetMetricsSummaryQuery.

v11 additions (retained):
  - ``core.audit`` module (new): AuditLevel, AuditEntry, AuditFilter,
    AuditLog, get_audit_log / reset_audit_log, audit_* helpers.
  - ``core.pipeline`` v11 stages: ReduceStage, BranchStage, CacheStage,
    AuditStage. Pipeline.fork(), describe(), __iter__; PipeStage.__add__.
  - ``core.pipeline`` ConfigPacket.with_errors() / with_warnings().
  - noop_pipeline() helper.

v10.1 additions (retained):
  - ``core/types.py`` as the zero-dependency primitive layer.
  - ``Keybind`` first-class public export.

v10 additions (retained):
  - LayerStack._layers property (public alias for _records).
  - FilterStage and LayerRecord exported.

v9 additions (retained):
  - Protocol: ConfigReloadedEvent, SnapshotTakenEvent, LayerConflictEvent,
              PolicyDeniedEvent, MetricsEvent.
  - Queries: GetSnapshotQuery, GetLayerDiffQuery, GetLayerNamesQuery.
  - Incremental: ConfigDiffer promoted to public class.
  - Health: new checks and HealthChecker.with_checks().
"""

# ── Primitive types FIRST (zero project-level deps) ───────────────────────
from core.types import (
    ConfigDict,
    Keybind,
)

# ── Incremental ────────────────────────────────────────────────────────────
from core.incremental import (
    ChangeKind,
    ConfigChange,
    ConfigDiffer,
    ConfigSnapshot,
    IncrementalApplier,
    SnapshotStore,
)

# ── Layer ──────────────────────────────────────────────────────────────────
from core.layer import (
    BaseConfigLayer,
    LayerProtocol,
    LayerRecord,
    LayerStack,
)

# ── Lifecycle ──────────────────────────────────────────────────────────────
from core.lifecycle import (
    LifecycleHook,
    LifecycleManager,
)

# ── Pipeline ───────────────────────────────────────────────────────────────
from core.pipeline import (
    ConfigPacket,
    FilterStage,
    LogStage,
    MergeStage,
    Pipeline,
    PipeStage,
    TransformStage,
    ValidateStage,
    # v11 stages
    ReduceStage,
    BranchStage,
    CacheStage,
    AuditStage,
    # v12 stages
    TeeStage,
    RetryStage,
    CompositeStage,
    noop_pipeline,
)

# ── Protocol / MessageRouter ───────────────────────────────────────────────
from core.protocol import (
    CommandBus,
    EventBus,
    MessageRouter,
    QueryBus,
    Event,
    Command,
    Query,
    # Events
    LayerAppliedEvent,
    ConfigErrorEvent,
    ThemeChangedEvent,
    BindingRegisteredEvent,
    ContextSwitchedEvent,
    HealthReportReadyEvent,
    ConfigReloadedEvent,
    SnapshotTakenEvent,
    LayerConflictEvent,
    PolicyDeniedEvent,
    MetricsEvent,
    # Queries
    GetMergedConfigQuery,
    GetHealthReportQuery,
    GetSnapshotQuery,
    GetLayerDiffQuery,
    GetLayerNamesQuery,
    GetMetricsSummaryQuery,
    # Commands
    ApplyLayerCommand,
    ReloadConfigCommand,
    SetOptionCommand,
)

# ── State Machine ──────────────────────────────────────────────────────────
from core.state import (
    ConfigEvent,
    ConfigState,
    ConfigStateMachine,
)

# ── Strategy / Policy ──────────────────────────────────────────────────────
from core.strategy import (
    Policy,
    PolicyAction,
    PolicyChain,
    PolicyDecision,
    Strategy,
    StrategyRegistry,
    ReadOnlyPolicy,
    TypeEnforcePolicy,
    RangePolicy,
    AllowlistPolicy,
)

# ── Health ─────────────────────────────────────────────────────────────────
from core.health import (
    HealthCheck,
    HealthChecker,
    HealthIssue,
    HealthReport,
    Severity,
    BlockingEnabledCheck,
    BlockingListCheck,
    SearchEngineDefaultCheck,
    SearchEngineUrlCheck,
    WebRTCPolicyCheck,
    CookieAcceptCheck,
    StartPageCheck,
    EditorCommandCheck,
    DownloadDirCheck,
    TabTitleFormatCheck,
    ProxySchemeCheck,
    ZoomDefaultCheck,
    FontFamilyCheck,
    SpellcheckLangCheck,
    ContentHeaderCheck,
    SearchEngineCountCheck,
    ProxySchemeDetailCheck,
    DownloadPromptCheck,
)

# ── Audit (v11/v12) ────────────────────────────────────────────────────────
from core.audit import (
    AuditLevel,
    AuditEntry,
    AuditFilter,
    AuditLog,
    get_audit_log,
    reset_audit_log,
    audit_debug,
    audit_info,
    audit_warn,
    audit_error,
)

# ── Metrics (v12) ──────────────────────────────────────────────────────────
from core.metrics import (
    MetricsSample,
    MetricsCollector,
    PhaseTimer,
    get_metrics_collector,
    reset_metrics_collector,
    metrics_time,
)

# ─────────────────────────────────────────────
# Stable public API surface
# ─────────────────────────────────────────────

__all__ = [
    # ── Types ─────────────────────────────────────────────────────────────
    "ConfigDict", "Keybind",
    # ── Incremental ───────────────────────────────────────────────────────
    "ChangeKind", "ConfigChange", "ConfigDiffer", "ConfigSnapshot",
    "IncrementalApplier", "SnapshotStore",
    # ── Layer ─────────────────────────────────────────────────────────────
    "BaseConfigLayer", "LayerProtocol", "LayerRecord", "LayerStack",
    # ── Lifecycle ─────────────────────────────────────────────────────────
    "LifecycleHook", "LifecycleManager",
    # ── Pipeline ──────────────────────────────────────────────────────────
    "ConfigPacket", "FilterStage", "LogStage", "MergeStage", "Pipeline",
    "PipeStage", "TransformStage", "ValidateStage",
    # pipeline v11
    "ReduceStage", "BranchStage", "CacheStage", "AuditStage",
    # pipeline v12
    "TeeStage", "RetryStage", "CompositeStage",
    "noop_pipeline",
    # ── Protocol / MessageRouter ──────────────────────────────────────────
    "CommandBus", "EventBus", "MessageRouter", "QueryBus",
    "Event", "Command", "Query",
    "LayerAppliedEvent", "ConfigErrorEvent", "ThemeChangedEvent",
    "BindingRegisteredEvent", "ContextSwitchedEvent", "HealthReportReadyEvent",
    "ConfigReloadedEvent", "SnapshotTakenEvent", "LayerConflictEvent",
    "PolicyDeniedEvent", "MetricsEvent",
    "GetMergedConfigQuery", "GetHealthReportQuery",
    "GetSnapshotQuery", "GetLayerDiffQuery", "GetLayerNamesQuery",
    "GetMetricsSummaryQuery",
    "ApplyLayerCommand", "ReloadConfigCommand", "SetOptionCommand",
    # ── State Machine ─────────────────────────────────────────────────────
    "ConfigEvent", "ConfigState", "ConfigStateMachine",
    # ── Strategy / Policy ─────────────────────────────────────────────────
    "Policy", "PolicyAction", "PolicyChain", "PolicyDecision",
    "Strategy", "StrategyRegistry",
    "ReadOnlyPolicy", "TypeEnforcePolicy", "RangePolicy", "AllowlistPolicy",
    # ── Health ────────────────────────────────────────────────────────────
    "HealthCheck", "HealthChecker", "HealthIssue", "HealthReport", "Severity",
    "BlockingEnabledCheck", "BlockingListCheck", "SearchEngineDefaultCheck",
    "SearchEngineUrlCheck", "WebRTCPolicyCheck", "CookieAcceptCheck",
    "StartPageCheck", "EditorCommandCheck", "DownloadDirCheck",
    "TabTitleFormatCheck", "ProxySchemeCheck", "ZoomDefaultCheck",
    "FontFamilyCheck", "SpellcheckLangCheck", "ContentHeaderCheck",
    "SearchEngineCountCheck", "ProxySchemeDetailCheck", "DownloadPromptCheck",
    # ── Audit (v11/v12) ───────────────────────────────────────────────────
    "AuditLevel", "AuditEntry", "AuditFilter", "AuditLog",
    "get_audit_log", "reset_audit_log",
    "audit_debug", "audit_info", "audit_warn", "audit_error",
    # ── Metrics (v12) ─────────────────────────────────────────────────────
    "MetricsSample", "MetricsCollector", "PhaseTimer",
    "get_metrics_collector", "reset_metrics_collector", "metrics_time",
]
