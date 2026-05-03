"""
tests/test_v11.py
=================
Tests for v11 additions:
  - core/audit.py: AuditLog, AuditEntry, AuditFilter, AuditLevel
  - layers/session.py: SessionMode, SessionSpec, SessionLayer
  - core/pipeline.py v11: ReduceStage, BranchStage, CacheStage, AuditStage
  - Pipeline.fork(), Pipeline.describe(), PipeStage.__add__()
  - ConfigPacket.with_errors(), ConfigPacket.with_warnings()

Expected: all tests pass with no running qutebrowser instance.
Run:  python3 tests/test_v11.py
      pytest tests/test_v11.py -v
"""

from __future__ import annotations

import sys
import os
import unittest
from typing import Any

_here = os.path.dirname(os.path.abspath(__file__))
_root = os.path.dirname(_here)
if _root not in sys.path:
    sys.path.insert(0, _root)


# ═════════════════════════════════════════════════════════════════════════════
# AuditLog Tests
# ═════════════════════════════════════════════════════════════════════════════

class TestAuditLog(unittest.TestCase):

    def setUp(self) -> None:
        from core.audit import reset_audit_log
        self.log = reset_audit_log(capacity=100)

    # ── record ────────────────────────────────────────────────────────────────

    def test_record_returns_entry(self) -> None:
        from core.audit import AuditLevel
        e = self.log.record(AuditLevel.INFO, "test", "hello world")
        self.assertEqual(e.component, "test")
        self.assertEqual(e.message, "hello world")
        self.assertEqual(e.level, AuditLevel.INFO)

    def test_record_increments_seq(self) -> None:
        from core.audit import AuditLevel
        e1 = self.log.record(AuditLevel.INFO, "test", "first")
        e2 = self.log.record(AuditLevel.INFO, "test", "second")
        self.assertEqual(e2.seq, e1.seq + 1)

    def test_record_with_meta(self) -> None:
        from core.audit import AuditLevel
        e = self.log.record(AuditLevel.DEBUG, "pipe", "stage done", duration_ms=12.3)
        self.assertAlmostEqual(e.meta["duration_ms"], 12.3)

    def test_size_tracks_entries(self) -> None:
        from core.audit import AuditLevel
        for i in range(5):
            self.log.record(AuditLevel.INFO, "t", f"msg {i}")
        self.assertEqual(self.log.size, 5)

    def test_ring_buffer_evicts_oldest(self) -> None:
        from core.audit import AuditLevel, AuditLog
        small = AuditLog(capacity=3)
        for i in range(5):
            small.record(AuditLevel.INFO, "t", f"msg {i}")
        self.assertEqual(small.size, 3)
        entries = small.query()
        self.assertEqual(entries[0].message, "msg 2")  # oldest kept

    def test_clear_empties_log(self) -> None:
        from core.audit import AuditLevel
        self.log.record(AuditLevel.INFO, "t", "hello")
        self.log.clear()
        self.assertEqual(self.log.size, 0)

    # ── query / filter ────────────────────────────────────────────────────────

    def test_query_all_returns_all(self) -> None:
        from core.audit import AuditLevel
        self.log.record(AuditLevel.INFO,  "c", "info msg")
        self.log.record(AuditLevel.ERROR, "c", "err msg")
        self.assertEqual(len(self.log.query()), 2)

    def test_filter_level_min(self) -> None:
        from core.audit import AuditLevel, AuditFilter
        self.log.record(AuditLevel.DEBUG, "c", "debug")
        self.log.record(AuditLevel.WARN,  "c", "warn")
        self.log.record(AuditLevel.ERROR, "c", "error")
        results = self.log.query(AuditFilter(level_min=AuditLevel.WARN))
        self.assertEqual(len(results), 2)

    def test_filter_component(self) -> None:
        from core.audit import AuditLevel, AuditFilter
        self.log.record(AuditLevel.INFO, "health",       "ok")
        self.log.record(AuditLevel.INFO, "orchestrator", "done")
        results = self.log.query(AuditFilter(component="health"))
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0].component, "health")

    def test_filter_since_seq(self) -> None:
        from core.audit import AuditLevel, AuditFilter
        _e1 = self.log.record(AuditLevel.INFO, "c", "first")
        e2 = self.log.record(AuditLevel.INFO, "c", "second")
        _  = self.log.record(AuditLevel.INFO, "c", "third")
        results = self.log.query(AuditFilter(since_seq=e2.seq))
        self.assertGreaterEqual(len(results), 2)

    def test_errors_convenience(self) -> None:
        from core.audit import AuditLevel
        self.log.record(AuditLevel.INFO,  "c", "info")
        self.log.record(AuditLevel.ERROR, "c", "error 1")
        self.log.record(AuditLevel.ERROR, "c", "error 2")
        self.assertEqual(len(self.log.errors()), 2)

    # ── export ────────────────────────────────────────────────────────────────

    def test_export_text_non_empty(self) -> None:
        from core.audit import AuditLevel
        self.log.record(AuditLevel.INFO, "test", "hello")
        text = self.log.export_text()
        self.assertIn("hello", text)

    def test_export_json_valid(self) -> None:
        import json
        from core.audit import AuditLevel
        self.log.record(AuditLevel.WARN, "test", "json test")
        data = json.loads(self.log.export_json())
        self.assertIsInstance(data, list)
        self.assertEqual(data[0]["component"], "test")

    def test_export_markdown_has_header(self) -> None:
        from core.audit import AuditLevel
        self.log.record(AuditLevel.INFO, "test", "md test")
        md = self.log.export_markdown()
        self.assertIn("| Seq |", md)

    def test_summary_shows_counts(self) -> None:
        from core.audit import AuditLevel
        self.log.record(AuditLevel.ERROR, "c", "err")
        summary = self.log.summary(last_n=5)
        self.assertIn("errors=", summary)

    # ── helpers ───────────────────────────────────────────────────────────────

    def test_module_helpers(self) -> None:
        from core.audit import audit_debug, audit_info, audit_warn, audit_error, get_audit_log, reset_audit_log
        reset_audit_log()
        audit_debug("t", "debug msg")
        audit_info("t",  "info msg")
        audit_warn("t",  "warn msg")
        audit_error("t", "error msg")
        log = get_audit_log()
        self.assertGreaterEqual(log.size, 4)

    def test_global_singleton_is_same_instance(self) -> None:
        from core.audit import get_audit_log, reset_audit_log
        reset_audit_log()
        a = get_audit_log()
        b = get_audit_log()
        self.assertIs(a, b)


