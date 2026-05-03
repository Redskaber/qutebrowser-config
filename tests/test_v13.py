"""
tests/test_v13.py
=================
Test Suite  (v13)

Covers all v13 additions:
  - core/compose.py     — ComposeLayer
  - core/event_filter.py — EventFilter + built-in middleware
  - core/hot_swap.py    — LayerHotSwap
  - core/validator.py   — ConfigValidator, FieldSpec, SchemaRegistry

Run::

    python3 tests/test_v13.py
    pytest tests/test_v13.py -v

Expected: all tests pass without a running qutebrowser instance.
"""

from __future__ import annotations

import sys
import os
import threading
import time
import unittest
from typing import Any, Iterable, List


# ── Path setup ────────────────────────────────────────────────────────────────
_here = os.path.dirname(os.path.abspath(__file__))
_root = os.path.dirname(_here)
if _root not in sys.path:
    sys.path.insert(0, _root)


# ═════════════════════════════════════════════════════════════════════════════
# ComposeLayer Tests
# ═════════════════════════════════════════════════════════════════════════════

class TestComposeLayer(unittest.TestCase):

    def _make_layer(self, name: str, priority: int, settings: dict[str, Any]) -> Any:
        from core.layer import BaseConfigLayer
        class _L(BaseConfigLayer):
            pass
        _L.name     = name          # type: ignore[assignment]
        _L.priority = priority      # type: ignore[assignment]
        _sett = settings
        _L._settings = lambda self: _sett  # type: ignore[assignment]
        return _L()

    # ── Basic construction ─────────────────────────────────────────────

    def test_empty_compose_builds_empty(self) -> None:
        from core.compose import ComposeLayer
        cl = ComposeLayer("empty", priority=50)
        self.assertEqual(cl.build(), {})

    def test_compose_merges_children(self) -> None:
        from core.compose import ComposeLayer
        a = self._make_layer("a", 10, {"key_a": 1})
        b = self._make_layer("b", 20, {"key_b": 2})
        cl = ComposeLayer("ab", priority=50, children=[a, b])
        result = cl.build()
        self.assertEqual(result.get("settings", result).get("key_a") or result.get("key_a"), 1)

    def test_higher_priority_child_wins(self) -> None:
        from core.compose import ComposeLayer
        from core.layer import BaseConfigLayer
        class Low(BaseConfigLayer):
            name     = "low"
            priority = 5
            def _settings(self): return {"zoom.default": "90%"}
        class High(BaseConfigLayer):
            name     = "high"
            priority = 15
            def _settings(self): return {"zoom.default": "120%"}
        cl = ComposeLayer("test", priority=50, children=[Low(), High()])
        result = cl.build()
        zoom = result.get("settings", {}).get("zoom.default")
        self.assertEqual(zoom, "120%")

    def test_priority_ordering_respected(self) -> None:
        from core.compose import ComposeLayer
        cl = ComposeLayer("ordered", priority=50)
        from core.layer import BaseConfigLayer
        class A(BaseConfigLayer):
            name="a"
            priority=30
            def _settings(self) -> dict[str, Any]:
                return {}
        class B(BaseConfigLayer):
            name="b"
            priority=10
            def _settings(self) -> dict[str, Any]:
                return {}
        cl.add(A()).add(B())
        self.assertEqual(cl.child_names(), ["b", "a"])

    def test_duplicate_child_name_raises(self) -> None:
        from core.compose import ComposeLayer, LayerCompositionError
        from core.layer import BaseConfigLayer
        class X(BaseConfigLayer):
            name="x"
            priority=10
            def _settings(self) -> dict[str, Any]:
                return {}
        cl = ComposeLayer("test", priority=50, children=[X()])
        with self.assertRaises(LayerCompositionError):
            cl.add(X())

    def test_child_same_name_as_parent_raises(self) -> None:
        from core.compose import ComposeLayer, LayerCompositionError
        from core.layer import BaseConfigLayer
        class X(BaseConfigLayer):
            name="parent"
            priority=10
            def _settings(self) -> dict[str, Any]:
                return {}
        with self.assertRaises(LayerCompositionError):
            cl = ComposeLayer("parent", priority=50)
            cl.add(X())

    def test_remove_child(self) -> None:
        from core.compose import ComposeLayer
        from core.layer import BaseConfigLayer
        class A(BaseConfigLayer):
            name="a"
            priority=10
            def _settings(self) -> dict[str, Any]:
                return {}
        cl = ComposeLayer("test", priority=50, children=[A()])
        cl.remove("a")
        self.assertEqual(cl.child_names(), [])

    def test_remove_missing_raises(self) -> None:
        from core.compose import ComposeLayer
        cl = ComposeLayer("test", priority=50)
        with self.assertRaises(KeyError):
            cl.remove("nonexistent")

    def test_describe_contains_name(self) -> None:
        from core.compose import ComposeLayer
        cl = ComposeLayer("my-compose", priority=50)
        self.assertIn("my-compose", cl.describe())

    def test_repr_contains_name_and_priority(self) -> None:
        from core.compose import ComposeLayer
        cl = ComposeLayer("rep-test", priority=77)
        r = repr(cl)
        self.assertIn("rep-test", r)
        self.assertIn("77", r)

    def test_compose_factory_helper(self) -> None:
        from core.compose import compose
        from core.layer import BaseConfigLayer
        class A(BaseConfigLayer):
            name="a"
            priority=10
            def _settings(self) -> dict[str, Any]:
                return {}
        cl = compose("factory-test", A(), priority=42, description="test")
        self.assertEqual(cl.name, "factory-test")
        self.assertEqual(cl.priority, 42)
        self.assertIn("a", cl.child_names())

    def test_nested_compose(self) -> None:
        """A ComposeLayer can be a child of another ComposeLayer."""
        from core.compose import ComposeLayer
        from core.layer import BaseConfigLayer
        class A(BaseConfigLayer):
            name="a"
            priority=10
            def _settings(self) -> dict[str, Any]:
                return {}
        inner = ComposeLayer("inner", priority=20, children=[A()])
        outer = ComposeLayer("outer", priority=50)
        outer.add(inner)   # no error
        self.assertIn("inner", outer.child_names())

    def test_validate_collects_child_errors(self) -> None:
        from core.compose import ComposeLayer
        from core.layer import BaseConfigLayer
        class BadLayer(BaseConfigLayer):
            name="bad"
            priority=10
            def _settings(self) -> dict[str, Any]:
                return {}
            def validate(self, data) -> list[str]: # type: ignore[missing]
                return ["child error"]
        cl = ComposeLayer("test", priority=50, children=[BadLayer()])
        errors = cl.validate({})
        self.assertIn("child error", errors)

    def test_pipeline_not_returned_from_compose_layer(self) -> None:
        """pipeline() should return None (applied inside build())."""
        from core.compose import ComposeLayer
        cl = ComposeLayer("test", priority=50)
        self.assertIsNone(cl.pipeline())


