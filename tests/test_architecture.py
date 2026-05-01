"""
tests/test_architecture.py
==========================
Architecture validation tests.

These run without qutebrowser — pure Python unit tests.
Run: python -m pytest tests/ -v
  or: python tests/test_architecture.py
"""

from __future__ import annotations

import sys
import os
import unittest

# Make project importable
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


# ─────────────────────────────────────────────
# Core: Pipeline
# ─────────────────────────────────────────────

class TestPipeline(unittest.TestCase):

    def setUp(self):
        from core.pipeline import (
            ConfigPacket, Pipeline, MergeStage,
            TransformStage, LogStage, ValidateStage,
        )
        self.ConfigPacket = ConfigPacket
        self.Pipeline = Pipeline
        self.MergeStage = MergeStage
        self.TransformStage = TransformStage
        self.LogStage = LogStage
        self.ValidateStage = ValidateStage

    def _packet(self, data=None, source="test"):
        return self.ConfigPacket(source=source, data=data or {})

    def test_empty_pipeline_passthrough(self):
        p = self.Pipeline("test")
        packet = self._packet({"a": 1})
        result = p.run(packet)
        self.assertEqual(result.data, {"a": 1})
        self.assertTrue(result.ok)

    def test_merge_stage(self):
        p = self.Pipeline("test").pipe(self.MergeStage({"b": 2}))
        result = p.run(self._packet({"a": 1}))
        self.assertEqual(result.data, {"a": 1, "b": 2})

    def test_merge_stage_override(self):
        p = self.Pipeline("test").pipe(self.MergeStage({"a": 99}))
        result = p.run(self._packet({"a": 1}))
        self.assertEqual(result.data["a"], 99)

    def test_transform_stage(self):
        def upper_keys(d):
            return {k.upper(): v for k, v in d.items()}
        p = self.Pipeline("t").pipe(self.TransformStage(upper_keys, "upper"))
        result = p.run(self._packet({"hello": "world"}))
        self.assertIn("HELLO", result.data)

    def test_transform_exception_becomes_error(self):
        def boom(d):
            raise ValueError("kaboom")
        p = self.Pipeline("t").pipe(self.TransformStage(boom, "boom"))
        result = p.run(self._packet({"x": 1}))
        self.assertFalse(result.ok)
        self.assertTrue(any("kaboom" in e for e in result.errors))

    def test_pipeline_chaining(self):
        p = (
            self.Pipeline("chain")
            .pipe(self.MergeStage({"b": 2}))
            .pipe(self.MergeStage({"c": 3}))
        )
        result = p.run(self._packet({"a": 1}))
        self.assertEqual(result.data, {"a": 1, "b": 2, "c": 3})

    def test_validate_stage_warns(self):
        rules = {"x": lambda v: isinstance(v, int)}
        p = self.Pipeline("v").pipe(self.ValidateStage(rules))
        result = p.run(self._packet({"x": "not-int"}))
        self.assertTrue(len(result.warnings) > 0)
        self.assertTrue(result.ok)  # warnings don't fail

    def test_packet_immutability(self):
        from core.pipeline import ConfigPacket
        p = ConfigPacket(source="s", data={"a": 1})
        p2 = p.with_data({"b": 2})
        # original unchanged
        self.assertNotIn("b", p.data)
        self.assertIn("b", p2.data)


# ─────────────────────────────────────────────
# Core: State Machine
# ─────────────────────────────────────────────

