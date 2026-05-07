"""
tests/test_v17.py
=================
Test Suite  (v17)

Covers all v17 additions and regressions:

  - core/protocol.py v17
      ContextSwitchedEvent gains ``source`` field (default "startup")
      ContextSwitchedEvent backward-compatible (old_context / new_context still work)
      GetActiveContextQuery importable and callable

  - core/protocol.py v17 — MessageRouter.emit_context_changed()
      emit_context_changed() exists and emits ContextSwitchedEvent

  - orchestrator.py v17
      _active_context tracking: old_context is "default" on first emission,
        then the previous mode on subsequent emissions
      GetActiveContextQuery registered and returns correct value
      _maybe_emit_context_event(source=) passes source to event
      _WrappedHotSwap._execute(): context layer swap emits ContextSwitchedEvent

  - Regressions: all v16 / v15 / v14 / v13 behaviours unchanged

Run::

    python3 tests/test_v17.py
    pytest tests/test_v17.py -v

Expected: all tests pass without a running qutebrowser instance.
"""

from __future__ import annotations

import os
import sys
import unittest
from typing import Any, List

# ── Path setup ────────────────────────────────────────────────────────────────
# In the real repo: tests/test_v17.py → parent is project root
# In the mounted project copy: test_v17.py IS at project root
_here = os.path.dirname(os.path.abspath(__file__))
_root = os.path.dirname(_here)
# Try parent first (normal repo layout); fall back to same dir (mounted copy)
if os.path.isdir(os.path.join(_root, "core")):
    if _root not in sys.path:
        sys.path.insert(0, _root)
else:
    # Mounted: file is already in the project root dir
    if _here not in sys.path:
        sys.path.insert(0, _here)


# ═══════════════════════════════════════════════════════════════════
# Helpers
# ═══════════════════════════════════════════════════════════════════

def _can_import() -> bool:
    try:
        from core.protocol import Event  # type: ignore[import]
        return True
    except Exception:
        return False


_ARCH_AVAILABLE = _can_import()


def skip_without_arch(fn: Any) -> Any:
    import functools

    @functools.wraps(fn)
    def wrapper(*a: Any, **kw: Any) -> Any:
        if not _ARCH_AVAILABLE:
            raise unittest.SkipTest("core architecture not importable in this environment")
        return fn(*a, **kw)
    return wrapper


# ═══════════════════════════════════════════════════════════════════
# protocol.py v17 — ContextSwitchedEvent source field
# ═══════════════════════════════════════════════════════════════════

class TestContextSwitchedEventV17(unittest.TestCase):

    @skip_without_arch
    def test_context_switched_event_has_source_field(self) -> None:
        """ContextSwitchedEvent must have a source field."""
        from core.protocol import ContextSwitchedEvent
        e = ContextSwitchedEvent(old_context="default", new_context="work", source="startup")
        self.assertEqual(e.source, "startup")

    @skip_without_arch
    def test_context_switched_event_source_default(self) -> None:
        """source defaults to 'startup' when omitted."""
        from core.protocol import ContextSwitchedEvent
        e = ContextSwitchedEvent(old_context="default", new_context="dev")
        self.assertEqual(e.source, "startup")

    @skip_without_arch
    def test_context_switched_event_backward_compat(self) -> None:
        """Old fields still work after adding source."""
        from core.protocol import ContextSwitchedEvent
        e = ContextSwitchedEvent(old_context="default", new_context="research")
        self.assertEqual(e.old_context, "default")
        self.assertEqual(e.new_context, "research")

    @skip_without_arch
    def test_context_switched_event_hot_swap_source(self) -> None:
        """source can be set to 'hot_swap'."""
        from core.protocol import ContextSwitchedEvent
        e = ContextSwitchedEvent(old_context="work", new_context="media", source="hot_swap")
        self.assertEqual(e.source, "hot_swap")
        self.assertEqual(e.old_context, "work")
        self.assertEqual(e.new_context, "media")

    @skip_without_arch
    def test_context_switched_event_frozen(self) -> None:
        """ContextSwitchedEvent is still immutable (frozen dataclass)."""
        from core.protocol import ContextSwitchedEvent
        e = ContextSwitchedEvent(old_context="default", new_context="work")
        with self.assertRaises((AttributeError, TypeError)):
            e.source = "mutated"  # type: ignore[misc]