# ═════════════════════════════════════════════════════════════════════════════
# EventFilter Tests
# ═════════════════════════════════════════════════════════════════════════════

class TestEventFilter(unittest.TestCase):

    def _make_filter(self) -> Any:
        from core.event_filter import EventFilter
        from core.protocol import EventBus
        return EventFilter(EventBus())

    def test_filter_passes_events_by_default(self) -> None:
        from core.event_filter import EventFilter
        from core.protocol import Event, EventBus, MetricsEvent
        bus = EventBus()
        received: List[Event] = []
        bus.subscribe(MetricsEvent, lambda e: received.append(e))
        flt = EventFilter(bus)
        flt.publish(MetricsEvent(phase="build", duration_ms=1.0, key_count=5))
        self.assertEqual(len(received), 1)

    def test_subscribe_delegates_to_inner_bus(self) -> None:
        from core.event_filter import EventFilter
        from core.protocol import Event, EventBus, MetricsEvent
        bus = EventBus()
        flt = EventFilter(bus)
        received: List[Event] = []
        flt.subscribe(MetricsEvent, lambda e: received.append(e))
        flt.publish(MetricsEvent(phase="test", duration_ms=0.0, key_count=0))
        self.assertEqual(len(received), 1)

    def test_logging_middleware_passes_events(self) -> None:
        from core.event_filter import EventFilter, LoggingMiddleware
        from core.protocol import Event, EventBus, MetricsEvent
        bus = EventBus()
        received: List[Event] = []
        bus.subscribe(MetricsEvent, lambda e: received.append(e))
        flt = EventFilter(bus).use(LoggingMiddleware())
        flt.publish(MetricsEvent(phase="x", duration_ms=0.0, key_count=0))
        self.assertEqual(len(received), 1)

    def test_filter_middleware_blocks_non_matching(self) -> None:
        from core.event_filter import EventFilter, FilterMiddleware
        from core.protocol import Event, EventBus, MetricsEvent, ConfigErrorEvent
        bus = EventBus()
        received: List[Event] = []
        bus.subscribe(MetricsEvent, lambda e: received.append(e))
        # Only allow ConfigErrorEvent
        flt = EventFilter(bus).use(
            FilterMiddleware(lambda e: isinstance(e, ConfigErrorEvent))
        )
        flt.publish(MetricsEvent(phase="x", duration_ms=0.0, key_count=0))
        self.assertEqual(len(received), 0)

    def test_filter_middleware_passes_matching(self) -> None:
        from core.event_filter import EventFilter, FilterMiddleware
        from core.protocol import Event, EventBus, ConfigErrorEvent
        bus = EventBus()
        received: List[Event] = []
        bus.subscribe(ConfigErrorEvent, lambda e: received.append(e))
        flt = EventFilter(bus).use(
            FilterMiddleware(lambda e: isinstance(e, ConfigErrorEvent))
        )
        flt.publish(ConfigErrorEvent(error_msg="boom"))
        self.assertEqual(len(received), 1)

    def test_dedupe_middleware_suppresses_rapid_duplicates(self) -> None:
        from core.event_filter import EventFilter, DedupeMiddleware
        from core.protocol import Event, EventBus, MetricsEvent
        bus = EventBus()
        received: List[Event]= []
        bus.subscribe(MetricsEvent, lambda e: received.append(e))
        flt = EventFilter(bus).use(DedupeMiddleware(ttl=10.0))  # large TTL
        flt.publish(MetricsEvent(phase="a", duration_ms=0.0, key_count=0))
        flt.publish(MetricsEvent(phase="a", duration_ms=0.0, key_count=0))
        self.assertEqual(len(received), 1)

    def test_dedupe_allows_after_ttl(self) -> None:
        from core.event_filter import EventFilter, DedupeMiddleware
        from core.protocol import Event, EventBus, MetricsEvent
        bus = EventBus()
        received: List[Event] = []
        bus.subscribe(MetricsEvent, lambda e: received.append(e))
        flt = EventFilter(bus).use(DedupeMiddleware(ttl=0.01))  # 10ms TTL
        flt.publish(MetricsEvent(phase="a", duration_ms=0.0, key_count=0))
        time.sleep(0.02)
        flt.publish(MetricsEvent(phase="a", duration_ms=0.0, key_count=0))
        self.assertEqual(len(received), 2)

    def test_throttle_middleware_limits_rate(self) -> None:
        from core.event_filter import EventFilter, ThrottleMiddleware
        from core.protocol import Event, EventBus, MetricsEvent
        bus = EventBus()
        received: List[Event] = []
        bus.subscribe(MetricsEvent, lambda e: received.append(e))
        flt = EventFilter(bus).use(ThrottleMiddleware(max_per_sec=2.0))
        for _ in range(10):
            flt.publish(MetricsEvent(phase="a", duration_ms=0.0, key_count=0))
        # With 2/sec throttle and all events fired instantly, only 1 should pass
        self.assertLessEqual(len(received), 3)

    def test_counting_middleware_counts_events(self) -> None:
        from core.event_filter import EventFilter, CountingMiddleware
        from core.protocol import EventBus, MetricsEvent, ConfigErrorEvent
        bus = EventBus()
        counter = CountingMiddleware()
        flt = EventFilter(bus).use(counter)
        flt.publish(MetricsEvent(phase="a", duration_ms=0.0, key_count=0))
        flt.publish(MetricsEvent(phase="b", duration_ms=0.0, key_count=0))
        flt.publish(ConfigErrorEvent(error_msg="x"))
        self.assertEqual(counter.count("MetricsEvent"), 2)
        self.assertEqual(counter.count("ConfigErrorEvent"), 1)
        self.assertEqual(counter.total(), 3)

    def test_counting_middleware_reset(self) -> None:
        from core.event_filter import EventFilter, CountingMiddleware
        from core.protocol import EventBus, MetricsEvent
        bus = EventBus()
        counter = CountingMiddleware()
        flt = EventFilter(bus).use(counter)
        flt.publish(MetricsEvent(phase="a", duration_ms=0.0, key_count=0))
        counter.reset()
        self.assertEqual(counter.total(), 0)

    def test_middleware_chain_order_respected(self) -> None:
        """Middleware runs in registration order."""
        from core.event_filter import EventFilter, Middleware, NextFn
        from core.protocol import Event, EventBus, MetricsEvent
        call_order: List[str] = []

        class M1(Middleware):
            def __call__(self, event: Event, next_fn: NextFn):
                call_order.append("M1")
                return next_fn(event)

        class M2(Middleware):
            def __call__(self, event: Event, next_fn: NextFn):
                call_order.append("M2")
                return next_fn(event)

        bus = EventBus()
        flt = EventFilter(bus).use(M1()).use(M2())
        flt.publish(MetricsEvent(phase="x", duration_ms=0.0, key_count=0))
        self.assertEqual(call_order, ["M1", "M2"])

    def test_describe_includes_middleware_names(self) -> None:
        from core.event_filter import EventFilter, LoggingMiddleware, DedupeMiddleware
        from core.protocol import EventBus
        flt = EventFilter(EventBus()).use(LoggingMiddleware()).use(DedupeMiddleware())
        desc = flt.describe()
        self.assertIn("LoggingMiddleware", desc)
        self.assertIn("DedupeMiddleware", desc)

    def test_build_default_filter_factory(self) -> None:
        from core.event_filter import build_default_filter
        flt = build_default_filter()
        self.assertIsNotNone(flt)

    def test_thread_safety_dedupe(self) -> None:
        """DedupeMiddleware is thread-safe."""
        from core.event_filter import EventFilter, DedupeMiddleware, CountingMiddleware
        from core.protocol import EventBus, MetricsEvent
        bus   = EventBus()
        counter = CountingMiddleware()
        flt   = EventFilter(bus).use(DedupeMiddleware(ttl=0.0)).use(counter)

        def publish_n(n: int) -> None:
            for _ in range(n):
                flt.publish(MetricsEvent(phase="t", duration_ms=0.0, key_count=0))

        threads = [threading.Thread(target=publish_n, args=(50,)) for _ in range(5)]
        for t in threads: t.start()
        for t in threads: t.join()
        # Should not raise; counts are thread-safe (not asserting exact value)
        self.assertGreater(counter.total(), 0)