class TestStateMachine(unittest.TestCase):

    def setUp(self):
        from core.state import ConfigStateMachine, ConfigState, ConfigEvent
        self.FSM = ConfigStateMachine
        self.State = ConfigState
        self.Event = ConfigEvent

    def test_initial_state(self):
        fsm = self.FSM()
        self.assertEqual(fsm.state, self.State.IDLE)

    def test_valid_transition(self):
        fsm = self.FSM()
        ok = fsm.send(self.Event.START_LOAD)
        self.assertTrue(ok)
        self.assertEqual(fsm.state, self.State.LOADING)

    def test_invalid_transition_returns_false(self):
        fsm = self.FSM()
        # Can't VALIDATE_DONE from IDLE
        ok = fsm.send(self.Event.VALIDATE_DONE)
        self.assertFalse(ok)
        self.assertEqual(fsm.state, self.State.IDLE)

    def test_full_happy_path(self):
        fsm = self.FSM()
        E = self.Event
        S = self.State
        path = [
            (E.START_LOAD,    S.LOADING),
            (E.LOAD_DONE,     S.VALIDATING),
            (E.VALIDATE_DONE, S.APPLYING),
            (E.APPLY_DONE,    S.ACTIVE),
        ]
        for event, expected_state in path:
            fsm.send(event)
            self.assertEqual(fsm.state, expected_state, f"after {event.name}")

    def test_error_recovery_via_reload(self):
        fsm = self.FSM()
        E = self.Event
        S = self.State
        fsm.send(E.START_LOAD)
        fsm.send(E.LOAD_FAILED)
        self.assertEqual(fsm.state, S.ERROR)
        fsm.send(E.RELOAD)
        self.assertEqual(fsm.state, S.RELOADING)

    def test_observer_called(self):
        observed = []
        fsm = self.FSM()
        fsm.on_transition(lambda f, t, e: observed.append((f, t, e)))
        fsm.send(self.Event.START_LOAD)
        self.assertEqual(len(observed), 1)
        self.assertEqual(observed[0][1], self.State.LOADING)

    def test_entry_action_called(self):
        entered = []
        fsm = self.FSM()
        fsm.on_enter(self.State.LOADING, lambda ctx: entered.append(ctx.current))
        fsm.send(self.Event.START_LOAD)
        self.assertEqual(len(entered), 1)


# ─────────────────────────────────────────────
# Core: Protocol / EventBus
# ─────────────────────────────────────────────

class TestEventBus(unittest.TestCase):

    def setUp(self):
        from core.protocol import EventBus, LayerAppliedEvent, ConfigErrorEvent
        self.EventBus = EventBus
        self.LayerAppliedEvent = LayerAppliedEvent
        self.ConfigErrorEvent = ConfigErrorEvent

    def test_subscribe_and_publish(self):
        bus = self.EventBus()
        received = []
        bus.subscribe(self.LayerAppliedEvent, received.append)
        bus.publish(self.LayerAppliedEvent(layer_name="base", key_count=5))
        self.assertEqual(len(received), 1)
        self.assertEqual(received[0].layer_name, "base")

    def test_no_subscribers_no_error(self):
        bus = self.EventBus()
        count = bus.publish(self.LayerAppliedEvent())
        self.assertEqual(count, 0)

    def test_wildcard_subscriber(self):
        bus = self.EventBus()
        received = []
        bus.subscribe_all(received.append)
        bus.publish(self.LayerAppliedEvent())
        bus.publish(self.ConfigErrorEvent())
        self.assertEqual(len(received), 2)

    def test_unsubscribe(self):
        bus = self.EventBus()
        received = []
        bus.subscribe(self.LayerAppliedEvent, received.append)
        bus.unsubscribe(self.LayerAppliedEvent, received.append)
        bus.publish(self.LayerAppliedEvent())
        self.assertEqual(len(received), 0)

    def test_handler_exception_doesnt_crash_bus(self):
        bus = self.EventBus()
        def bad_handler(e):
            raise RuntimeError("oops")
        bus.subscribe(self.LayerAppliedEvent, bad_handler)
        # Should not raise
        count = bus.publish(self.LayerAppliedEvent())
        self.assertEqual(count, 0)  # handler failed, count=0


# ─────────────────────────────────────────────
# Core: Layer Stack
# ─────────────────────────────────────────────

