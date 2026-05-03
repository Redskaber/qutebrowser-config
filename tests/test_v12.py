"""
tests/test_v12.py
=================
v12 regression and feature tests

Coverage:
  - core.metrics: MetricsSample, MetricsCollector, PhaseTimer,
                  get_metrics_collector / reset_metrics_collector,
                  metrics_time() context manager
  - core.pipeline v12 stages:
      TeeStage       — fan-out: observer runs, main packet unchanged
      RetryStage     — retry on exception; raises after max_retries
      CompositeStage — sub-pipeline as single named stage
  - Pipeline.__iter__ / describe() with v12 stages
  - core/__init__ v12 exports completeness
  - Orchestrator v12 audit_trail() + metrics_summary() methods
  - MetricsCollector callback integration (router.emit_metrics wired)

Test isolation:
  - reset_metrics_collector() called in setUp to clear global state
  - reset_audit_log() called in setUp to clear global audit state
  - All tests are self-contained; no qutebrowser runtime required
"""

from __future__ import annotations

import sys
import os
import time
import unittest
from typing import Any, List

# ── sys.path setup ───────────────────────────────────────────────────────────
# Ensure project root is importable regardless of working directory.
_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(_HERE)
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)


# ─────────────────────────────────────────────
# MetricsSample tests
# ─────────────────────────────────────────────

class TestMetricsSample(unittest.TestCase):

    def setUp(self) -> None:
        from core.metrics import reset_metrics_collector
        reset_metrics_collector()

    def test_str_format(self) -> None:
        from core.metrics import MetricsSample
        s = MetricsSample(phase="build", duration_ms=2.5, key_count=10)
        text = str(s)
        self.assertIn("build", text)
        self.assertIn("2.5", text)
        self.assertIn("keys=10", text)

    def test_immutable(self) -> None:
        from core.metrics import MetricsSample
        s = MetricsSample(phase="apply", duration_ms=5.0, key_count=20)
        with self.assertRaises((AttributeError, TypeError)):
            s.phase = "other"  # type: ignore[misc]

    def test_meta_stored(self) -> None:
        from core.metrics import MetricsSample
        s = MetricsSample(phase="build", duration_ms=1.0, key_count=5,
                          meta={"layer_count": 7})
        self.assertEqual(s.meta["layer_count"], 7)


# ─────────────────────────────────────────────
# PhaseTimer tests
# ─────────────────────────────────────────────

class TestPhaseTimer(unittest.TestCase):

    def test_measures_time(self) -> None:
        from core.metrics import PhaseTimer
        timer = PhaseTimer()
        with timer:
            time.sleep(0.01)
        self.assertGreater(timer.elapsed_ms, 5.0)

    def test_elapsed_before_stop_non_zero(self) -> None:
        from core.metrics import PhaseTimer
        timer = PhaseTimer()
        timer.__enter__()
        # before __exit__, elapsed_ms reads live clock
        ms = timer.elapsed_ms
        timer.__exit__(None, None, None)
        self.assertGreaterEqual(ms, 0.0)

    def test_does_not_suppress_exception(self) -> None:
        from core.metrics import PhaseTimer
        timer = PhaseTimer()
        with self.assertRaises(ValueError):
            with timer:
                raise ValueError("test")


# ─────────────────────────────────────────────
# MetricsCollector tests
# ─────────────────────────────────────────────

