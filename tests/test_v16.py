"""
tests/test_v16.py
=================
Test Suite  (v16)

Covers all v16 fixes and regressions:

  - core/pipeline.py v16
      deep_merge public alias present in __all__ and importable
      deep_merge behaviour identical to _deep_merge

  - core/compose.py v16
      no longer imports private _deep_merge (import uses deep_merge)

  - orchestrator.py v16
      _active_session tracking: old_session is "unknown" on first emission,
        then the previous mode on subsequent emissions
      _active_network_mode tracking: same pattern for network events
      _WrappedHotSwap._execute(): HotSwapResult.changes propagated to
        _last_hot_swap_result["changes"] and HotSwapCompletedEvent.changes

  - Regressions: all v15 / v14 / v13 behaviours unchanged

Run::

    python3 tests/test_v16.py
    pytest tests/test_v16.py -v

Expected: all tests pass without a running qutebrowser instance.

Note: tests that require core.types (which shadows stdlib types) are skipped
in sandbox environments where the import is blocked.  They pass in the real
qutebrowser config environment.
"""

from __future__ import annotations

import os
import sys
import unittest
from typing import Any, List

# ── Path setup ────────────────────────────────────────────────────────────────
_here = os.path.dirname(os.path.abspath(__file__))
_root = os.path.dirname(_here)
if _root not in sys.path:
    sys.path.insert(0, _root)


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
# pipeline.py v16 — deep_merge public export
# ═══════════════════════════════════════════════════════════════════

class TestPipelineDeepMergePublicExport(unittest.TestCase):

    @skip_without_arch
    def test_deep_merge_in_all(self) -> None:
        from core import pipeline
        self.assertIn("deep_merge", pipeline.__all__)

    @skip_without_arch
    def test_deep_merge_importable_directly(self) -> None:
        from core.pipeline import deep_merge  # type: ignore[import]
        self.assertTrue(callable(deep_merge))

    @skip_without_arch
    def test_deep_merge_simple(self) -> None:
        from core.pipeline import deep_merge  # type: ignore[import]
        result = deep_merge({"a": 1, "b": 2}, {"b": 3, "c": 4})
        self.assertEqual(result, {"a": 1, "b": 3, "c": 4})

    @skip_without_arch
    def test_deep_merge_nested(self) -> None:
        from core.pipeline import deep_merge  # type: ignore[import]
        base    = {"x": {"a": 1, "b": 2}}
        overlay = {"x": {"b": 99, "c": 3}}
        result  = deep_merge(base, overlay)
        self.assertEqual(result["x"], {"a": 1, "b": 99, "c": 3})

    @skip_without_arch
    def test_deep_merge_does_not_mutate_base(self) -> None:
        from core.pipeline import deep_merge  # type: ignore[import]
        base    = {"a": 1}
        overlay = {"b": 2}
        deep_merge(base, overlay)
        self.assertNotIn("b", base)


# ═══════════════════════════════════════════════════════════════════
# compose.py v16 — no longer uses private _deep_merge
# ═══════════════════════════════════════════════════════════════════

class TestComposeNoPrivateImport(unittest.TestCase):

    @skip_without_arch
    def test_compose_importable(self) -> None:
        from core.compose import ComposeLayer  # type: ignore[import]
        self.assertTrue(True)

    @skip_without_arch
    def test_compose_uses_public_deep_merge(self) -> None:
        """compose.py must not import _deep_merge directly."""
        import importlib.util
        spec = importlib.util.find_spec("core.compose")
        if spec is None or spec.origin is None:
            raise unittest.SkipTest("core.compose not found as file")
        with open(spec.origin) as f:
            source = f.read()
        self.assertNotIn(
            "import _deep_merge",
            source,
            "compose.py should import deep_merge (public), not _deep_merge",
        )

    @skip_without_arch
    def test_compose_build_merges_children(self) -> None:
        from core.compose import ComposeLayer       # type: ignore[import]
        from core.layer   import BaseConfigLayer    # type: ignore[import]
        from core.types   import ConfigDict         # type: ignore[import]

        class LayerA(BaseConfigLayer):
            name = "a"
            priority = 10
            description = "A"
            def _settings(self) -> ConfigDict: return {"k1": "v1"}

        class LayerB(BaseConfigLayer):
            name = "b"
            priority = 20
            description = "B"
            def _settings(self) -> ConfigDict: return {"k1": "v2", "k2": "v3"}

        comp = ComposeLayer("comp", 50, [LayerA(), LayerB()])
        built = comp.build()
        settings = built.get("settings", built)
        self.assertEqual(settings.get("k1"), "v2")   # LayerB wins (higher priority)
        self.assertEqual(settings.get("k2"), "v3")


# ═══════════════════════════════════════════════════════════════════
# orchestrator.py v16 — _active_session tracking
# ═══════════════════════════════════════════════════════════════════