# ═════════════════════════════════════════════════════════════════════════════
# AuditEntry Tests
# ═════════════════════════════════════════════════════════════════════════════

class TestAuditEntry(unittest.TestCase):

    def _make(self) -> Any:
        from core.audit import AuditLevel, reset_audit_log
        log = reset_audit_log()
        return log.record(AuditLevel.INFO, "comp", "test message", key="val")

    def test_ts_iso_format(self) -> None:
        e = self._make()
        self.assertTrue(e.ts_iso.endswith("Z"))
        self.assertIn("T", e.ts_iso)

    def test_ts_short_format(self) -> None:
        e = self._make()
        parts = e.ts_short.split(":")
        self.assertEqual(len(parts), 3)

    def test_to_dict_keys(self) -> None:
        e = self._make()
        d = e.to_dict()
        self.assertIn("seq", d)
        self.assertIn("level", d)
        self.assertIn("component", d)
        self.assertIn("message", d)
        self.assertIn("meta", d)

    def test_str_contains_component_and_message(self) -> None:
        e = self._make()
        s = str(e)
        self.assertIn("comp", s)
        self.assertIn("test message", s)


# ═════════════════════════════════════════════════════════════════════════════
# AuditFilter Tests
# ═════════════════════════════════════════════════════════════════════════════