# ═══════════════════════════════════════════════════════════════════
# protocol.py v17 — GetActiveContextQuery
# ═══════════════════════════════════════════════════════════════════

class TestGetActiveContextQueryV17(unittest.TestCase):

    @skip_without_arch
    def test_get_active_context_query_importable(self) -> None:
        from core.protocol import GetActiveContextQuery
        q = GetActiveContextQuery()
        self.assertIsNotNone(q)

    @skip_without_arch
    def test_get_active_context_query_is_query(self) -> None:
        from core.protocol import GetActiveContextQuery, Query
        q = GetActiveContextQuery()
        self.assertIsInstance(q, Query)


# ═══════════════════════════════════════════════════════════════════
# protocol.py v17 — MessageRouter.emit_context_changed()
# ═══════════════════════════════════════════════════════════════════

class TestEmitContextChangedV17(unittest.TestCase):

    @skip_without_arch
    def test_emit_context_changed_exists(self) -> None:
        from core.protocol import MessageRouter
        router = MessageRouter()
        self.assertTrue(callable(getattr(router, "emit_context_changed", None)))

    @skip_without_arch
    def test_emit_context_changed_emits_event(self) -> None:
        from core.protocol import MessageRouter, ContextSwitchedEvent, Event
        router = MessageRouter()
        received: List[ContextSwitchedEvent] = []

        def handler(e: Event) -> None:
            if isinstance(e, ContextSwitchedEvent):
                received.append(e)

        router.events.subscribe(ContextSwitchedEvent, handler)
        router.emit_context_changed(
            old_context="default",
            new_context="work",
            source="startup",
        )
        self.assertEqual(len(received), 1)
        self.assertEqual(received[0].new_context, "work")
        self.assertEqual(received[0].old_context, "default")
        self.assertEqual(received[0].source, "startup")

    @skip_without_arch
    def test_emit_context_changed_default_source(self) -> None:
        from core.protocol import MessageRouter, ContextSwitchedEvent, Event
        router = MessageRouter()
        received: List[ContextSwitchedEvent] = []

        def handler(e: Event) -> None:
            if isinstance(e, ContextSwitchedEvent):
                received.append(e)

        router.events.subscribe(ContextSwitchedEvent, handler)
        router.emit_context_changed(old_context="default", new_context="media")
        self.assertEqual(received[0].source, "startup")


# ═══════════════════════════════════════════════════════════════════
# orchestrator.py v17 — _active_context tracking
# ═══════════════════════════════════════════════════════════════════