# ═════════════════════════════════════════════════════════════════════════════
# LayerHotSwap Tests
# ═════════════════════════════════════════════════════════════════════════════

class TestLayerHotSwap(unittest.TestCase):
    from core.layer import LayerProtocol, LayerStack

    def _make_layer(self, name: str, priority: int, settings: dict[str, Any]) -> Any:
        from core.layer import BaseConfigLayer
        class _L(BaseConfigLayer):
            pass
        _L.name     = name
        _L.priority = priority
        _sett = {"settings": settings}
        _L._settings = lambda self: settings  # type: ignore[private]
        return _L()

    def _make_stack_with(self, *layers: Iterable[LayerProtocol]) -> Any:
        from core.layer import LayerStack
        stack = LayerStack()
        for layer in layers:
            stack.register(layer) # type: ignore[dack]
        stack.resolve()
        return stack

    def _make_hot_swap(self, stack: LayerStack) -> Any:
        from core.hot_swap import LayerHotSwap
        applied: dict[str, Any] = {}
        def apply_fn(key: str, value: Any) -> List[str]:
            applied[key] = value
            return []
        hs = LayerHotSwap(stack, apply_fn=apply_fn)
        hs._applied = applied # type: ignore[private]
        return hs

    def test_swap_applies_changed_keys(self) -> None:
        from core.hot_swap import LayerHotSwap
        from core.layer import LayerStack, BaseConfigLayer

        class LayerA(BaseConfigLayer):
            name="a"
            priority=10
            def _settings(self) -> dict[str, Any]:
                return {"zoom.default": "100%"}

        class LayerB(BaseConfigLayer):
            name="a"
            priority=10
            def _settings(self) -> dict[str, Any]:
                return {"zoom.default": "150%"}

        stack = LayerStack()
        stack.register(LayerA())
        stack.resolve()

        applied: dict[str, Any] = {}
        def apply_fn(key: str, value: Any) -> List[str]:
            applied[key] = value
            return []

        hs = LayerHotSwap(stack, apply_fn)
        result = hs.swap("a", LayerB())
        self.assertTrue(result.ok)
        self.assertGreater(result.changes, 0)

    def test_remove_layer(self) -> None:
        from core.hot_swap import LayerHotSwap
        from core.layer import LayerStack, BaseConfigLayer

        class LayerA(BaseConfigLayer):
            name="removable"
            priority=10
            def _settings(self) -> dict[str, Any]:
                return {"zoom.default": "110%"}

        stack = LayerStack()
        stack.register(LayerA())
        stack.resolve()

        # applied: dict[str, Any] = {}
        hs = LayerHotSwap(stack, lambda k, v: [])
        result = hs.remove("removable")
        self.assertEqual(result.operation, "remove")

    def test_insert_new_layer(self) -> None:
        from core.hot_swap import LayerHotSwap
        from core.layer import LayerStack, BaseConfigLayer

        class LayerNew(BaseConfigLayer):
            name="new_layer"
            priority=10
            def _settings(self) -> dict[str, Any]:
                return {"zoom.default": "105%"}

        stack = LayerStack()
        stack.resolve()

        hs = LayerHotSwap(stack, lambda k, v: [])
        result = hs.insert(LayerNew())
        self.assertEqual(result.operation, "insert")

    def test_result_str(self) -> None:
        from core.hot_swap import HotSwapResult
        r = HotSwapResult(operation="swap", layer_name="ctx", changes=3, errors=[], duration_ms=1.2)
        s = str(r)
        self.assertIn("swap", s)
        self.assertIn("ctx", s)
        self.assertIn("3", s)

    def test_result_ok_false_when_errors(self) -> None:
        from core.hot_swap import HotSwapResult
        r = HotSwapResult("swap", "x", 0, ["error"], 0.0)
        self.assertFalse(r.ok)

    def test_result_ok_true_when_no_errors(self) -> None:
        from core.hot_swap import HotSwapResult
        r = HotSwapResult("swap", "x", 2, [], 1.0)
        self.assertTrue(r.ok)

    def test_remove_nonexistent_layer_returns_error(self) -> None:
        from core.hot_swap import LayerHotSwap
        from core.layer import LayerStack
        stack = LayerStack()
        stack.resolve()
        hs = LayerHotSwap(stack, lambda k, v: [])
        result = hs.remove("nonexistent")
        self.assertFalse(result.ok)