class TestAuditFilter(unittest.TestCase):

    def _entry(self, level: Any, component: str, message: str, seq: int = 1) -> Any:
        from core.audit import AuditEntry
        from datetime import datetime, timezone
        return AuditEntry(
            ts=datetime.now(tz=timezone.utc),
            level=level,
            component=component,
            message=message,
            seq=seq,
        )

    def test_matches_level_min(self) -> None:
        from core.audit import AuditFilter, AuditLevel
        flt = AuditFilter(level_min=AuditLevel.WARN)
        e_warn  = self._entry(AuditLevel.WARN,  "c", "w")
        e_debug = self._entry(AuditLevel.DEBUG, "c", "d")
        self.assertTrue(flt.matches(e_warn))
        self.assertFalse(flt.matches(e_debug))

    def test_matches_component(self) -> None:
        from core.audit import AuditFilter, AuditLevel
        flt = AuditFilter(component="health")
        e_health = self._entry(AuditLevel.INFO, "health", "ok")
        e_other  = self._entry(AuditLevel.INFO, "other",  "ok")
        self.assertTrue(flt.matches(e_health))
        self.assertFalse(flt.matches(e_other))

    def test_matches_message_contains(self) -> None:
        from core.audit import AuditFilter, AuditLevel
        flt = AuditFilter(message_contains="build")
        e1 = self._entry(AuditLevel.INFO, "c", "build complete")
        e2 = self._entry(AuditLevel.INFO, "c", "apply done")
        self.assertTrue(flt.matches(e1))
        self.assertFalse(flt.matches(e2))

    def test_factory_errors_and_warnings(self) -> None:
        from core.audit import AuditFilter, AuditLevel
        flt = AuditFilter.errors_and_warnings()
        self.assertEqual(flt.level_min, AuditLevel.WARN)


# ═════════════════════════════════════════════════════════════════════════════
# SessionLayer Tests
# ═════════════════════════════════════════════════════════════════════════════

class TestSessionLayer(unittest.TestCase):

    def test_default_construction(self) -> None:
        from layers.session import SessionLayer
        layer = SessionLayer()
        data = layer.build()
        # Session should emit at least keybindings (,S prefix)
        self.assertIn("keybindings", data)

    def test_day_session_emits_settings(self) -> None:
        from layers.session import SessionLayer
        layer = SessionLayer(session="day")
        data = layer.build()
        settings = data.get("settings", {})
        # Day emits content.autoplay = False
        self.assertFalse(settings.get("content.autoplay", True))

    def test_night_session_larger_font(self) -> None:
        from layers.session import SessionLayer
        layer = SessionLayer(session="night")
        data = layer.build()
        settings = data.get("settings", {})
        self.assertGreaterEqual(settings.get("fonts.web.size.default", 16), 18)

    def test_present_session_large_zoom(self) -> None:
        from layers.session import SessionLayer
        layer = SessionLayer(session="present")
        self.assertEqual(layer.active_spec.zoom_hint, "125%")

    def test_commute_disables_images(self) -> None:
        from layers.session import SessionLayer
        layer = SessionLayer(session="commute")
        data = layer.build()
        settings = data.get("settings", {})
        self.assertFalse(settings.get("content.images", True))

    def test_focus_hides_statusbar(self) -> None:
        from layers.session import SessionLayer
        layer = SessionLayer(session="focus")
        data = layer.build()
        settings = data.get("settings", {})
        self.assertEqual(settings.get("statusbar.show"), "in-mode")

    def test_invalid_session_falls_back_to_auto(self) -> None:
        from layers.session import SessionLayer, SessionMode
        # Invalid session name should not raise — falls back to auto-detect
        layer = SessionLayer(session="nonexistent_session_xyz")
        # Should resolve to one of the time-based modes
        self.assertIn(layer.active_session, list(SessionMode))

    def test_available_sessions_returns_list(self) -> None:
        from layers.session import SessionLayer
        names = SessionLayer.available_sessions()
        self.assertIn("day", names)
        self.assertIn("night", names)
        self.assertIn("focus", names)

    def test_describe_returns_string(self) -> None:
        from layers.session import SessionLayer
        layer = SessionLayer(session="evening")
        desc = layer.describe()
        self.assertIn("evening", desc)

    def test_keybindings_have_session_prefix(self) -> None:
        from layers.session import SessionLayer
        layer = SessionLayer(session="day", leader=",")
        data  = layer.build()
        bindings = data.get("keybindings", [])
        keys = [b[0] for b in bindings]
        self.assertIn(",Sd", keys)
        self.assertIn(",Sn", keys)
        self.assertIn(",Si", keys)

    def test_priority_is_55(self) -> None:
        from layers.session import SessionLayer
        self.assertEqual(SessionLayer.priority, 55)