class TestOrchestratorActiveContextTracking(unittest.TestCase):

    @skip_without_arch
    def test_active_context_initial_value(self) -> None:
        from core.layer     import LayerStack
        from core.lifecycle import LifecycleManager
        from core.protocol  import MessageRouter
        from core.state     import ConfigStateMachine
        from orchestrator   import ConfigOrchestrator

        orch = ConfigOrchestrator(
            stack     = LayerStack(),
            router    = MessageRouter(),
            lifecycle = LifecycleManager(),
            fsm       = ConfigStateMachine(),
        )
        self.assertEqual(orch._active_context, "default")  # type: ignore[attr-defined]

    @skip_without_arch
    def test_maybe_emit_context_event_updates_tracker(self) -> None:
        """After _maybe_emit_context_event(), _active_context is updated."""
        from core.layer     import LayerStack
        from core.lifecycle import LifecycleManager
        from core.protocol  import MessageRouter
        from core.state     import ConfigStateMachine
        from orchestrator   import ConfigOrchestrator
        from layers.context import ContextLayer

        stack = LayerStack()
        stack.register(ContextLayer(context="work"))
        stack.resolve()

        orch = ConfigOrchestrator(
            stack     = stack,
            router    = MessageRouter(),
            lifecycle = LifecycleManager(),
            fsm       = ConfigStateMachine(),
        )
        self.assertEqual(orch._active_context, "default")  # type: ignore[attr-defined]
        orch._maybe_emit_context_event(source="startup")    # type: ignore[attr-defined]
        self.assertEqual(orch._active_context, "work")      # type: ignore[attr-defined]

    @skip_without_arch
    def test_old_context_reflects_previous_on_second_emission(self) -> None:
        """old_context in second event = value from first event."""
        from core.layer     import LayerStack
        from core.lifecycle import LifecycleManager
        from core.protocol  import MessageRouter, ContextSwitchedEvent, Event
        from core.state     import ConfigStateMachine
        from orchestrator   import ConfigOrchestrator
        from layers.context import ContextLayer

        received: List[ContextSwitchedEvent] = []

        stack = LayerStack()
        stack.register(ContextLayer(context="work"))
        stack.resolve()

        router = MessageRouter()

        def handler(e: Event) -> None:
            if isinstance(e, ContextSwitchedEvent):
                received.append(e)

        router.events.subscribe(ContextSwitchedEvent, handler)

        orch = ConfigOrchestrator(
            stack     = stack,
            router    = router,
            lifecycle = LifecycleManager(),
            fsm       = ConfigStateMachine(),
        )

        # First emission: old_context should be "default" (initial)
        orch._maybe_emit_context_event(source="startup")    # type: ignore[attr-defined]
        self.assertEqual(len(received), 1)
        self.assertEqual(received[0].old_context, "default")
        self.assertEqual(received[0].new_context, "work")
        self.assertEqual(received[0].source, "startup")

        # Swap to "research" and emit again
        stack2 = LayerStack()
        stack2.register(ContextLayer(context="research"))
        stack2.resolve()
        orch._stack = stack2                                # type: ignore[attr-defined]

        orch._maybe_emit_context_event(source="hot_swap")   # type: ignore[attr-defined]
        self.assertEqual(len(received), 2)
        # old_context should now be "work" (the actual previous value)
        self.assertEqual(received[1].old_context, "work")
        self.assertEqual(received[1].new_context, "research")
        self.assertEqual(received[1].source, "hot_swap")


# ═══════════════════════════════════════════════════════════════════
# orchestrator.py v17 — GetActiveContextQuery handler
# ═══════════════════════════════════════════════════════════════════

class TestGetActiveContextQueryHandler(unittest.TestCase):

    @skip_without_arch
    def test_get_active_context_query_registered(self) -> None:
        from core.layer     import LayerStack
        from core.lifecycle import LifecycleManager
        from core.protocol  import MessageRouter, GetActiveContextQuery
        from core.state     import ConfigStateMachine
        from orchestrator   import ConfigOrchestrator

        orch = ConfigOrchestrator(
            stack     = LayerStack(),
            router    = MessageRouter(),
            lifecycle = LifecycleManager(),
            fsm       = ConfigStateMachine(),
        )
        self.assertTrue(orch._router.queries.has(GetActiveContextQuery))  # type: ignore[protected]

    @skip_without_arch
    def test_get_active_context_returns_default_without_context_layer(self) -> None:
        from core.layer     import LayerStack
        from core.lifecycle import LifecycleManager
        from core.protocol  import MessageRouter, GetActiveContextQuery
        from core.state     import ConfigStateMachine
        from orchestrator   import ConfigOrchestrator

        orch = ConfigOrchestrator(
            stack     = LayerStack(),
            router    = MessageRouter(),
            lifecycle = LifecycleManager(),
            fsm       = ConfigStateMachine(),
        )
        result = orch._router.ask(GetActiveContextQuery())  # type: ignore[attr-defined]
        self.assertEqual(result, "default")

    @skip_without_arch
    def test_get_active_context_returns_active_mode(self) -> None:
        from core.layer     import LayerStack
        from core.lifecycle import LifecycleManager
        from core.protocol  import MessageRouter, GetActiveContextQuery
        from core.state     import ConfigStateMachine
        from orchestrator   import ConfigOrchestrator
        from layers.context import ContextLayer

        stack = LayerStack()
        stack.register(ContextLayer(context="research"))
        stack.resolve()

        orch = ConfigOrchestrator(
            stack     = stack,
            router    = MessageRouter(),
            lifecycle = LifecycleManager(),
            fsm       = ConfigStateMachine(),
        )
        result = orch._router.ask(GetActiveContextQuery()) # type: ignore[private]
        self.assertEqual(result, "research")


