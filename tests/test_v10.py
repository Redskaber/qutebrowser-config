"""
tests/test_v10.py
=================
v10 regression and feature tests.

Covers:
  - Bug fix: _handle_get_layer_names variable shadowing (v10)
  - Bug fix: LayerStack._layers property added (v10)
  - core/__init__.py complete export surface (v10)
  - FilterStage pipeline stage (implemented v5, tested v10)
  - LayerRecord accessible from core package (v10)
  - GetLayerNamesQuery end-to-end via QueryBus (v10)
  - Package import integrity (all sub-packages importable)

Run: python3 -m pytest tests/test_v10.py -v
"""

from __future__ import annotations

import sys
import os
import unittest
from typing import Any, Dict

_here = os.path.dirname(os.path.abspath(__file__))
_root = os.path.dirname(_here)
if _root not in sys.path:
    sys.path.insert(0, _root)


# ═════════════════════════════════════════════════════════════════════════════
# Package Import Surface Tests
# ═════════════════════════════════════════════════════════════════════════════
class TestPackageImports(unittest.TestCase):

    def test_core_package_importable(self) -> None:
        import core
        self.assertTrue(hasattr(core, "__all__"))

    def test_core_exports_layer_stack(self) -> None:
        from core import LayerStack
        self.assertTrue(callable(LayerStack))

    def test_core_exports_layer_record(self) -> None:
        from core import LayerRecord
        self.assertTrue(callable(LayerRecord))

    def test_core_exports_filter_stage(self) -> None:
        from core import FilterStage
        self.assertTrue(callable(FilterStage))

    def test_core_exports_all_health_checks(self) -> None:
        import core
        check_names = [
            "BlockingEnabledCheck", "BlockingListCheck",
            "SearchEngineDefaultCheck", "SearchEngineUrlCheck",
            "WebRTCPolicyCheck", "CookieAcceptCheck",
            "StartPageCheck", "EditorCommandCheck",
            "DownloadDirCheck", "TabTitleFormatCheck",
            "ProxySchemeCheck", "ZoomDefaultCheck",
            "FontFamilyCheck", "SpellcheckLangCheck",
            "ContentHeaderCheck",
            "SearchEngineCountCheck", "ProxySchemeDetailCheck",
            "DownloadPromptCheck",
        ]
        for name in check_names:
            with self.subTest(check=name):
                self.assertIn(name, core.__all__)
                self.assertTrue(hasattr(core, name))

    def test_layers_package_importable(self) -> None:
        import layers
        self.assertIsNotNone(layers)

    def test_strategies_package_importable(self) -> None:
        import strategies
        self.assertIsNotNone(strategies)

    def test_policies_package_importable(self) -> None:
        import policies
        self.assertIsNotNone(policies)

    def test_themes_package_importable(self) -> None:
        import themes
        self.assertIsNotNone(themes)

    def test_keybindings_package_importable(self) -> None:
        import keybindings
        self.assertIsNotNone(keybindings)


# ═════════════════════════════════════════════════════════════════════════════
# LayerStack._layers Bug Fix (v10)
# ═════════════════════════════════════════════════════════════════════════════
class TestLayerStackLayersProperty(unittest.TestCase):
    """
    v10 fix: LayerStack._layers is a public alias for _records.
    Required for orchestrator._handle_get_layer_names.
    """

    def setUp(self) -> None:
        from core.layer import LayerStack, BaseConfigLayer

        class LayerA(BaseConfigLayer):
            name = "a"
            priority = 10
            def _settings(self) -> Dict[str, Any]:
                return {"key_a": "val"}

        class LayerB(BaseConfigLayer):
            name = "b"
            priority = 30
            def _settings(self) -> Dict[str, Any]:
                return {"key_b": "val"}

        self.stack = LayerStack()
        self.stack.register(LayerA())
        self.stack.register(LayerB())

    def test_layers_property_returns_records(self) -> None:
        from core.layer import LayerRecord
        layers = self.stack._layers # type: ignore
        self.assertIsInstance(layers, list)
        self.assertTrue(all(isinstance(r, LayerRecord) for r in layers)) # type: ignore

    def test_layers_sorted_by_priority(self) -> None:
        priorities = [r.layer.priority for r in self.stack._layers] # type: ignore
        self.assertEqual(priorities, sorted(priorities))

    def test_layers_count_matches_registered(self) -> None:
        self.assertEqual(len(self.stack._layers), 2) # type: ignore

    def test_layers_names_correct(self) -> None:
        names = [r.layer.name for r in self.stack._layers] # type: ignore
        self.assertIn("a", names)
        self.assertIn("b", names)

    def test_layers_is_same_object_as_records(self) -> None:
        """_layers must be the same list object as _records."""
        self.assertIs(self.stack._layers, self.stack._records) # type: ignore