class TestLayerStack(unittest.TestCase):

    def setUp(self):
        from core.layer import LayerStack, BaseConfigLayer

        class TestLayer(BaseConfigLayer):
            def __init__(self, n, p, data):
                self.name = n
                self.priority = p
                self._data = data
            def _settings(self):
                return self._data

        self.LayerStack = LayerStack
        self.TestLayer = TestLayer

    def test_single_layer(self):
        stack = self.LayerStack()
        stack.register(self.TestLayer("a", 10, {"x": 1}))
        stack.resolve()
        self.assertEqual(stack.merged["settings"]["x"], 1)

    def test_priority_ordering(self):
        stack = self.LayerStack()
        # Higher priority (50) should override lower (10)
        stack.register(self.TestLayer("low",  10, {"x": 1}))
        stack.register(self.TestLayer("high", 50, {"x": 99}))
        stack.resolve()
        self.assertEqual(stack.merged["settings"]["x"], 99)

    def test_disable_layer(self):
        stack = self.LayerStack()
        stack.register(self.TestLayer("a", 10, {"x": 1}))
        stack.register(self.TestLayer("b", 20, {"x": 99}))
        stack.disable("b")
        stack.resolve()
        self.assertEqual(stack.merged["settings"]["x"], 1)

    def test_enable_layer(self):
        stack = self.LayerStack()
        stack.register(self.TestLayer("a", 10, {"x": 1}))
        stack.register(self.TestLayer("b", 20, {"x": 99}), enabled=False)
        stack.enable("b")
        stack.resolve()
        self.assertEqual(stack.merged["settings"]["x"], 99)


# ─────────────────────────────────────────────
# Core: Policy Chain
# ─────────────────────────────────────────────

class TestPolicyChain(unittest.TestCase):

    def setUp(self):
        from core.strategy import (
            PolicyChain, ReadOnlyPolicy, TypeEnforcePolicy,
            RangePolicy, PolicyAction,
        )
        self.PolicyChain = PolicyChain
        self.ReadOnlyPolicy = ReadOnlyPolicy
        self.TypeEnforcePolicy = TypeEnforcePolicy
        self.RangePolicy = RangePolicy
        self.PolicyAction = PolicyAction

    def test_allow_by_default(self):
        chain = self.PolicyChain()
        decision = chain.evaluate("key", "value", {})
        self.assertEqual(decision.action, self.PolicyAction.ALLOW)

    def test_readonly_policy_denies(self):
        chain = self.PolicyChain()
        chain.add(self.ReadOnlyPolicy(["protected_key"]))
        decision = chain.evaluate("protected_key", "x", {})
        self.assertEqual(decision.action, self.PolicyAction.DENY)

    def test_readonly_policy_allows_others(self):
        chain = self.PolicyChain()
        chain.add(self.ReadOnlyPolicy(["protected_key"]))
        decision = chain.evaluate("other_key", "x", {})
        self.assertEqual(decision.action, self.PolicyAction.ALLOW)

    def test_type_enforce_warns(self):
        chain = self.PolicyChain()
        chain.add(self.TypeEnforcePolicy({"count": int}))
        decision = chain.evaluate("count", "not-int", {})
        self.assertEqual(decision.action, self.PolicyAction.WARN)

    def test_range_policy_clamps(self):
        chain = self.PolicyChain()
        chain.add(self.RangePolicy({"zoom": (50, 200)}))
        decision = chain.evaluate("zoom", 300, {})
        self.assertEqual(decision.action, self.PolicyAction.MODIFY)
        self.assertEqual(decision.modified_value, 200)


# ─────────────────────────────────────────────
# Layers: Base
# ─────────────────────────────────────────────

class TestBaseLayer(unittest.TestCase):

    def setUp(self):
        from layers.base import BaseLayer
        self.layer = BaseLayer()

    def test_build_returns_dict(self):
        data = self.layer.build()
        self.assertIsInstance(data, dict)

    def test_has_settings(self):
        data = self.layer.build()
        self.assertIn("settings", data)
        settings = data["settings"]
        self.assertIn("url.searchengines", settings)
        self.assertIn("tabs.background", settings)

    def test_has_keybindings(self):
        data = self.layer.build()
        self.assertIn("keybindings", data)
        bindings = data["keybindings"]
        self.assertIsInstance(bindings, list)
        self.assertTrue(len(bindings) > 0)

    def test_has_aliases(self):
        data = self.layer.build()
        self.assertIn("aliases", data)
        self.assertIn("q", data["aliases"])

    def test_validate_returns_empty_for_valid(self):
        data = self.layer.build()
        errors = self.layer.validate(data)
        self.assertEqual(errors, [])