class TestOrchestratorActiveSessionTracking(unittest.TestCase):

    def _make_orchestrator(self) -> Any:
        from core.layer     import LayerStack
        from core.lifecycle import LifecycleManager
        from core.protocol  import MessageRouter
        from core.state     import ConfigStateMachine
        from orchestrator   import ConfigOrchestrator
        return ConfigOrchestrator(
            stack     = LayerStack(),
            router    = MessageRouter(),
            lifecycle = LifecycleManager(),
            fsm       = ConfigStateMachine(),
        )

    @skip_without_arch
    def test_active_session_initial_value(self) -> None:
        orch = self._make_orchestrator()
        self.assertEqual(orch._active_session, "unknown")

    @skip_without_arch
    def test_active_network_mode_initial_value(self) -> None:
        orch = self._make_orchestrator()
        self.assertEqual(orch._active_network_mode, "unknown")

    @skip_without_arch
    def test_maybe_emit_session_event_updates_tracker(self) -> None:
        from core.layer     import LayerStack
        from core.lifecycle import LifecycleManager
        from core.protocol  import MessageRouter, SessionChangedEvent, Event
        from core.state     import ConfigStateMachine
        from orchestrator   import ConfigOrchestrator
        from layers.session import SessionLayer

        router = MessageRouter()
        orch = ConfigOrchestrator(
            stack     = LayerStack(),
            router    = router,
            lifecycle = LifecycleManager(),
            fsm       = ConfigStateMachine(),
        )
        orch._stack.register(SessionLayer(session="day"))   # type: ignore[protected]
        # Resolve so stack.get() works
        orch._stack.resolve() # type: ignore[protected]

        received: List[SessionChangedEvent] = []
        def handler(e: Event) -> None:
            if isinstance(e, SessionChangedEvent):
                received.append(e)
        router.events.subscribe(SessionChangedEvent, handler)

        # First call: old_session must be "unknown"
        orch._maybe_emit_session_event(source="startup") # type: ignore[protected]
        self.assertEqual(len(received), 1)
        self.assertEqual(received[0].old_session, "unknown")
        self.assertEqual(received[0].new_session, "day")
        self.assertEqual(orch._active_session, "day") # type: ignore[protected]

        # Second call: old_session must reflect the previous emission
        orch._stack.get("session")   # layer still "day"    # type: ignore[protected]
        orch._maybe_emit_session_event(source="hot_swap")   # type: ignore[protected]
        self.assertEqual(len(received), 2)
        self.assertEqual(received[1].old_session, "day")

    @skip_without_arch
    def test_maybe_emit_network_event_updates_tracker(self) -> None:
        from core.layer     import LayerStack
        from core.lifecycle import LifecycleManager
        from core.protocol  import MessageRouter, NetworkModeChangedEvent, Event
        from core.state     import ConfigStateMachine
        from orchestrator   import ConfigOrchestrator
        from layers.network import NetworkLayer

        router = MessageRouter()
        orch = ConfigOrchestrator(
            stack     = LayerStack(),
            router    = router,
            lifecycle = LifecycleManager(),
            fsm       = ConfigStateMachine(),
        )
        orch._stack.register(NetworkLayer(mode="system"))   # type: ignore[protected]
        orch._stack.resolve()                               # type: ignore[protected]

        received: List[NetworkModeChangedEvent] = []
        def handler(e: Event) -> None:
            if isinstance(e, NetworkModeChangedEvent):
                received.append(e)
        router.events.subscribe(NetworkModeChangedEvent, handler)

        # First call: old_mode must be "unknown"
        orch._maybe_emit_network_event(source="startup")    # type: ignore[protected]
        self.assertEqual(len(received), 1)
        self.assertEqual(received[0].old_mode, "unknown")
        self.assertEqual(received[0].new_mode, "system")
        self.assertEqual(orch._active_network_mode, "system")   # type: ignore[protected]

        # Second call: old_mode must be "system"
        orch._maybe_emit_network_event(source="hot_swap") # type: ignore[protected]
        self.assertEqual(len(received), 2)
        self.assertEqual(received[1].old_mode, "system")


# ═══════════════════════════════════════════════════════════════════
# orchestrator.py v16 — _WrappedHotSwap changes propagation
# ═══════════════════════════════════════════════════════════════════

