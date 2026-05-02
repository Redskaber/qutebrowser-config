"""
core/__init__.py
================
Public API surface for the ``core`` architecture package.  v9

Import from here for stable, versioned access to core types.
Internal implementation details live in the individual modules.

v9 additions:
  - Protocol: ConfigReloadedEvent, SnapshotTakenEvent, LayerConflictEvent,
              PolicyDeniedEvent, MetricsEvent
  - Protocol queries: GetSnapshotQuery, GetLayerDiffQuery, GetLayerNamesQuery
  - Incremental: ConfigDiffer (now a proper public class)
  - Health: SearchEngineCountCheck, ProxySchemeDetailCheck, DownloadPromptCheck
            HealthChecker.with_checks()

v5–v8 additions retained:
  - ContextSwitchedEvent, HealthReportReadyEvent
  - GetMergedConfigQuery, GetHealthReportQuery
  - ChangeKind, ConfigChange, ConfigSnapshot, IncrementalApplier, SnapshotStore
"""

from core.incremental import (
    ChangeKind,
    ConfigChange,
    ConfigDiffer,
    ConfigSnapshot,
    IncrementalApplier,
    SnapshotStore,
)
from core.layer import (
    BaseConfigLayer,
    LayerProtocol,
    LayerStack,
)
from core.lifecycle import (
    LifecycleHook,
    LifecycleManager,
)
from core.pipeline import (
    ConfigPacket,
    LogStage,
    MergeStage,
    Pipeline,
    PipeStage,
    TransformStage,
    ValidateStage,
)
from core.protocol import (
    # buses / router
    CommandBus,
    EventBus,
    MessageRouter,
    QueryBus,
    # base message types
    Event,
    Command,
    Query,
    # events (v5–v8)
    LayerAppliedEvent,
    ConfigErrorEvent,
    ThemeChangedEvent,
    BindingRegisteredEvent,
    ContextSwitchedEvent,
    HealthReportReadyEvent,
    # events (v9)
    ConfigReloadedEvent,
    SnapshotTakenEvent,
    LayerConflictEvent,
    PolicyDeniedEvent,
    MetricsEvent,
    # queries (v5–v8)
    GetMergedConfigQuery,
    GetHealthReportQuery,
    # queries (v9)
    GetSnapshotQuery,
    GetLayerDiffQuery,
    GetLayerNamesQuery,
    # commands
    ApplyLayerCommand,
    ReloadConfigCommand,
    SetOptionCommand,
)
from core.state import (
    ConfigEvent,
    ConfigState,
    ConfigStateMachine,
)
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
from core.health import (
    HealthCheck,
    HealthChecker,
    HealthIssue,
    HealthReport,
    Severity,
    # individual checks (useful for test injection via HealthChecker.with_checks)
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
    # v9
    SearchEngineCountCheck,
    ProxySchemeDetailCheck,
    DownloadPromptCheck,
)

__all__ = [
    # ── incremental ──────────────────────────────────────────────────
    "ChangeKind", "ConfigChange", "ConfigDiffer",
    "ConfigSnapshot", "IncrementalApplier", "SnapshotStore",
    # ── layer ────────────────────────────────────────────────────────
    "BaseConfigLayer", "LayerProtocol", "LayerStack",
    # ── lifecycle ────────────────────────────────────────────────────
    "LifecycleHook", "LifecycleManager",
    # ── pipeline ─────────────────────────────────────────────────────
    "ConfigPacket", "LogStage", "MergeStage", "Pipeline",
    "PipeStage", "TransformStage", "ValidateStage",
    # ── protocol — buses / router ────────────────────────────────────
    "CommandBus", "EventBus", "MessageRouter", "QueryBus",
    "Event", "Command", "Query",
    # ── protocol — events (v5–v8) ────────────────────────────────────
    "LayerAppliedEvent", "ConfigErrorEvent", "ThemeChangedEvent",
    "BindingRegisteredEvent", "ContextSwitchedEvent", "HealthReportReadyEvent",
    # ── protocol — events (v9) ───────────────────────────────────────
    "ConfigReloadedEvent", "SnapshotTakenEvent", "LayerConflictEvent",
    "PolicyDeniedEvent", "MetricsEvent",
    # ── protocol — queries (v5–v8) ───────────────────────────────────
    "GetMergedConfigQuery", "GetHealthReportQuery",
    # ── protocol — queries (v9) ──────────────────────────────────────
    "GetSnapshotQuery", "GetLayerDiffQuery", "GetLayerNamesQuery",
    # ── protocol — commands ──────────────────────────────────────────
    "ApplyLayerCommand", "ReloadConfigCommand", "SetOptionCommand",
    # ── state ────────────────────────────────────────────────────────
    "ConfigEvent", "ConfigState", "ConfigStateMachine",
    # ── strategy ─────────────────────────────────────────────────────
    "Policy", "PolicyAction", "PolicyChain", "PolicyDecision",
    "Strategy", "StrategyRegistry",
    "ReadOnlyPolicy", "TypeEnforcePolicy", "RangePolicy", "AllowlistPolicy",
    # ── health ───────────────────────────────────────────────────────
    "HealthCheck", "HealthChecker", "HealthIssue", "HealthReport", "Severity",
    "BlockingEnabledCheck", "BlockingListCheck", "SearchEngineDefaultCheck",
    "SearchEngineUrlCheck", "WebRTCPolicyCheck", "CookieAcceptCheck",
    "StartPageCheck", "EditorCommandCheck", "DownloadDirCheck",
    "TabTitleFormatCheck", "ProxySchemeCheck", "ZoomDefaultCheck",
    "FontFamilyCheck", "SpellcheckLangCheck", "ContentHeaderCheck",
    "SearchEngineCountCheck", "ProxySchemeDetailCheck", "DownloadPromptCheck",
]