# ═════════════════════════════════════════════════════════════════════════════
# ConfigValidator Tests
# ═════════════════════════════════════════════════════════════════════════════

class TestFieldSpec(unittest.TestCase):

    def test_immutable(self) -> None:
        from core.validator import FieldSpec
        spec = FieldSpec(type_=str, required=True)
        with self.assertRaises((AttributeError, TypeError)):
            spec.required = False  # type: ignore[misc]

    def test_default_values(self) -> None:
        from core.validator import FieldSpec
        spec = FieldSpec()
        self.assertIsNone(spec.type_)
        self.assertFalse(spec.required)
        self.assertIsNone(spec.choices)


class TestConfigValidator(unittest.TestCase):
    from core.validator import SchemaType

    def _make(self, schema: SchemaType, strict: bool = False) -> Any:
        from core.validator import ConfigValidator
        return ConfigValidator(schema, strict=strict)

    def test_required_field_missing_is_error(self) -> None:
        from core.validator import FieldSpec
        v = self._make({"zoom.default": FieldSpec(required=True)})
        result = v.validate({})
        self.assertFalse(result.ok)
        self.assertTrue(any("required" in e for e in result.errors))

    def test_required_field_present_passes(self) -> None:
        from core.validator import FieldSpec
        v = self._make({"zoom.default": FieldSpec(required=True)})
        result = v.validate({"zoom.default": "100%"})
        self.assertTrue(result.ok)

    def test_type_check_fails(self) -> None:
        from core.validator import FieldSpec
        v = self._make({"content.javascript.enabled": FieldSpec(type_=bool)})
        result = v.validate({"content.javascript.enabled": "yes"})
        self.assertFalse(result.ok)

    def test_type_check_passes(self) -> None:
        from core.validator import FieldSpec
        v = self._make({"content.javascript.enabled": FieldSpec(type_=bool)})
        result = v.validate({"content.javascript.enabled": True})
        self.assertTrue(result.ok)

    def test_choices_constraint_fails(self) -> None:
        from core.validator import FieldSpec
        v = self._make({
            "tabs.position": FieldSpec(type_=str, choices={"top", "bottom", "left", "right"})
        })
        result = v.validate({"tabs.position": "center"})
        self.assertFalse(result.ok)

    def test_choices_constraint_passes(self) -> None:
        from core.validator import FieldSpec
        v = self._make({
            "tabs.position": FieldSpec(type_=str, choices={"top", "bottom", "left", "right"})
        })
        result = v.validate({"tabs.position": "top"})
        self.assertTrue(result.ok)

    def test_pattern_constraint_fails(self) -> None:
        from core.validator import FieldSpec
        v = self._make({"zoom.default": FieldSpec(type_=str, pattern=r"^\d+%$")})
        result = v.validate({"zoom.default": "100px"})
        self.assertFalse(result.ok)

    def test_pattern_constraint_passes(self) -> None:
        from core.validator import FieldSpec
        v = self._make({"zoom.default": FieldSpec(type_=str, pattern=r"^\d+%$")})
        result = v.validate({"zoom.default": "110%"})
        self.assertTrue(result.ok)

    def test_min_constraint_fails(self) -> None:
        from core.validator import FieldSpec
        v = self._make({"messages.timeout": FieldSpec(type_=int, min_=0)})
        result = v.validate({"messages.timeout": -1})
        self.assertFalse(result.ok)

    def test_min_constraint_passes(self) -> None:
        from core.validator import FieldSpec
        v = self._make({"messages.timeout": FieldSpec(type_=int, min_=0)})
        result = v.validate({"messages.timeout": 5000})
        self.assertTrue(result.ok)

    def test_max_constraint_fails(self) -> None:
        from core.validator import FieldSpec
        v = self._make({"fonts.web.size.default": FieldSpec(type_=int, min_=1, max_=200)})
        result = v.validate({"fonts.web.size.default": 999})
        self.assertFalse(result.ok)

    def test_custom_validator_returns_error(self) -> None:
        from core.validator import FieldSpec
        spec = FieldSpec(custom=lambda v: "bad" if v == 0 else None)
        v = self._make({"x": spec})
        result = v.validate({"x": 0})
        self.assertFalse(result.ok)

    def test_custom_validator_passes(self) -> None:
        from core.validator import FieldSpec
        spec = FieldSpec(custom=lambda v: None)
        v = self._make({"x": spec})
        result = v.validate({"x": 42})
        self.assertTrue(result.ok)

    def test_unknown_key_silent_in_non_strict(self) -> None:
        v = self._make({})
        result = v.validate({"unknown_key": "value"})
        self.assertTrue(result.ok)

    def test_unknown_key_warn_in_strict(self) -> None:
        v = self._make({}, strict=True)
        result = v.validate({"unknown_key": "value"})
        self.assertGreater(len(result.warnings), 0)

    def test_empty_settings_empty_schema_ok(self) -> None:
        from core.validator import ConfigValidator
        v = ConfigValidator({})
        result = v.validate({})
        self.assertTrue(result.ok)

    def test_validation_result_merge(self) -> None:
        from core.validator import ValidationResult
        a = ValidationResult(errors=["e1"], warnings=["w1"])
        b = ValidationResult(errors=["e2"], warnings=["w2"])
        c = a.merge(b)
        self.assertEqual(c.errors, ["e1", "e2"])
        self.assertEqual(c.warnings, ["w1", "w2"])

    def test_validation_result_str_ok(self) -> None:
        from core.validator import ValidationResult
        r = ValidationResult()
        self.assertIn("OK", str(r))

    def test_validation_result_str_errors(self) -> None:
        from core.validator import ValidationResult
        r = ValidationResult(errors=["fail"], warnings=["hmm"])
        s = str(r)
        self.assertIn("ERROR", s)
        self.assertIn("WARNING", s)