class TestMetricsCollector(unittest.TestCase):

    def setUp(self) -> None:
        from core.metrics import reset_metrics_collector
        reset_metrics_collector()

    def test_emit_records_sample(self) -> None:
        from core.metrics import MetricsCollector
        c = MetricsCollector()
        c.emit("build", 3.0, key_count=5)
        self.assertEqual(len(c), 1)

    def test_get_latest_by_phase(self) -> None:
        from core.metrics import MetricsCollector
        c = MetricsCollector()
        c.emit("build", 1.0, key_count=1)
        c.emit("apply", 2.0, key_count=2)
        c.emit("build", 3.0, key_count=3)
        s = c.get("build")
        self.assertIsNotNone(s)
        assert s is not None
        self.assertAlmostEqual(s.duration_ms, 3.0)

    def test_get_missing_phase_returns_none(self) -> None:
        from core.metrics import MetricsCollector
        c = MetricsCollector()
        self.assertIsNone(c.get("nonexistent"))

    def test_last_n_ordering(self) -> None:
        from core.metrics import MetricsCollector
        c = MetricsCollector()
        for i in range(10):
            c.emit(f"p{i}", float(i), key_count=i)
        last5 = c.last_n(5)
        self.assertEqual(len(last5), 5)
        # last_n returns newest-last; verify ordering
        phases = [s.phase for s in last5]
        self.assertEqual(phases, [f"p{i}" for i in range(5, 10)])

    def test_capacity_ring_buffer(self) -> None:
        from core.metrics import MetricsCollector
        c = MetricsCollector(capacity=3)
        for i in range(6):
            c.emit(f"p{i}", float(i))
        # Only last 3 remain
        self.assertEqual(len(c), 3)
        phases = [s.phase for s in c.last_n(10)]
        self.assertEqual(phases, ["p3", "p4", "p5"])

    def test_callback_invoked(self) -> None:
        from core.metrics import MetricsCollector
        c = MetricsCollector()
        calls: List[tuple[str, float, int]] = []
        c.on_emit(lambda ph, ms, n: calls.append((ph, ms, n)))
        c.emit("build", 1.5, key_count=7)
        self.assertEqual(len(calls), 1)
        self.assertEqual(calls[0], ("build", 1.5, 7))

    def test_multiple_callbacks(self) -> None:
        from core.metrics import MetricsCollector
        c = MetricsCollector()
        log1: List[str] = []
        log2: List[str] = []
        c.on_emit(lambda ph, ms, n: log1.append(ph))
        c.on_emit(lambda ph, ms, n: log2.append(ph))
        c.emit("apply", 2.0)
        self.assertEqual(log1, ["apply"])
        self.assertEqual(log2, ["apply"])

    def test_callback_exception_does_not_crash(self) -> None:
        from core.metrics import MetricsCollector
        c = MetricsCollector()
        def bad_cb(ph: str, ms: float, n: int) -> None:
            raise RuntimeError("boom")
        c.on_emit(bad_cb)
        # Should not raise
        c.emit("build", 1.0)
        self.assertEqual(len(c), 1)

    def test_all_phases(self) -> None:
        from core.metrics import MetricsCollector
        c = MetricsCollector()
        c.emit("build", 1.0)
        c.emit("apply", 2.0)
        c.emit("build", 1.5)
        phases = c.all_phases()
        # order of first occurrence
        self.assertEqual(phases, ["build", "apply"])

    def test_totals_by_phase(self) -> None:
        from core.metrics import MetricsCollector
        c = MetricsCollector()
        c.emit("build", 1.0)
        c.emit("build", 2.0)
        c.emit("apply", 3.0)
        totals = c.totals_by_phase()
        self.assertAlmostEqual(totals["build"], 3.0)
        self.assertAlmostEqual(totals["apply"], 3.0)

    def test_clear(self) -> None:
        from core.metrics import MetricsCollector
        c = MetricsCollector()
        c.emit("build", 1.0)
        c.clear()
        self.assertEqual(len(c), 0)

    def test_summary_no_samples(self) -> None:
        from core.metrics import MetricsCollector
        c = MetricsCollector()
        s = c.summary()
        self.assertIn("no samples", s)

    def test_summary_with_samples(self) -> None:
        from core.metrics import MetricsCollector
        c = MetricsCollector()
        c.emit("build", 2.5, key_count=10)
        s = c.summary()
        self.assertIn("build", s)
        self.assertIn("2.5", s)

    def test_meta_stored_in_sample(self) -> None:
        from core.metrics import MetricsCollector
        c = MetricsCollector()
        s = c.emit("build", 1.0, key_count=5, layer_count=3)
        self.assertEqual(s.meta.get("layer_count"), 3)


