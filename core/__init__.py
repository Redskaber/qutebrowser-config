"""
core/__init__.py
================
Public API surface for the ``core`` architecture package.

Import from here for stable, versioned access to core types.
Internal implementation details live in the individual modules.
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
    ConfigErrorEvent,
    EventBus,
    LayerAppliedEvent,
    MessageRouter,
    QueryBus,
    SetOptionCommand,
    ThemeChangedEvent,
)
from core.state import (
    ConfigEvent,
    ConfigState,
    ConfigStateMachine,
    StateContext,
)
from core.strategy import (
    AllowlistPolicy,
    Policy,
    PolicyAction,
    PolicyChain,
    PolicyDecision,
    RangePolicy,
    ReadOnlyPolicy,
    Strategy,
    StrategyRegistry,
    TypeEnforcePolicy,
)

__all__ = [
    # incremental
    "ChangeKind", "ConfigChange", "ConfigDiffer", "ConfigSnapshot",
    "IncrementalApplier", "SnapshotStore",
    # layer
    "BaseConfigLayer", "LayerProtocol", "LayerStack",
    # lifecycle
    "LifecycleHook", "LifecycleManager",
    # pipeline
    "ConfigPacket", "LogStage", "MergeStage", "Pipeline", "PipeStage",
    "TransformStage", "ValidateStage",
    # protocol
    "CommandBus", "ConfigErrorEvent", "EventBus", "LayerAppliedEvent",
    "MessageRouter", "QueryBus", "SetOptionCommand", "ThemeChangedEvent",
    # state
    "ConfigEvent", "ConfigState", "ConfigStateMachine", "StateContext",
    # strategy
    "AllowlistPolicy", "Policy", "PolicyAction", "PolicyChain",
    "PolicyDecision", "RangePolicy", "ReadOnlyPolicy", "Strategy",
    "StrategyRegistry", "TypeEnforcePolicy",
]