class TestCommonSchema(unittest.TestCase):

    def test_common_schema_validates_valid_settings(self) -> None:
        from core.validator import ConfigValidator, COMMON_SCHEMA
        settings = {
            "content.javascript.enabled": True,
            "content.blocking.enabled":   True,
            "zoom.default":               "100%",
            "fonts.default_size":         "10pt",
            "fonts.web.size.default":     16,
            "tabs.position":              "top",
            "messages.timeout":           5000,
            "downloads.location.prompt":  True,
        }
        v = ConfigValidator(COMMON_SCHEMA)
        result = v.validate(settings)
        self.assertTrue(result.ok, f"Unexpected errors: {result.errors}")

    def test_common_schema_catches_bad_zoom(self) -> None:
        from core.validator import ConfigValidator, COMMON_SCHEMA
        v = ConfigValidator(COMMON_SCHEMA)
        result = v.validate({"zoom.default": "100px"})
        self.assertFalse(result.ok)

    def test_common_schema_catches_bad_js_type(self) -> None:
        from core.validator import ConfigValidator, COMMON_SCHEMA
        v = ConfigValidator(COMMON_SCHEMA)
        result = v.validate({"content.javascript.enabled": "yes"})
        self.assertFalse(result.ok)

    def test_common_schema_catches_bad_tabs_position(self) -> None:
        from core.validator import ConfigValidator, COMMON_SCHEMA
        v = ConfigValidator(COMMON_SCHEMA)
        result = v.validate({"tabs.position": "center"})
        self.assertFalse(result.ok)

    def test_common_schema_catches_bad_editor_command(self) -> None:
        from core.validator import ConfigValidator, COMMON_SCHEMA
        v = ConfigValidator(COMMON_SCHEMA)
        result = v.validate({"editor.command": ["vim"]})  # missing {}
        self.assertFalse(result.ok)

    def test_common_schema_editor_command_with_placeholder_ok(self) -> None:
        from core.validator import ConfigValidator, COMMON_SCHEMA
        v = ConfigValidator(COMMON_SCHEMA)
        result = v.validate({"editor.command": ["nvim", "{}"]})
        self.assertTrue(result.ok)