# ═════════════════════════════════════════════════════════════════════════════
# Pipeline v11 — new stages
# ═════════════════════════════════════════════════════════════════════════════

class TestReduceStage(unittest.TestCase):

    def _packet(self, data: dict[str, Any]) -> Any:
        from core.pipeline import ConfigPacket
        return ConfigPacket(source="test", data=data)

    def test_reduce_counts_keys(self) -> None:
        from core.pipeline import ReduceStage
        stage = ReduceStage(
            reducer    = lambda acc, k, v: acc + 1,
            initial    = 0,
            result_key = "key_count",
        )
        packet = stage.process(self._packet({"a": 1, "b": 2, "c": 3}))
        self.assertEqual(packet.meta["key_count"], 3)

    def test_reduce_sums_values(self) -> None:
        from core.pipeline import ReduceStage
        stage = ReduceStage(
            reducer    = lambda acc, k, v: acc + (v if isinstance(v, int) else 0),
            initial    = 0,
            result_key = "total",
        )
        packet = stage.process(self._packet({"x": 10, "y": 20}))
        self.assertEqual(packet.meta["total"], 30)

    def test_reduce_does_not_modify_data(self) -> None:
        from core.pipeline import ReduceStage
        data = {"a": 1}
        stage = ReduceStage(lambda acc, k, v: acc + 1, 0, "n")
        packet = stage.process(self._packet(data))
        self.assertEqual(packet.data, {"a": 1})


class TestBranchStage(unittest.TestCase):

    def _packet(self, data: dict[str, Any]) -> Any:
        from core.pipeline import ConfigPacket
        return ConfigPacket(source="test", data=data)

    def test_true_branch_runs_when_predicate_true(self) -> None:
        from core.pipeline import BranchStage, Pipeline, TransformStage
        true_branch = Pipeline("add").pipe(
            TransformStage(lambda d: {**d, "injected": True}, "inject")
        )
        stage = BranchStage(
            predicate   = lambda p: True,
            true_branch = true_branch,
        )
        packet = stage.process(self._packet({"a": 1}))
        self.assertTrue(packet.data.get("injected"))

    def test_false_branch_passthrough_when_no_false_branch(self) -> None:
        from core.pipeline import BranchStage, Pipeline, TransformStage
        true_branch = Pipeline("add").pipe(
            TransformStage(lambda d: {**d, "injected": True}, "inject")
        )
        stage = BranchStage(
            predicate   = lambda p: False,
            true_branch = true_branch,
        )
        packet = stage.process(self._packet({"a": 1}))
        self.assertNotIn("injected", packet.data)

    def test_false_branch_runs_when_predicate_false(self) -> None:
        from core.pipeline import BranchStage, Pipeline, TransformStage
        true_p  = Pipeline("t").pipe(TransformStage(lambda d: {**d, "branch": "true"},  "t"))
        false_p = Pipeline("f").pipe(TransformStage(lambda d: {**d, "branch": "false"}, "f"))
        stage = BranchStage(lambda p: False, true_p, false_p)
        packet = stage.process(self._packet({}))
        self.assertEqual(packet.data.get("branch"), "false")


class TestCacheStage(unittest.TestCase):

    def _packet(self, data: dict[str, Any]) -> Any:
        from core.pipeline import ConfigPacket
        return ConfigPacket(source="test", data=data)

    def test_cache_hit_returns_same_result(self) -> None:
        from core.pipeline import CacheStage, TransformStage
        call_count = [0]
        def expensive(d: dict[str, Any]) -> dict[str, Any]:
            call_count[0] += 1
            return {**d, "expensive": True}
        inner = TransformStage(expensive, "expensive")
        stage = CacheStage(inner, label="test")

        p1 = stage.process(self._packet({"a": 1}))
        p2 = stage.process(self._packet({"a": 1}))  # same input = cache hit
        self.assertEqual(call_count[0], 1)  # inner called only once
        self.assertEqual(p1.data, p2.data)

    def test_cache_miss_on_different_input(self) -> None:
        from core.pipeline import CacheStage, TransformStage
        call_count = [0]
        def fn(d: dict[str, Any]) -> dict[str, Any]:
            call_count[0] += 1
            return d
        stage = CacheStage(TransformStage(fn, "fn"), label="test")
        stage.process(self._packet({"a": 1}))
        stage.process(self._packet({"b": 2}))  # different input = cache miss
        self.assertEqual(call_count[0], 2)

    def test_invalidate_clears_cache(self) -> None:
        from core.pipeline import CacheStage, TransformStage
        call_count = [0]
        def fn(d: dict[str, Any]) -> dict[str, Any]:
            call_count[0] += 1
            return d
        stage = CacheStage(TransformStage(fn, "fn"), label="test")
        stage.process(self._packet({"a": 1}))
        stage.invalidate()
        stage.process(self._packet({"a": 1}))  # after invalidate = miss
        self.assertEqual(call_count[0], 2)