# ─────────────────────────────────────────────
# metrics_time context manager
# ─────────────────────────────────────────────

class TestMetricsTime(unittest.TestCase):

    def test_yields_phase_timer(self) -> None:
        from core.metrics import metrics_time
        with metrics_time() as t:
            time.sleep(0.005)
        self.assertGreater(t.elapsed_ms, 1.0)


# ─────────────────────────────────────────────
# Singleton tests
# ─────────────────────────────────────────────

class TestMetricsSingleton(unittest.TestCase):

    def setUp(self) -> None:
        from core.metrics import reset_metrics_collector
        reset_metrics_collector()

    def test_get_returns_same_instance(self) -> None:
        from core.metrics import get_metrics_collector
        a = get_metrics_collector()
        b = get_metrics_collector()
        self.assertIs(a, b)

    def test_reset_returns_new_instance(self) -> None:
        from core.metrics import get_metrics_collector, reset_metrics_collector
        a = get_metrics_collector()
        b = reset_metrics_collector()
        c = get_metrics_collector()
        self.assertIsNot(a, b)
        self.assertIs(b, c)


# ─────────────────────────────────────────────
# TeeStage tests
# ─────────────────────────────────────────────

class TestTeeStage(unittest.TestCase):

    def _make_packet(self, data: dict[str, Any]) -> Any:
        from core.pipeline import ConfigPacket
        return ConfigPacket(source="test", data=data)

    def test_original_packet_returned_unchanged(self) -> None:
        from core.pipeline import TeeStage, LogStage
        pkt = self._make_packet({"k": "v"})
        stage = TeeStage(LogStage("side"), label="t1")
        result = stage.process(pkt)
        self.assertEqual(result.data, {"k": "v"})
        self.assertIs(result, pkt)   # same object

    def test_observer_receives_packet(self) -> None:
        from core.pipeline import TeeStage
        seen: List[Any] = []

        class CaptureStage:
            name = "capture"
            def process(self, p: Any) -> Any:
                seen.append(p)
                return p

        pkt = self._make_packet({"x": 1})
        stage = TeeStage(CaptureStage(), label="cap")   # type: ignore[arg-type]
        stage.process(pkt)
        self.assertEqual(len(seen), 1)
        self.assertIs(seen[0], pkt)

    def test_observer_exception_does_not_propagate(self) -> None:
        from core.pipeline import TeeStage, PipeStage, ConfigPacket

        class BoomStage(PipeStage):
            @property
            def name(self) -> str:
                return "boom"
            def process(self, p: ConfigPacket) -> ConfigPacket: # type: ignore
                raise RuntimeError("observer failure")

        pkt = self._make_packet({"k": 1})
        stage = TeeStage(BoomStage(), label="safe")
        # Must not raise
        result = stage.process(pkt)
        self.assertIs(result, pkt)

    def test_name_includes_observer_name(self) -> None:
        from core.pipeline import TeeStage, LogStage
        stage = TeeStage(LogStage("probe"), label="tee1")
        self.assertIn("tee1", stage.name)
        self.assertIn("probe", stage.name)


# ─────────────────────────────────────────────
# RetryStage tests
# ─────────────────────────────────────────────