# ═════════════════════════════════════════════════════════════════════════════
# GetLayerNamesQuery End-to-End (v10)
# ═════════════════════════════════════════════════════════════════════════════
class TestGetLayerNamesQuery(unittest.TestCase):
    """
    End-to-end: QueryBus → _handle_get_layer_names uses _layers correctly.

    Catches the v9 variable-shadowing bug where the comprehension iterated
    as `for layer in ...` but filtered with `if rec.enabled` — different
    names, so the filter was always from the outer scope (last loop var),
    causing wrong or erroneous results.
    """

    def setUp(self) -> None:
        from core.layer import LayerStack, BaseConfigLayer
        from core.protocol import MessageRouter
        from core.state import ConfigStateMachine
        from core.lifecycle import LifecycleManager
        from core.strategy import PolicyChain
        from orchestrator import ConfigOrchestrator

        class LayerX(BaseConfigLayer):
            name = "x"
            priority = 10
            def _settings(self) -> Dict[str, Any]:
                return {"zoom.default": "100%"}

        class LayerY(BaseConfigLayer):
            name = "y"
            priority = 20
            def _settings(self) -> Dict[str, Any]:
                return {"content.javascript.enabled": True}

        stack = LayerStack()
        stack.register(LayerX())
        stack.register(LayerY())

        self.stack = stack
        self.orch = ConfigOrchestrator(
            stack=stack,
            router=MessageRouter(),
            fsm=ConfigStateMachine(),
            lifecycle=LifecycleManager(),
            policy_chain=PolicyChain(),
        )

    def test_query_returns_list(self) -> None:
        from core.protocol import GetLayerNamesQuery
        result = self.orch._router.ask(GetLayerNamesQuery()) # type: ignore
        self.assertIsInstance(result, list)

    def test_query_returns_correct_names(self) -> None:
        from core.protocol import GetLayerNamesQuery
        names = self.orch._router.ask(GetLayerNamesQuery()) # type: ignore
        self.assertIn("x", names)
        self.assertIn("y", names)

    def test_query_returns_priority_ordered(self) -> None:
        from core.protocol import GetLayerNamesQuery
        names = self.orch._router.ask(GetLayerNamesQuery()) # type: ignore
        self.assertLess(names.index("x"), names.index("y"))

    def test_disabled_layer_excluded(self) -> None:
        from core.protocol import GetLayerNamesQuery
        self.stack.disable("y")
        names = self.orch._router.ask(GetLayerNamesQuery()) # type: ignore
        self.assertNotIn("y", names)
        self.assertIn("x", names)

    def test_all_layers_present_when_all_enabled(self) -> None:
        from core.protocol import GetLayerNamesQuery
        names = self.orch._router.ask(GetLayerNamesQuery()) # type: ignore
        self.assertEqual(len(names), 2)


