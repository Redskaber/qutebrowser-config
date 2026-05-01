"""
core/__init__.py
================
Public API surface for the ``core`` architecture package.  v5

Import from here for stable, versioned access to core types.
Internal implementation details live in the individual modules.

v5 additions:
  - ContextSwitchedEvent, HealthReportReadyEvent
  - GetMergedConfigQuery, GetHealthReportQuery
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
    GetMergedConfigQuery,
    GetHealthReportQuery,
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
)

__all__ = [
    # incremental
    "ChangeKind", "ConfigChange", "ConfigDiffer",
    "ConfigSnapshot", "IncrementalApplier", "SnapshotStore",
    # layer
    "BaseConfigLayer", "LayerProtocol", "LayerStack",
    # lifecycle
    "LifecycleHook", "LifecycleManager",
    # pipeline
    "ConfigPacket", "LogStage", "MergeStage", "Pipeline",
    "PipeStage", "TransformStage", "ValidateStage",
    # protocol — events
    "CommandBus", "EventBus", "MessageRouter", "QueryBus",
    "Event", "Command", "Query",
    "LayerAppliedEvent", "ConfigErrorEvent", "ThemeChangedEvent",
    "BindingRegisteredEvent", "ContextSwitchedEvent", "HealthReportReadyEvent",
    # protocol — queries
    "GetMergedConfigQuery", "GetHealthReportQuery",
    # state
    "ConfigEvent", "ConfigState", "ConfigStateMachine",
    # strategy
    "Policy", "PolicyAction", "PolicyChain", "PolicyDecision",
    "Strategy", "StrategyRegistry",
    "ReadOnlyPolicy", "TypeEnforcePolicy", "RangePolicy", "AllowlistPolicy",
    # health
    "HealthCheck", "HealthChecker", "HealthIssue", "HealthReport", "Severity",
]