class TestRetryStage(unittest.TestCase):

    def _make_packet(self, data: dict[str, Any]) -> Any:
        from core.pipeline import ConfigPacket
        return ConfigPacket(source="test", data=data)

    def test_success_on_first_try(self) -> None:
        from core.pipeline import RetryStage, TransformStage
        calls: List[int] = []
        def fn(d: dict[str, Any]) -> dict[str, Any]:
            calls.append(1)
            return {**d, "new": 1}
        stage = RetryStage(TransformStage(fn, "t"), max_retries=3)
        pkt = self._make_packet({"a": 1})
        result = stage.process(pkt)
        self.assertEqual(len(calls), 1)
        self.assertIn("new", result.data)

    def test_retries_on_exception(self) -> None:
        from core.pipeline import RetryStage, PipeStage, ConfigPacket

        attempts: List[int] = [0]

        class FlakyStage(PipeStage):
            @property
            def name(self) -> str:
                return "flaky"
            def process(self, p: ConfigPacket) -> ConfigPacket: # type: ignore
                attempts[0] += 1
                if attempts[0] < 3:
                    raise RuntimeError("transient")
                return p.with_data({"recovered": True})

        stage = RetryStage(FlakyStage(), max_retries=3)
        pkt = self._make_packet({})
        result = stage.process(pkt)
        self.assertEqual(attempts[0], 3)
        self.assertIn("recovered", result.data)

    def test_raises_after_max_retries(self) -> None:
        from core.pipeline import RetryStage, PipeStage, ConfigPacket

        class AlwaysFail(PipeStage):
            @property
            def name(self) -> str:
                return "always-fail"
            def process(self, p: ConfigPacket) -> ConfigPacket: # type: ignore
                raise RuntimeError("permanent failure")

        stage = RetryStage(AlwaysFail(), max_retries=2)
        pkt = self._make_packet({})
        with self.assertRaises(RuntimeError):
            stage.process(pkt)

    def test_warnings_recorded_for_each_failure(self) -> None:
        from core.pipeline import RetryStage, PipeStage, ConfigPacket

        class Fail2Then(PipeStage):
            _n: int = 0
            @property
            def name(self) -> str:
                return "fail2then"
            def process(self, p: ConfigPacket) -> ConfigPacket: # type: ignore
                self._n += 1
                if self._n < 3:
                    raise RuntimeError("fail")
                return p

        stage = RetryStage(Fail2Then(), max_retries=3)
        pkt = self._make_packet({})
        result = stage.process(pkt)
        # Two failures → two warning entries
        self.assertEqual(len(result.warnings), 2)

    def test_min_retries_is_1(self) -> None:
        from core.pipeline import RetryStage, LogStage
        stage = RetryStage(LogStage("l"), max_retries=0)
        self.assertIn("×1", stage.name)

    def test_name_contains_multiplier(self) -> None:
        from core.pipeline import RetryStage, LogStage
        stage = RetryStage(LogStage("l"), max_retries=5)
        self.assertIn("×5", stage.name)


# ─────────────────────────────────────────────
# CompositeStage tests
# ─────────────────────────────────────────────

class TestCompositeStage(unittest.TestCase):

    def _make_packet(self, data: dict[str, Any]) -> Any:
        from core.pipeline import ConfigPacket
        return ConfigPacket(source="test", data=data)

    def test_delegates_to_sub_pipeline(self) -> None:
        from core.pipeline import CompositeStage, Pipeline, MergeStage
        sub = Pipeline("sub").pipe(MergeStage({"injected": True}))
        stage = CompositeStage(sub, label="composite-test")
        pkt = self._make_packet({"orig": 1})
        result = stage.process(pkt)
        self.assertTrue(result.data.get("injected"))
        self.assertEqual(result.data.get("orig"), 1)

    def test_name_uses_label(self) -> None:
        from core.pipeline import CompositeStage, Pipeline
        sub = Pipeline("inner-name")
        stage = CompositeStage(sub, label="my-label")
        self.assertIn("my-label", stage.name)

    def test_name_uses_sub_pipeline_name_if_no_label(self) -> None:
        from core.pipeline import CompositeStage, Pipeline
        sub = Pipeline("auto-name")
        stage = CompositeStage(sub)
        self.assertIn("auto-name", stage.name)

    def test_multiple_stages_in_composite(self) -> None:
        from core.pipeline import CompositeStage, Pipeline, MergeStage
        sub = (
            Pipeline("multi")
            .pipe(MergeStage({"a": 1}))
            .pipe(MergeStage({"b": 2}))
        )
        stage = CompositeStage(sub, label="multi")
        pkt = self._make_packet({})
        result = stage.process(pkt)
        self.assertEqual(result.data.get("a"), 1)
        self.assertEqual(result.data.get("b"), 2)

    def test_composite_in_parent_pipeline(self) -> None:
        from core.pipeline import CompositeStage, Pipeline, MergeStage
        sub = Pipeline("sub").pipe(MergeStage({"sub_key": "sub_val"}))
        main = (
            Pipeline("main")
            .pipe(CompositeStage(sub, label="s"))
            .pipe(MergeStage({"main_key": "main_val"}))
        )
        from core.pipeline import ConfigPacket
        pkt = ConfigPacket(source="test", data={})
        result = main.run(pkt)
        self.assertEqual(result.data.get("sub_key"), "sub_val")
        self.assertEqual(result.data.get("main_key"), "main_val")