# ═══════════════════════════════════════════════════════════════════
# Regressions  (v16 / v15 behaviours unchanged)
# ═══════════════════════════════════════════════════════════════════

class TestV17Regressions(unittest.TestCase):

    @skip_without_arch
    def test_summary_shows_v17(self) -> None:
        from core.layer     import LayerStack
        from core.lifecycle import LifecycleManager
        from core.protocol  import MessageRouter
        from core.state     import ConfigStateMachine
        from orchestrator   import ConfigOrchestrator
        from layers.base    import BaseLayer

        orch = ConfigOrchestrator(
            stack     = LayerStack(),
            router    = MessageRouter(),
            lifecycle = LifecycleManager(),
            fsm       = ConfigStateMachine(),
        )
        orch._stack.register(BaseLayer())   # type: ignore[protected]
        orch._stack.resolve()               # type: ignore[protected]
        summary = orch.summary()
        self.assertIn("v17", summary)

    @skip_without_arch
    def test_get_active_session_query_still_registered(self) -> None:
        from core.layer     import LayerStack
        from core.lifecycle import LifecycleManager
        from core.protocol  import MessageRouter, GetActiveSessionQuery
        from core.state     import ConfigStateMachine
        from orchestrator   import ConfigOrchestrator

        orch = ConfigOrchestrator(
            stack     = LayerStack(),
            router    = MessageRouter(),
            lifecycle = LifecycleManager(),
            fsm       = ConfigStateMachine(),
        )
        self.assertTrue(orch._router.queries.has(GetActiveSessionQuery))  # type: ignore[protected]

    @skip_without_arch
    def test_get_active_network_query_still_registered(self) -> None:
        from core.layer     import LayerStack
        from core.lifecycle import LifecycleManager
        from core.protocol  import MessageRouter, GetActiveNetworkQuery
        from core.state     import ConfigStateMachine
        from orchestrator   import ConfigOrchestrator

        orch = ConfigOrchestrator(
            stack     = LayerStack(),
            router    = MessageRouter(),
            lifecycle = LifecycleManager(),
            fsm       = ConfigStateMachine(),
        )
        self.assertTrue(orch._router.queries.has(GetActiveNetworkQuery))  # type: ignore[protected]

    @skip_without_arch
    def test_session_changed_event_still_importable(self) -> None:
        from core.protocol import SessionChangedEvent
        e = SessionChangedEvent(old_session="unknown", new_session="night", source="startup")
        self.assertEqual(e.new_session, "night")

    @skip_without_arch
    def test_network_mode_changed_event_still_importable(self) -> None:
        from core.protocol import NetworkModeChangedEvent
        e = NetworkModeChangedEvent(old_mode="unknown", new_mode="socks5",
                                    proxy="socks5://127.0.0.1:7897", source="startup")
        self.assertEqual(e.new_mode, "socks5")

    @skip_without_arch
    def test_hot_swap_completed_event_ok_property(self) -> None:
        from core.protocol import HotSwapCompletedEvent
        e = HotSwapCompletedEvent(operation="swap", layer_name="network",
                                   changes=[], errors=[], duration_ms=0.5)
        self.assertTrue(e.ok)

    @skip_without_arch
    def test_active_session_tracking_still_works(self) -> None:
        """v16 _active_session tracker regression."""
        from core.layer     import LayerStack
        from core.lifecycle import LifecycleManager
        from core.protocol  import MessageRouter
        from core.state     import ConfigStateMachine
        from orchestrator   import ConfigOrchestrator

        orch = ConfigOrchestrator(
            stack     = LayerStack(),
            router    = MessageRouter(),
            lifecycle = LifecycleManager(),
            fsm       = ConfigStateMachine(),
        )
        self.assertEqual(orch._active_session, "unknown")  # type: ignore[attr-defined]

    @skip_without_arch
    def test_active_network_tracking_still_works(self) -> None:
        """v16 _active_network_mode tracker regression."""
        from core.layer     import LayerStack
        from core.lifecycle import LifecycleManager
        from core.protocol  import MessageRouter
        from core.state     import ConfigStateMachine
        from orchestrator   import ConfigOrchestrator

        orch = ConfigOrchestrator(
            stack     = LayerStack(),
            router    = MessageRouter(),
            lifecycle = LifecycleManager(),
            fsm       = ConfigStateMachine(),
        )
        self.assertEqual(orch._active_network_mode, "unknown")  # type: ignore[attr-defined]

    @skip_without_arch
    def test_compose_layer_still_functional(self) -> None:
        from core.compose import ComposeLayer
        comp = ComposeLayer("test", 50)
        self.assertEqual(comp.name, "test")

    @skip_without_arch
    def test_pipeline_deep_merge_still_works(self) -> None:
        from core.pipeline import deep_merge
        result = deep_merge({"a": 1}, {"b": 2})
        self.assertEqual(result, {"a": 1, "b": 2})

    @skip_without_arch
    def test_context_switched_event_source_field_in_all_existing_code(self) -> None:
        """Existing code that creates ContextSwitchedEvent without source still works."""
        from core.protocol import ContextSwitchedEvent
        # Backward-compat: source has a default value
        e = ContextSwitchedEvent(old_context="default", new_context="work")
        self.assertEqual(e.source, "startup")
        self.assertEqual(e.new_context, "work")