# ─────────────────────────────────────────────
# Layers: Appearance
# ─────────────────────────────────────────────

class TestAppearanceLayer(unittest.TestCase):

    def test_all_themes_build(self):
        from layers.appearance import AppearanceLayer, THEMES
        for theme_name in THEMES:
            with self.subTest(theme=theme_name):
                layer = AppearanceLayer(theme=theme_name)
                data = layer.build()
                self.assertIn("settings", data)

    def test_unknown_theme_raises(self):
        from layers.appearance import AppearanceLayer
        with self.assertRaises(ValueError):
            AppearanceLayer(theme="nonexistent-theme")

    def test_color_keys_present(self):
        from layers.appearance import AppearanceLayer
        layer = AppearanceLayer()
        data = layer.build()
        settings = data["settings"]
        self.assertIn("colors.statusbar.normal.bg", settings)
        self.assertIn("colors.tabs.selected.odd.bg", settings)
        self.assertIn("fonts.statusbar", settings)


# ─────────────────────────────────────────────
# Layers: Privacy
# ─────────────────────────────────────────────

class TestPrivacyLayer(unittest.TestCase):

    def test_standard_profile(self):
        from layers.privacy import PrivacyLayer, PrivacyProfile
        layer = PrivacyLayer(PrivacyProfile.STANDARD)
        data = layer.build()
        settings = data["settings"]
        self.assertIn("content.blocking.enabled", settings)
        self.assertTrue(settings["content.blocking.enabled"])

    def test_hardened_disables_cookies(self):
        from layers.privacy import PrivacyLayer, PrivacyProfile
        layer = PrivacyLayer(PrivacyProfile.HARDENED)
        settings = layer.build()["settings"]
        self.assertEqual(settings["content.cookies.accept"], "never")

    def test_paranoid_disables_js(self):
        from layers.privacy import PrivacyLayer, PrivacyProfile
        layer = PrivacyLayer(PrivacyProfile.PARANOID)
        settings = layer.build()["settings"]
        self.assertFalse(settings.get("content.javascript.enabled", True))


# ─────────────────────────────────────────────
# Integration: Full stack resolve
# ─────────────────────────────────────────────

class TestFullStack(unittest.TestCase):

    def test_full_stack_resolves(self):
        from core.layer import LayerStack
        from layers.base import BaseLayer
        from layers.privacy import PrivacyLayer, PrivacyProfile
        from layers.appearance import AppearanceLayer
        from layers.behavior import BehaviorLayer
        from layers.performance import PerformanceLayer, PerformanceProfile

        stack = LayerStack()
        stack.register(BaseLayer())
        stack.register(PrivacyLayer(PrivacyProfile.STANDARD))
        stack.register(AppearanceLayer("catppuccin-mocha"))
        stack.register(BehaviorLayer())
        stack.register(PerformanceLayer(PerformanceProfile.BALANCED))

        packets = stack.resolve()

        self.assertEqual(set(packets.keys()),
                         {"base", "privacy", "appearance", "behavior", "performance"})

        merged = stack.merged
        self.assertIn("settings", merged)
        self.assertIn("keybindings", merged)
        self.assertIn("aliases", merged)

    def test_priority_override_in_full_stack(self):
        """Higher-priority layer values override lower-priority ones."""
        from core.layer import LayerStack, BaseConfigLayer

        class LowLayer(BaseConfigLayer):
            name = "low"; priority = 10
            def _settings(self): return {"test_key": "low_value"}

        class HighLayer(BaseConfigLayer):
            name = "high"; priority = 90
            def _settings(self): return {"test_key": "high_value"}

        stack = LayerStack()
        stack.register(LowLayer())
        stack.register(HighLayer())
        stack.resolve()

        self.assertEqual(stack.merged["settings"]["test_key"], "high_value")


# ─────────────────────────────────────────────
# Runner
# ─────────────────────────────────────────────

if __name__ == "__main__":
    print("=" * 60)
    print("qutebrowser config architecture tests")
    print("=" * 60)
    unittest.main(verbosity=2)