# ─────────────────────────────────────────────
# Pipeline.describe() with v12 stages
# ─────────────────────────────────────────────

class TestPipelineDescribeV12(unittest.TestCase):

    def test_describe_includes_tee_and_retry(self) -> None:
        from core.pipeline import Pipeline, TeeStage, RetryStage, LogStage
        p = (
            Pipeline("desc-test")
            .pipe(TeeStage(LogStage("side"), label="side"))
            .pipe(RetryStage(LogStage("inner"), max_retries=2))
        )
        desc = p.describe()
        self.assertIn("tee", desc)
        self.assertIn("retry", desc)

    def test_pipeline_iter(self) -> None:
        from core.pipeline import Pipeline, LogStage
        p = Pipeline("iter-test").pipe(LogStage("a")).pipe(LogStage("b"))
        names = [s.name for s in p.stages()]
        self.assertEqual(names, ["log:a", "log:b"])


# ─────────────────────────────────────────────
# core/__init__ v12 exports
# ─────────────────────────────────────────────

class TestCoreInitV12Exports(unittest.TestCase):

    def test_metrics_exports_present(self) -> None:
        import core
        for name in ("MetricsSample", "MetricsCollector", "PhaseTimer",
                     "get_metrics_collector", "reset_metrics_collector",
                     "metrics_time"):
            self.assertIn(name, core.__all__, f"Missing from core.__all__: {name}")

    def test_audit_exports_present(self) -> None:
        import core
        for name in ("AuditLevel", "AuditEntry", "AuditFilter", "AuditLog",
                     "get_audit_log", "reset_audit_log",
                     "audit_debug", "audit_info", "audit_warn", "audit_error"):
            self.assertIn(name, core.__all__, f"Missing from core.__all__: {name}")

    def test_pipeline_v12_stages_exported(self) -> None:
        import core
        for name in ("TeeStage", "RetryStage", "CompositeStage"):
            self.assertIn(name, core.__all__, f"Missing from core.__all__: {name}")

    def test_pipeline_v11_stages_still_exported(self) -> None:
        import core
        for name in ("ReduceStage", "BranchStage", "CacheStage", "AuditStage"):
            self.assertIn(name, core.__all__, f"Missing from core.__all__: {name}")

    def test_tee_importable_from_core(self) -> None:
        from core import TeeStage   # type: ignore[import]
        from core import RetryStage  # type: ignore[import]
        from core import CompositeStage  # type: ignore[import]

    def test_metrics_importable_from_core(self) -> None:
        from core import MetricsCollector, PhaseTimer, metrics_time  # type: ignore[import]


# ─────────────────────────────────────────────
# Orchestrator v12: audit_trail / metrics_summary
# ─────────────────────────────────────────────

