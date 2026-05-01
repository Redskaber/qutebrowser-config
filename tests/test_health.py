"""
tests/test_health.py
====================
Tests for core/health.py — configuration health check system.

Expected: all tests pass with no running qutebrowser instance.
Run:  python3 tests/test_health.py
      pytest tests/test_health.py -v
"""

from __future__ import annotations

import sys
import os
import unittest

_here = os.path.dirname(os.path.abspath(__file__))
_root = os.path.dirname(_here)
if _root not in sys.path:
    sys.path.insert(0, _root)


class TestHealthIssue(unittest.TestCase):

    def test_str_error(self) -> None:
        from core.health import HealthIssue, Severity
        issue = HealthIssue(check="test", severity=Severity.ERROR, message="bad", key="k")
        self.assertIn("✗", str(issue))
        self.assertIn("bad", str(issue))
        self.assertIn("[k]", str(issue))

    def test_str_warning(self) -> None:
        from core.health import HealthIssue, Severity
        issue = HealthIssue(check="test", severity=Severity.WARNING, message="warn")
        self.assertIn("⚠", str(issue))

    def test_str_info(self) -> None:
        from core.health import HealthIssue, Severity
        issue = HealthIssue(check="test", severity=Severity.INFO, message="note")
        self.assertIn("ℹ", str(issue))


class TestHealthReport(unittest.TestCase):

    def test_ok_when_empty(self) -> None:
        from core.health import HealthReport
        r = HealthReport()
        self.assertTrue(r.ok)

    def test_not_ok_with_error(self) -> None:
        from core.health import HealthReport, HealthIssue, Severity
        r = HealthReport()
        r.add(HealthIssue(check="x", severity=Severity.ERROR, message="fail"))
        self.assertFalse(r.ok)

    def test_ok_with_warning_only(self) -> None:
        from core.health import HealthReport, HealthIssue, Severity
        r = HealthReport()
        r.add(HealthIssue(check="x", severity=Severity.WARNING, message="warn"))
        self.assertTrue(r.ok)

    def test_errors_filter(self) -> None:
        from core.health import HealthReport, HealthIssue, Severity
        r = HealthReport()
        r.add(HealthIssue(check="a", severity=Severity.ERROR, message="e"))
        r.add(HealthIssue(check="b", severity=Severity.WARNING, message="w"))
        self.assertEqual(len(r.errors), 1)
        self.assertEqual(len(r.warnings), 1)

    def test_summary_contains_status(self) -> None:
        from core.health import HealthReport
        r = HealthReport()
        s = r.summary()
        self.assertIn("HEALTHY", s)


class TestBuiltinChecks(unittest.TestCase):

    def _run(self, check_cls, settings: dict) -> list:  # type: ignore[no-untyped-def]
        from core.health import HealthReport
        from importlib import import_module
        mod = import_module("core.health")
        check = getattr(mod, check_cls)()
        report = HealthReport()
        check.run(settings, report)
        return report.issues

    def test_blocking_disabled_warns(self) -> None:
        issues = self._run("BlockingEnabledCheck", {"content.blocking.enabled": False})
        self.assertEqual(len(issues), 1)

    def test_blocking_enabled_no_issue(self) -> None:
        issues = self._run("BlockingEnabledCheck", {"content.blocking.enabled": True})
        self.assertEqual(len(issues), 0)

    def test_search_missing_default_errors(self) -> None:
        issues = self._run("SearchEngineDefaultCheck", {"url.searchengines": {"g": "https://google.com?q={}"}})
        from core.health import Severity
        self.assertTrue(any(i.severity == Severity.ERROR for i in issues))

    def test_search_with_default_ok(self) -> None:
        issues = self._run("SearchEngineDefaultCheck", {
            "url.searchengines": {"DEFAULT": "https://brave.com?q={}"}
        })
        self.assertEqual(len(issues), 0)

    def test_webrtc_policy_unsafe_warns(self) -> None:
        issues = self._run("WebRTCPolicyCheck", {"content.webrtc_ip_handling_policy": "default"})
        self.assertGreater(len(issues), 0)

    def test_webrtc_policy_safe_ok(self) -> None:
        issues = self._run("WebRTCPolicyCheck", {
            "content.webrtc_ip_handling_policy": "default-public-interface-only"
        })
        self.assertEqual(len(issues), 0)

    def test_cookie_all_is_info(self) -> None:
        issues = self._run("CookieAcceptCheck", {"content.cookies.accept": "all"})
        from core.health import Severity
        self.assertTrue(any(i.severity == Severity.INFO for i in issues))

    def test_start_pages_empty_warns(self) -> None:
        issues = self._run("StartPageCheck", {"url.start_pages": []})
        self.assertGreater(len(issues), 0)

    def test_start_pages_present_ok(self) -> None:
        issues = self._run("StartPageCheck", {"url.start_pages": ["about:blank"]})
        self.assertEqual(len(issues), 0)


class TestHealthChecker(unittest.TestCase):

    def test_default_checker_construction(self) -> None:
        from core.health import HealthChecker
        c = HealthChecker.default()
        self.assertIsNotNone(c)

    def test_default_checker_passes_clean_config(self) -> None:
        from core.health import HealthChecker
        from layers.base import BaseLayer
        settings = BaseLayer().build().get("settings", {})
        # Inject DEFAULT engine which base layer has
        report = HealthChecker.default().check(settings)
        # Should have no errors (warnings for webrtc are ok)
        self.assertTrue(report.ok)

    def test_checker_can_add_custom_check(self) -> None:
        from core.health import HealthCheck, HealthChecker, HealthReport, HealthIssue, Severity

        class AlwaysWarn(HealthCheck):
            name = "always-warn"
            def run(self, settings, report):  # type: ignore[override]
                report.add(HealthIssue(check=self.name, severity=Severity.WARNING, message="test"))

        c = HealthChecker().add(AlwaysWarn())
        report = c.check({})
        self.assertEqual(len(report.warnings), 1)

    def test_broken_check_doesnt_crash_checker(self) -> None:
        from core.health import HealthCheck, HealthChecker, HealthReport, Severity

        class Crasher(HealthCheck):
            name = "crasher"
            def run(self, settings, report):  # type: ignore[override]
                raise RuntimeError("intentional crash")

        c = HealthChecker().add(Crasher())
        report = c.check({})
        # Crash captured as an error issue, not an exception propagated
        self.assertFalse(report.ok)

    def test_full_pipeline_integration(self) -> None:
        """Health checker runs against a fully-resolved LayerStack."""
        from core.layer import LayerStack
        from layers.base import BaseLayer
        from layers.privacy import PrivacyLayer, PrivacyProfile
        from layers.behavior import BehaviorLayer
        from core.health import HealthChecker

        stack = LayerStack()
        stack.register(BaseLayer())
        stack.register(PrivacyLayer(PrivacyProfile.STANDARD))
        stack.register(BehaviorLayer())
        stack.resolve()

        settings = stack.merged.get("settings", {})
        report = HealthChecker.default().check(settings)
        self.assertTrue(report.ok)


if __name__ == "__main__":
    unittest.main(verbosity=2)