# ═════════════════════════════════════════════════════════════════════════════
# FilterStage Pipeline Tests (v10)
# ═════════════════════════════════════════════════════════════════════════════
class TestFilterStage(unittest.TestCase):
    """FilterStage was implemented in v5 but lacked dedicated tests until v10."""

    def _make_packet(self, data: Dict[str, Any]) -> Any:
        from core.pipeline import ConfigPacket
        return ConfigPacket(source="test", data=data)

    def _make_pipe_with_filter(self, predicate: Any, label: str = "t") -> Any:
        from core.pipeline import FilterStage, Pipeline
        return Pipeline("test").pipe(FilterStage(predicate=predicate, label=label))

    def test_filter_removes_matching_keys(self) -> None:
        pipe = self._make_pipe_with_filter(
            lambda k, v: not k.startswith("_"), "no_private" # type: ignore
        )
        pkt = self._make_packet({"public": 1, "_private": 2, "__dunder": 3})
        result = pipe.run(pkt)
        self.assertIn("public", result.data)
        self.assertNotIn("_private", result.data)
        self.assertNotIn("__dunder", result.data)

    def test_filter_keeps_all_when_predicate_always_true(self) -> None:
        pipe = self._make_pipe_with_filter(lambda k, v: True) # type: ignore
        pkt = self._make_packet({"a": 1, "b": 2})
        result = pipe.run(pkt)
        self.assertEqual(set(result.data.keys()), {"a", "b"})

    def test_filter_removes_all_when_predicate_always_false(self) -> None:
        pipe = self._make_pipe_with_filter(lambda k, v: False) # type: ignore
        pkt = self._make_packet({"a": 1, "b": 2})
        result = pipe.run(pkt)
        self.assertEqual(result.data, {})

    def test_filter_by_value_type(self) -> None:
        pipe = self._make_pipe_with_filter(lambda k, v: isinstance(v, str)) # type: ignore
        pkt = self._make_packet({"name": "alice", "age": 30, "active": True})
        result = pipe.run(pkt)
        self.assertEqual(result.data, {"name": "alice"})

    def test_filter_does_not_mutate_original_packet(self) -> None:
        pipe = self._make_pipe_with_filter(lambda k, v: k != "remove_me") # type: ignore
        orig = self._make_packet({"keep": 1, "remove_me": 2})
        result = pipe.run(orig)
        self.assertIn("remove_me", orig.data)
        self.assertNotIn("remove_me", result.data)

    def test_filter_empty_packet_returns_empty(self) -> None:
        pipe = self._make_pipe_with_filter(lambda k, v: True) # type: ignore
        pkt = self._make_packet({})
        result = pipe.run(pkt)
        self.assertEqual(result.data, {})

    def test_filter_preserves_errors_and_warnings(self) -> None:
        from core.pipeline import FilterStage, Pipeline
        pipe = Pipeline("t").pipe(FilterStage(lambda k, v: True, "passthru"))
        from core.pipeline import ConfigPacket
        pkt = ConfigPacket(
            source="t",
            data={"x": 1},
            errors=["err1"],
            warnings=["warn1"],
        )
        result = pipe.run(pkt)
        self.assertEqual(result.errors, ["err1"])
        self.assertEqual(result.warnings, ["warn1"])


# ═════════════════════════════════════════════════════════════════════════════
# core.__init__ Public Surface Completeness
# ═════════════════════════════════════════════════════════════════════════════
class TestCorePublicSurface(unittest.TestCase):

    def setUp(self) -> None:
        import core
        self.core = core

    def _assert_exported(self, *names: str) -> None:
        for name in names:
            with self.subTest(name=name):
                self.assertIn(name, self.core.__all__)
                self.assertTrue(hasattr(self.core, name))

    def test_layer_types_exported(self) -> None:
        self._assert_exported(
            "LayerProtocol", "LayerStack", "BaseConfigLayer", "LayerRecord"
        )

    def test_pipeline_types_exported(self) -> None:
        self._assert_exported(
            "ConfigPacket", "Pipeline", "PipeStage",
            "LogStage", "ValidateStage", "TransformStage",
            "FilterStage", "MergeStage",
        )

    def test_protocol_buses_exported(self) -> None:
        self._assert_exported(
            "EventBus", "CommandBus", "QueryBus", "MessageRouter"
        )

    def test_fsm_types_exported(self) -> None:
        self._assert_exported(
            "ConfigState", "ConfigEvent", "ConfigStateMachine"
        )

    def test_lifecycle_types_exported(self) -> None:
        self._assert_exported("LifecycleHook", "LifecycleManager")

    def test_strategy_types_exported(self) -> None:
        self._assert_exported(
            "Strategy", "StrategyRegistry",
            "Policy", "PolicyAction", "PolicyChain", "PolicyDecision",
        )

    def test_health_types_exported(self) -> None:
        self._assert_exported(
            "HealthCheck", "HealthChecker", "HealthIssue",
            "HealthReport", "Severity",
        )

    def test_incremental_types_exported(self) -> None:
        self._assert_exported(
            "ChangeKind", "ConfigChange", "ConfigDiffer",
            "ConfigSnapshot", "IncrementalApplier", "SnapshotStore",
        )

    def test_v9_events_exported(self) -> None:
        self._assert_exported(
            "ConfigReloadedEvent", "SnapshotTakenEvent",
            "LayerConflictEvent", "PolicyDeniedEvent", "MetricsEvent",
        )

    def test_v9_queries_exported(self) -> None:
        self._assert_exported(
            "GetSnapshotQuery", "GetLayerDiffQuery", "GetLayerNamesQuery",
        )

    def test_all_symbols_importable_from_package(self) -> None:
        """Every symbol in __all__ must be importable as `from core import X`."""
        import core
        for name in core.__all__:
            with self.subTest(name=name):
                obj = getattr(core, name, None)
                self.assertIsNotNone(obj, f"core.{name} is None")


# ═════════════════════════════════════════════════════════════════════════════
# Runner
# ═════════════════════════════════════════════════════════════════════════════
if __name__ == "__main__":
    print("=" * 60)
    print("qutebrowser config v10 tests")
    print("=" * 60)
    unittest.main(verbosity=2)