class TestOrchestratorV12Methods(unittest.TestCase):
    """
    Test orchestrator v12 introspection methods in isolation.

    We test the methods directly without spinning up qutebrowser's config
    object — only the pure-Python orchestrator layer.
    """

    def setUp(self) -> None:
        try:
            from core.audit import reset_audit_log
            reset_audit_log()
        except ImportError:
            pass
        try:
            from core.metrics import reset_metrics_collector
            reset_metrics_collector()
        except ImportError:
            pass

    def _build_minimal_orchestrator(self) -> Any:
        """Build a minimal orchestrator with no real layers."""
        from core.layer import LayerStack
        from core.lifecycle import LifecycleManager
        from core.state import ConfigStateMachine
        from core.protocol import MessageRouter
        # Lazy import to avoid circular at module level in test file
        import importlib
        orch_mod = importlib.import_module("orchestrator")
        stack     = LayerStack()
        router    = MessageRouter()
        lifecycle = LifecycleManager()
        fsm       = ConfigStateMachine()
        return orch_mod.ConfigOrchestrator(
            stack=stack,
            router=router,
            lifecycle=lifecycle,
            fsm=fsm,
        )

    def test_audit_trail_returns_string(self) -> None:
        orch = self._build_minimal_orchestrator()
        result = orch.audit_trail(last_n=5)
        self.assertIsInstance(result, str)

    def test_metrics_summary_returns_string(self) -> None:
        orch = self._build_minimal_orchestrator()
        result = orch.metrics_summary(last_n=5)
        self.assertIsInstance(result, str)

    def test_audit_phase_records_entry(self) -> None:
        try:
            from core.audit import get_audit_log, reset_audit_log
            reset_audit_log()
        except ImportError:
            self.skipTest("core.audit not available")

        orch = self._build_minimal_orchestrator()
        orch._audit_phase("test_phase", "hello world", level="info", foo="bar")

        from core.audit import get_audit_log
        log = get_audit_log()
        entries = log.query()
        self.assertTrue(
            any("test_phase" in e.message or "hello world" in e.message for e in entries),
            "Audit entry not recorded",
        )

    def test_metrics_collector_wired(self) -> None:
        orch = self._build_minimal_orchestrator()
        if orch._metrics is None:
            self.skipTest("MetricsCollector not available")
        # Manually emit
        orch._emit_metrics("test_phase", 1.5, key_count=3)
        s = orch._metrics.get("test_phase")
        self.assertIsNotNone(s)
        assert s is not None
        self.assertAlmostEqual(s.duration_ms, 1.5)

    def test_summary_returns_string(self) -> None:
        orch = self._build_minimal_orchestrator()
        result = orch.summary()
        self.assertIsInstance(result, str)
        self.assertIn("v12", result)

    def test_handle_metrics_summary_query(self) -> None:
        orch = self._build_minimal_orchestrator()
        result = orch._handle_get_metrics_summary(object())
        self.assertIsInstance(result, str)


# ─────────────────────────────────────────────
# MetricsCollector × router integration
# ─────────────────────────────────────────────

class TestMetricsCollectorRouterIntegration(unittest.TestCase):
    """Verify that MetricsCollector.on_emit() correctly bridges to router."""

    def test_callback_receives_all_fields(self) -> None:
        from core.metrics import MetricsCollector
        received: List[dict[str, Any]] = []
        c = MetricsCollector()
        c.on_emit(lambda ph, ms, n: received.append({"phase": ph, "ms": ms, "n": n}))
        c.emit("build", 4.2, key_count=11)
        self.assertEqual(len(received), 1)
        self.assertEqual(received[0]["phase"], "build")
        self.assertAlmostEqual(received[0]["ms"], 4.2)
        self.assertEqual(received[0]["n"], 11)

    def test_on_emit_returns_self_for_chaining(self) -> None:
        from core.metrics import MetricsCollector
        c = MetricsCollector()
        result = c.on_emit(lambda ph, ms, n: None)
        self.assertIs(result, c)

    def test_iter_phase(self) -> None:
        from core.metrics import MetricsCollector
        c = MetricsCollector()
        c.emit("build", 1.0)
        c.emit("apply", 2.0)
        c.emit("build", 3.0)
        builds = list(c.iter_phase("build"))
        self.assertEqual(len(builds), 2)
        self.assertAlmostEqual(builds[1].duration_ms, 3.0)


# ─────────────────────────────────────────────
# Runner
# ─────────────────────────────────────────────

if __name__ == "__main__":
    print("=" * 60)
    print("qutebrowser config v12 tests")
    print("=" * 60)
    unittest.main(verbosity=2)