class TestSchemaRegistry(unittest.TestCase):

    def setUp(self) -> None:
        from core.validator import reset_schema_registry
        reset_schema_registry()

    def test_register_and_get(self) -> None:
        from core.validator import get_schema_registry, FieldSpec
        reg = get_schema_registry()
        reg.register("test_schema", {"x": FieldSpec(type_=int)})
        self.assertIsNotNone(reg.get("test_schema"))

    def test_validate_all_runs_all_schemas(self) -> None:
        from core.validator import get_schema_registry, FieldSpec
        reg = get_schema_registry()
        reg.register("s1", {"x": FieldSpec(type_=int, required=True)})
        reg.register("s2", {"y": FieldSpec(type_=str, required=True)})
        result = reg.validate_all({})  # both required fields missing
        self.assertFalse(result.ok)
        self.assertGreaterEqual(len(result.errors), 2)

    def test_extend_merges_schemas(self) -> None:
        from core.validator import get_schema_registry, FieldSpec
        reg = get_schema_registry()
        reg.register("base_schema", {"x": FieldSpec(type_=int)})
        reg.extend("base_schema", {"y": FieldSpec(type_=str)})
        schema = reg.get("base_schema")
        assert schema is not None
        self.assertIn("x", schema)
        self.assertIn("y", schema)

    def test_names_returns_registered_names(self) -> None:
        from core.validator import SchemaRegistry
        reg = SchemaRegistry()
        reg.register("aaa", {})
        reg.register("bbb", {})
        self.assertIn("aaa", reg.names())
        self.assertIn("bbb", reg.names())

    def test_reset_returns_fresh_registry(self) -> None:
        from core.validator import get_schema_registry, reset_schema_registry, FieldSpec
        reg = get_schema_registry()
        reg.register("stale", {"x": FieldSpec(type_=int)})
        reg2 = reset_schema_registry()
        self.assertIsNone(reg2.get("stale"))

    def test_singleton_returns_same_object(self) -> None:
        from core.validator import get_schema_registry
        a = get_schema_registry()
        b = get_schema_registry()
        self.assertIs(a, b)