# ═══════════════════════════════════════════════════════════════════
# ContextSwitchedEvent hot-swap wiring in _WrappedHotSwap
# ═══════════════════════════════════════════════════════════════════

class TestWrappedHotSwapContextEmission(unittest.TestCase):

    @skip_without_arch
    def test_hot_swap_context_layer_emits_context_switched_event(self) -> None:
        """
        When context layer is hot-swapped, ContextSwitchedEvent must be emitted
        with source='hot_swap'.
        """
        from core.layer     import LayerStack
        from core.lifecycle import LifecycleManager
        from core.protocol  import MessageRouter, ContextSwitchedEvent, Event
        from core.state     import ConfigStateMachine
        from orchestrator   import ConfigOrchestrator
        from layers.context import ContextLayer

        stack = LayerStack()
        stack.register(ContextLayer(context="default"))
        stack.resolve()

        router = MessageRouter()
        received: List[ContextSwitchedEvent] = []

        def handler(e: Event) -> None:
            if isinstance(e, ContextSwitchedEvent):
                received.append(e)

        router.events.subscribe(ContextSwitchedEvent, handler)

        orch = ConfigOrchestrator(
            stack     = stack,
            router    = router,
            lifecycle = LifecycleManager(),
            fsm       = ConfigStateMachine(),
        )

        # Simulate hot-swap of context layer
        new_layer = ContextLayer(context="media")
        orch.hot_swap.swap("context", new_layer)

        # ContextSwitchedEvent should have been emitted with source="hot_swap"
        context_events = [e for e in received if e.source == "hot_swap"]
        self.assertTrue(
            len(context_events) >= 1,
            f"Expected ContextSwitchedEvent(source='hot_swap'), got: {received}",
        )


