"""
core/__init__.py
================
Public API surface for the ``core`` architecture package.  v10

Import from here for stable, versioned access to core types.
Internal implementation details live in the individual modules.

v10 additions:
  - LayerStack._layers property (public alias for _records; fixes
    orchestrator._handle_get_layer_names variable-shadowing bug)
  - conftest.py for clean pytest discovery from any working directory
  - core/__init__.py now properly exports all public symbols (was empty)
  - FilterStage added to exports (was missing despite being implemented)
  - LayerRecord added to exports (needed by orchestrator type signatures)

v9 additions (retained):
  - Protocol: ConfigReloadedEvent, SnapshotTakenEvent, LayerConflictEvent,
              PolicyDeniedEvent, MetricsEvent
  - Protocol queries: GetSnapshotQuery, GetLayerDiffQuery, GetLayerNamesQuery
  - Incremental: ConfigDiffer promoted to public class
  - Health: SearchEngineCountCheck, ProxySchemeDetailCheck, DownloadPromptCheck
            HealthChecker.with_checks()
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
    LayerRecord,
    LayerStack,
)
from core.lifecycle import (
    LifecycleHook,
    LifecycleManager,
)
from core.pipeline import (
    ConfigPacket,
    FilterStage,
    LogStage,
    MergeStage,
    Pipeline,
    PipeStage,
    TransformStage,
    ValidateStage,
)
from core.protocol import (
    CommandBus,
    EventBus,
    MessageRouter,
    QueryBus,
    Event,
    Command,
    Query,
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
    GetMergedConfigQuery,
    GetHealthReportQuery,
    GetSnapshotQuery,
    GetLayerDiffQuery,
    GetLayerNamesQuery,
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

__all__ = [
    "ChangeKind", "ConfigChange", "ConfigDiffer",
    "ConfigSnapshot", "IncrementalApplier", "SnapshotStore",
    "BaseConfigLayer", "LayerProtocol", "LayerRecord", "LayerStack",
    "LifecycleHook", "LifecycleManager",
    "ConfigPacket", "FilterStage", "LogStage", "MergeStage", "Pipeline",
    "PipeStage", "TransformStage", "ValidateStage",
    "CommandBus", "EventBus", "MessageRouter", "QueryBus",
    "Event", "Command", "Query",
    "LayerAppliedEvent", "ConfigErrorEvent", "ThemeChangedEvent",
    "BindingRegisteredEvent", "ContextSwitchedEvent", "HealthReportReadyEvent",
    "ConfigReloadedEvent", "SnapshotTakenEvent", "LayerConflictEvent",
    "PolicyDeniedEvent", "MetricsEvent",
    "GetMergedConfigQuery", "GetHealthReportQuery",
    "GetSnapshotQuery", "GetLayerDiffQuery", "GetLayerNamesQuery",
    "ApplyLayerCommand", "ReloadConfigCommand", "SetOptionCommand",
    "ConfigEvent", "ConfigState", "ConfigStateMachine",
    "Policy", "PolicyAction", "PolicyChain", "PolicyDecision",
    "Strategy", "StrategyRegistry",
    "ReadOnlyPolicy", "TypeEnforcePolicy", "RangePolicy", "AllowlistPolicy",
    "HealthCheck", "HealthChecker", "HealthIssue", "HealthReport", "Severity",
    "BlockingEnabledCheck", "BlockingListCheck", "SearchEngineDefaultCheck",
    "SearchEngineUrlCheck", "WebRTCPolicyCheck", "CookieAcceptCheck",
    "StartPageCheck", "EditorCommandCheck", "DownloadDirCheck",
    "TabTitleFormatCheck", "ProxySchemeCheck", "ZoomDefaultCheck",
    "FontFamilyCheck", "SpellcheckLangCheck", "ContentHeaderCheck",
    "SearchEngineCountCheck", "ProxySchemeDetailCheck", "DownloadPromptCheck",
]