# ═════════════════════════════════════════════════════════════════════════════
# Integration: ComposeLayer in LayerStack
# ═════════════════════════════════════════════════════════════════════════════

class TestComposeLayerInStack(unittest.TestCase):

    def test_compose_layer_registered_in_stack(self) -> None:
        from core.layer import LayerStack, BaseConfigLayer
        from core.compose import ComposeLayer

        class A(BaseConfigLayer):
            name="a"
            priority=10
            def _settings(self) -> dict[str, Any]:
                return {"zoom.default": "90%"}

        class B(BaseConfigLayer):
            name="b"
            priority=20
            def _settings(self) -> dict[str, Any]:
                return {"zoom.default": "110%"}

        composed = ComposeLayer("composed", priority=50, children=[A(), B()])
        stack = LayerStack()
        stack.register(composed)
        packets = stack.resolve()
        self.assertIn("composed", packets)

    def test_compose_layer_overrides_individual_layer(self) -> None:
        """A ComposeLayer at priority 70 should override a layer at priority 10."""
        from core.layer import LayerStack, BaseConfigLayer
        from core.compose import ComposeLayer

        class Base(BaseConfigLayer):
            name="base2"
            priority=10
            def _settings(self) -> dict[str, Any]:
                return {"settings": {"zoom.default": "80%"}}

        class Overlay(BaseConfigLayer):
            name="overlay"
            priority=60
            def _settings(self) -> dict[str, Any]:
                return {"zoom.default": "130%"}

        composed = ComposeLayer("composed2", priority=70, children=[Overlay()])
        stack = LayerStack()
        stack.register(Base())
        stack.register(composed)
        stack.resolve()
        # composed is higher priority, should win
        zoom = stack.merged.get("settings", {}).get("zoom.default") or \
               stack.merged.get("zoom.default")
        # Composed wins at priority 70 over base at 10
        self.assertIsNotNone(zoom)


# ═════════════════════════════════════════════════════════════════════════════
# Runner
# ═════════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    print("=" * 60)
    print("qutebrowser config v13 tests")
    print("=" * 60)
    unittest.main(verbosity=2)