if __name__ == "__main__":
    unittest.main(verbosity=2)


# ═══════════════════════════════════════════════════════════════════
# Structural fixes (strict-mode cleanup)
# ═══════════════════════════════════════════════════════════════════

class TestPolicyChainBoolLen(unittest.TestCase):
    """PolicyChain now has __bool__ and __len__ — eliminates ._policies access."""

    @skip_without_arch
    def test_empty_policy_chain_is_falsy(self) -> None:
        from core.strategy import PolicyChain
        pc = PolicyChain()
        self.assertFalse(bool(pc))

    @skip_without_arch
    def test_policy_chain_with_policy_is_truthy(self) -> None:
        from core.strategy import PolicyChain, ReadOnlyPolicy
        pc = PolicyChain()
        pc.add(ReadOnlyPolicy(["some.key"]))
        self.assertTrue(bool(pc))

    @skip_without_arch
    def test_policy_chain_len(self) -> None:
        from core.strategy import PolicyChain, ReadOnlyPolicy
        pc = PolicyChain()
        self.assertEqual(len(pc), 0)
        pc.add(ReadOnlyPolicy(["k"]))
        self.assertEqual(len(pc), 1)


class TestLayerStackSwapLayer(unittest.TestCase):
    """LayerStack.swap_layer() public method replaces _layers private access."""

    @skip_without_arch
    def test_swap_layer_replaces_existing(self) -> None:
        from core.layer import LayerStack, BaseConfigLayer
        from core.types import ConfigDict as CD

        class LayerA(BaseConfigLayer):
            name = "test_layer"
            priority = 50
            def _settings(self) -> CD:
                return {"x": 1}

        class LayerB(BaseConfigLayer):
            name = "test_layer"
            priority = 50
            def _settings(self) -> CD:
                return {"x": 2}

        stack = LayerStack()
        stack.register(LayerA())
        stack.resolve()
        self.assertEqual(stack.merged.get("settings", {}).get("x"), 1)
        result = stack.swap_layer("test_layer", LayerB())
        self.assertTrue(result)
        stack.resolve()
        self.assertEqual(stack.merged.get("settings", {}).get("x"), 2)

    @skip_without_arch
    def test_swap_layer_returns_false_when_not_found(self) -> None:
        from core.layer import LayerStack
        from layers.base import BaseLayer
        stack = LayerStack()
        stack.register(BaseLayer())
        result = stack.swap_layer("nonexistent_xyz", BaseLayer())
        self.assertFalse(result)


class TestPolicyChainEvaluateSignature(unittest.TestCase):
    """PolicyChain.evaluate() correct 3-arg signature — was broken in config.py."""

    @skip_without_arch
    def test_evaluate_returns_allow_by_default(self) -> None:
        from core.strategy import PolicyChain, PolicyAction
        pc = PolicyChain()
        decision = pc.evaluate("some.key", "value", {})
        self.assertEqual(decision.action, PolicyAction.ALLOW)

    @skip_without_arch
    def test_evaluate_deny_protected_key(self) -> None:
        from core.strategy import PolicyChain, ReadOnlyPolicy, PolicyAction
        pc = PolicyChain()
        pc.add(ReadOnlyPolicy(["protected.key"]))
        decision = pc.evaluate("protected.key", "v", {})
        self.assertEqual(decision.action, PolicyAction.DENY)

    @skip_without_arch
    def test_evaluate_allow_unprotected_key(self) -> None:
        from core.strategy import PolicyChain, ReadOnlyPolicy, PolicyAction
        pc = PolicyChain()
        pc.add(ReadOnlyPolicy(["protected.key"]))
        decision = pc.evaluate("other.key", "v", {})
        self.assertEqual(decision.action, PolicyAction.ALLOW)