class TestPipelineV11(unittest.TestCase):

    def _packet(self, data: dict[str, Any]) -> Any:
        from core.pipeline import ConfigPacket
        return ConfigPacket(source="test", data=data)

    def test_pipeline_fork_is_independent(self) -> None:
        from core.pipeline import Pipeline, LogStage
        original = Pipeline("orig").pipe(LogStage("a"))
        fork     = original.fork()
        fork.pipe(LogStage("b"))
        self.assertEqual(len(original), 1)
        self.assertEqual(len(fork), 2)

    def test_pipeline_describe(self) -> None:
        from core.pipeline import Pipeline, LogStage
        p = Pipeline("test").pipe(LogStage("a")).pipe(LogStage("b"))
        desc = p.describe()
        self.assertIn("test", desc)
        self.assertIn("log:a", desc)
        self.assertIn("log:b", desc)

    def test_stage_add_creates_pipeline(self) -> None:
        from core.pipeline import LogStage, Pipeline
        combined = LogStage("a") + LogStage("b")
        self.assertIsInstance(combined, Pipeline)
        self.assertEqual(len(combined), 2)

    def test_configpacket_with_errors_bulk(self) -> None:
        from core.pipeline import ConfigPacket
        p = ConfigPacket(source="t", data={})
        p2 = p.with_errors(["err1", "err2", "err3"])
        self.assertEqual(len(p2.errors), 3)
        self.assertEqual(len(p.errors), 0)  # original unchanged

    def test_configpacket_with_warnings_bulk(self) -> None:
        from core.pipeline import ConfigPacket
        p = ConfigPacket(source="t", data={})
        p2 = p.with_warnings(["w1", "w2"])
        self.assertEqual(len(p2.warnings), 2)

    def test_configpacket_with_errors_empty_noop(self) -> None:
        from core.pipeline import ConfigPacket
        p = ConfigPacket(source="t", data={})
        p2 = p.with_errors([])
        self.assertIs(p2, p)  # same object, no-op


# ═════════════════════════════════════════════════════════════════════════════
# Session × LayerStack integration
# ═════════════════════════════════════════════════════════════════════════════

class TestSessionLayerIntegration(unittest.TestCase):

    def test_session_layer_registers_in_stack(self) -> None:
        from core.layer  import LayerStack
        from layers.base import BaseLayer
        from layers.session import SessionLayer
        stack = LayerStack()
        stack.register(BaseLayer())
        stack.register(SessionLayer(session="night"))
        stack.resolve()
        # Night mode should push fonts.web.size.default ≥ 18 into merged settings
        merged_settings = stack.merged.get("settings", {})
        size = merged_settings.get("fonts.web.size.default", 0)
        self.assertGreaterEqual(size, 18)

    def test_session_priority_is_between_perf_and_user(self) -> None:
        from layers.session     import SessionLayer
        from layers.performance import PerformanceLayer
        from layers.user        import UserLayer
        self.assertGreater(SessionLayer.priority, PerformanceLayer.priority)
        self.assertLess(SessionLayer.priority,    UserLayer.priority)


# ═════════════════════════════════════════════════════════════════════════════
# Runner
# ═════════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    print("=" * 60)
    print("qutebrowser config v11 tests")
    print("=" * 60)
    unittest.main(verbosity=2)