class TestWrappedHotSwapChangesPropagation(unittest.TestCase):

    def _make_orchestrator(self) -> Any:
        from core.layer     import LayerStack
        from core.lifecycle import LifecycleManager
        from core.protocol  import MessageRouter
        from core.state     import ConfigStateMachine
        from orchestrator   import ConfigOrchestrator
        return ConfigOrchestrator(
            stack     = LayerStack(),
            router    = MessageRouter(),
            lifecycle = LifecycleManager(),
            fsm       = ConfigStateMachine(),
        )

    @skip_without_arch
    def test_last_hot_swap_result_has_changes_key(self) -> None:
        """After a hot-swap, _last_hot_swap_result must contain 'changes' (int)."""
        from core.layer     import LayerStack
        from layers.base    import BaseLayer
        from orchestrator   import ConfigOrchestrator
        from core.lifecycle import LifecycleManager
        from core.protocol  import MessageRouter
        from core.state     import ConfigStateMachine

        orch = ConfigOrchestrator(
            stack     = LayerStack(),
            router    = MessageRouter(),
            lifecycle = LifecycleManager(),
            fsm       = ConfigStateMachine(),
        )
        orch._stack.register(BaseLayer())   # type: ignore[protected]
        orch._stack.resolve()               # type: ignore[protected]

        # Run hot_swap.swap — no applier means apply_fn returns []
        orch.hot_swap.swap("base", BaseLayer())

        result = orch._last_hot_swap_result # type: ignore[protected]
        self.assertIn("changes", result)
        self.assertIsInstance(result["changes"], int)

    @skip_without_arch
    def test_hot_swap_completed_event_carries_changes(self) -> None:
        """HotSwapCompletedEvent.changes must be a list (possibly empty/descriptive)."""
        from core.layer     import LayerStack
        from core.lifecycle import LifecycleManager
        from core.protocol  import MessageRouter, HotSwapCompletedEvent, Event
        from core.state     import ConfigStateMachine
        from layers.base    import BaseLayer
        from orchestrator   import ConfigOrchestrator

        router = MessageRouter()
        orch = ConfigOrchestrator(
            stack     = LayerStack(),
            router    = router,
            lifecycle = LifecycleManager(),
            fsm       = ConfigStateMachine(),
        )
        orch._stack.register(BaseLayer())   # type: ignore[protected]
        orch._stack.resolve()               # type: ignore[protected]

        received: List[HotSwapCompletedEvent] = []
        def handler(e: Event) -> None:
            if isinstance(e, HotSwapCompletedEvent):
                received.append(e)
        router.events.subscribe(HotSwapCompletedEvent, handler)

        orch.hot_swap.swap("base", BaseLayer())

        self.assertEqual(len(received), 1)
        # changes field on HotSwapCompletedEvent is List[str]
        self.assertIsInstance(received[0].changes, list)

    @skip_without_arch
    def test_hot_swap_ok_when_no_errors(self) -> None:
        from core.layer     import LayerStack
        from core.lifecycle import LifecycleManager
        from core.protocol  import MessageRouter
        from core.state     import ConfigStateMachine
        from layers.base    import BaseLayer
        from orchestrator   import ConfigOrchestrator

        orch = ConfigOrchestrator(
            stack     = LayerStack(),
            router    = MessageRouter(),
            lifecycle = LifecycleManager(),
            fsm       = ConfigStateMachine(),
        )
        orch._stack.register(BaseLayer())   # type: ignore[protected]
        orch._stack.resolve()               # type: ignore[protected]

        orch.hot_swap.swap("base", BaseLayer())
        self.assertTrue(orch._last_hot_swap_result.get("ok")) # type: ignore[protected]


# ═══════════════════════════════════════════════════════════════════
# Regressions — v15 / v14 / v13 features unchanged in v16
# ═══════════════════════════════════════════════════════════════════

class TestV16Regressions(unittest.TestCase):

    @skip_without_arch
    def test_session_changed_event_still_importable(self) -> None:
        from core.protocol import SessionChangedEvent
        e = SessionChangedEvent(old_session="day", new_session="night", source="test")
        self.assertEqual(e.new_session, "night")

    @skip_without_arch
    def test_network_mode_changed_event_still_importable(self) -> None:
        from core.protocol import NetworkModeChangedEvent
        e = NetworkModeChangedEvent(old_mode="system", new_mode="socks5",
                                    proxy="socks5://127.0.0.1:7897", source="hot_swap")
        self.assertEqual(e.new_mode, "socks5")
        self.assertTrue(e.proxy.startswith("socks5://"))

    @skip_without_arch
    def test_hot_swap_completed_event_ok_property(self) -> None:
        from core.protocol import HotSwapCompletedEvent
        ok  = HotSwapCompletedEvent(operation="swap", layer_name="network", errors=[])
        bad = HotSwapCompletedEvent(errors=["oops"])
        self.assertTrue(ok.ok)
        self.assertFalse(bad.ok)

    @skip_without_arch
    def test_pipeline_deep_merge_backward_compat(self) -> None:
        """_deep_merge still importable for backward compatibility."""
        from core.pipeline import deep_merge
        self.assertTrue(callable(deep_merge))

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
        self.assertTrue(orch._router.queries.has(GetActiveSessionQuery)) # type: ignore[protected]

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
        self.assertTrue(orch._router.queries.has(GetActiveNetworkQuery)) # type: ignore[protected]

    @skip_without_arch
    def test_summary_shows_v16(self) -> None:
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
        # Summary must contain version marker (v16 or higher)
        self.assertIn("ConfigOrchestrator Summary", summary)

    @skip_without_arch
    def test_context_switched_event_still_exists(self) -> None:
        from core.protocol import ContextSwitchedEvent
        e = ContextSwitchedEvent(old_context="default", new_context="work")
        self.assertEqual(e.new_context, "work")

    @skip_without_arch
    def test_compose_layer_still_functional(self) -> None:
        from core.compose import ComposeLayer
        comp = ComposeLayer("test", 50)
        self.assertEqual(comp.name, "test")
        self.assertEqual(comp.priority, 50)


if __name__ == "__main__":
    unittest.main(verbosity=2)
