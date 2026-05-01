"""
tests/test_health.py
====================
Tests for core/health.py (HealthChecker, HealthCheck, HealthReport).

v5: Added tests for new checks:
  EditorCommandCheck, SearchEngineUrlCheck, DownloadDirCheck,
  TabTitleFormatCheck, HealthReport.full_report().

Run: python3 tests/test_health.py
     pytest tests/test_health.py -v
"""

from __future__ import annotations

import os
import sys
import unittest

_here = os.path.dirname(os.path.abspath(__file__))
_root = os.path.dirname(_here) if os.path.basename(_here) == "tests" else _here
if _root not in sys.path:
    sys.path.insert(0, _root)


# ═════════════════════════════════════════════════════════════════════════════
# Individual Check Tests
# ═════════════════════════════════════════════════════════════════════════════
class TestIndividualChecks(unittest.TestCase):

    def _run(self, check_name: str, settings: dict) -> list:
        """Helper: run one named check, return list of issues."""
        import core.health as h
        check_cls = getattr(h, check_name)
        check = check_cls()
        report = h.HealthReport()
        check.run(settings, report)
        return report.issues

    # ── BlockingEnabledCheck ──────────────────────────────────────────
    def test_blocking_disabled_warns(self) -> None:
        issues = self._run("BlockingEnabledCheck", {"content.blocking.enabled": False})
        self.assertGreater(len(issues), 0)

    def test_blocking_enabled_ok(self) -> None:
        issues = self._run("BlockingEnabledCheck", {"content.blocking.enabled": True})
        self.assertEqual(len(issues), 0)

    def test_blocking_missing_ok(self) -> None:
        issues = self._run("BlockingEnabledCheck", {})
        self.assertEqual(len(issues), 0)

    # ── SearchEngineDefaultCheck ──────────────────────────────────────
    def test_search_no_default_errors(self) -> None:
        issues = self._run("SearchEngineDefaultCheck", {
            "url.searchengines": {"g": "https://google.com?q={}"}
        })
        from core.health import Severity
        self.assertTrue(any(i.severity == Severity.ERROR for i in issues))

    def test_search_with_default_ok(self) -> None:
        issues = self._run("SearchEngineDefaultCheck", {
            "url.searchengines": {"DEFAULT": "https://brave.com?q={}"}
        })
        self.assertEqual(len(issues), 0)

    def test_search_missing_key_errors(self) -> None:
        issues = self._run("SearchEngineDefaultCheck", {})
        from core.health import Severity
        self.assertTrue(any(i.severity == Severity.ERROR for i in issues))

    # ── SearchEngineUrlCheck (NEW) ────────────────────────────────────
    def test_search_engine_url_missing_placeholder_warns(self) -> None:
        issues = self._run("SearchEngineUrlCheck", {
            "url.searchengines": {
                "DEFAULT": "https://brave.com?q={}",
                "bad":     "https://example.com/search",  # no {}
            }
        })
        self.assertGreater(len(issues), 0)
        self.assertTrue(any("bad" in str(i) for i in issues))

    def test_search_engine_url_all_valid_ok(self) -> None:
        issues = self._run("SearchEngineUrlCheck", {
            "url.searchengines": {
                "DEFAULT": "https://brave.com?q={}",
                "g":       "https://google.com/search?q={}",
            }
        })
        self.assertEqual(len(issues), 0)

    # ── WebRTCPolicyCheck ─────────────────────────────────────────────
    def test_webrtc_policy_unsafe_warns(self) -> None:
        issues = self._run("WebRTCPolicyCheck", {"content.webrtc_ip_handling_policy": "default"})
        self.assertGreater(len(issues), 0)

    def test_webrtc_policy_safe_ok(self) -> None:
        issues = self._run("WebRTCPolicyCheck", {
            "content.webrtc_ip_handling_policy": "default-public-interface-only"
        })
        self.assertEqual(len(issues), 0)

    # ── CookieAcceptCheck ─────────────────────────────────────────────
    def test_cookie_all_is_info(self) -> None:
        issues = self._run("CookieAcceptCheck", {"content.cookies.accept": "all"})
        from core.health import Severity
        self.assertTrue(any(i.severity == Severity.INFO for i in issues))

    def test_cookie_no3rdparty_ok(self) -> None:
        issues = self._run("CookieAcceptCheck", {"content.cookies.accept": "no-3rdparty"})
        self.assertEqual(len(issues), 0)

    # ── StartPageCheck ────────────────────────────────────────────────
    def test_start_pages_empty_warns(self) -> None:
        issues = self._run("StartPageCheck", {"url.start_pages": []})
        self.assertGreater(len(issues), 0)

    def test_start_pages_present_ok(self) -> None:
        issues = self._run("StartPageCheck", {"url.start_pages": ["about:blank"]})
        self.assertEqual(len(issues), 0)

    # ── EditorCommandCheck (NEW) ──────────────────────────────────────
    def test_editor_missing_placeholder_errors(self) -> None:
        issues = self._run("EditorCommandCheck", {
            "editor.command": ["nvim"]  # no {} — editor never gets the file
        })
        from core.health import Severity
        self.assertTrue(any(i.severity == Severity.ERROR for i in issues))

    def test_editor_with_placeholder_ok(self) -> None:
        issues = self._run("EditorCommandCheck", {
            "editor.command": ["kitty", "-e", "nvim", "{}"]
        })
        self.assertEqual(len(issues), 0)

    def test_editor_not_a_list_errors(self) -> None:
        issues = self._run("EditorCommandCheck", {
            "editor.command": "nvim {}"  # string, not list
        })
        from core.health import Severity
        self.assertTrue(any(i.severity == Severity.ERROR for i in issues))

    def test_editor_empty_list_errors(self) -> None:
        issues = self._run("EditorCommandCheck", {"editor.command": []})
        from core.health import Severity
        self.assertTrue(any(i.severity == Severity.ERROR for i in issues))

    def test_editor_none_ok(self) -> None:
        """Not set = use qutebrowser default; should not trigger check."""
        issues = self._run("EditorCommandCheck", {})
        self.assertEqual(len(issues), 0)

    # ── DownloadDirCheck (NEW) ────────────────────────────────────────
    def test_download_dir_tmp_warns(self) -> None:
        issues = self._run("DownloadDirCheck", {
            "downloads.location.directory": "/tmp"
        })
        self.assertGreater(len(issues), 0)

    def test_download_dir_tmp_subdir_warns(self) -> None:
        issues = self._run("DownloadDirCheck", {
            "downloads.location.directory": "/tmp/downloads"
        })
        self.assertGreater(len(issues), 0)

    def test_download_dir_home_ok(self) -> None:
        issues = self._run("DownloadDirCheck", {
            "downloads.location.directory": "~/Downloads"
        })
        self.assertEqual(len(issues), 0)

    def test_download_dir_none_ok(self) -> None:
        issues = self._run("DownloadDirCheck", {})
        self.assertEqual(len(issues), 0)

    # ── TabTitleFormatCheck (NEW) ─────────────────────────────────────
    def test_tab_title_missing_current_title_info(self) -> None:
        issues = self._run("TabTitleFormatCheck", {
            "tabs.title.format": "{index}"  # no {current_title}
        })
        from core.health import Severity
        self.assertTrue(any(i.severity == Severity.INFO for i in issues))

    def test_tab_title_with_current_title_ok(self) -> None:
        issues = self._run("TabTitleFormatCheck", {
            "tabs.title.format": "{audio}{index}: {current_title}"
        })
        self.assertEqual(len(issues), 0)

    def test_tab_title_none_ok(self) -> None:
        issues = self._run("TabTitleFormatCheck", {})
        self.assertEqual(len(issues), 0)


# ═════════════════════════════════════════════════════════════════════════════
# HealthChecker Tests
# ═════════════════════════════════════════════════════════════════════════════
class TestHealthChecker(unittest.TestCase):

    def test_default_checker_construction(self) -> None:
        from core.health import HealthChecker
        c = HealthChecker.default()
        self.assertIsNotNone(c)

    def test_default_checker_passes_clean_config(self) -> None:
        from core.health import HealthChecker
        from layers.base import BaseLayer
        settings = BaseLayer().build().get("settings", {})
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
        from core.health import HealthCheck, HealthChecker, Severity

        class Crasher(HealthCheck):
            name = "crasher"
            def run(self, settings, report):  # type: ignore[override]
                raise RuntimeError("intentional crash")

        c = HealthChecker().add(Crasher())
        report = c.check({})
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

    def test_health_report_full_report(self) -> None:
        from core.health import HealthChecker, HealthCheck, HealthReport, HealthIssue, Severity

        class MultiIssue(HealthCheck):
            name = "multi"
            def run(self, settings, report):  # type: ignore[override]
                report.add(HealthIssue(check=self.name, severity=Severity.INFO,    message="info"))
                report.add(HealthIssue(check=self.name, severity=Severity.WARNING, message="warn"))

        c = HealthChecker().add(MultiIssue())
        report = c.check({})
        full = report.full_report()
        self.assertIn("info", full.lower())
        self.assertIn("warn", full.lower())


# ═════════════════════════════════════════════════════════════════════════════
# ContextLayer Tests
# ═════════════════════════════════════════════════════════════════════════════
class TestContextLayer(unittest.TestCase):

    def test_import(self) -> None:
        from layers.context import ContextLayer, ContextMode
        self.assertIsNotNone(ContextLayer)
        self.assertIsNotNone(ContextMode)

    def test_default_context(self) -> None:
        from layers.context import ContextLayer, ContextMode
        layer = ContextLayer(context=None)
        self.assertEqual(layer.active_mode, ContextMode.DEFAULT)

    def test_dev_context(self) -> None:
        from layers.context import ContextLayer, ContextMode
        layer = ContextLayer(context="dev")
        self.assertEqual(layer.active_mode, ContextMode.DEV)
        settings = layer.build().get("settings", {})
        engines = settings.get("url.searchengines", {})
        self.assertIn("mdn", engines)
        self.assertIn("crates", engines)

    def test_research_context(self) -> None:
        from layers.context import ContextLayer, ContextMode
        layer = ContextLayer(context="research")
        settings = layer.build().get("settings", {})
        engines = settings.get("url.searchengines", {})
        self.assertIn("arxiv", engines)
        self.assertIn("scholar", engines)

    def test_media_context(self) -> None:
        from layers.context import ContextLayer, ContextMode
        layer = ContextLayer(context="media")
        settings = layer.build().get("settings", {})
        # Media context allows autoplay
        self.assertTrue(settings.get("content.autoplay", False))

    def test_work_context(self) -> None:
        from layers.context import ContextLayer, ContextMode
        layer = ContextLayer(context="work")
        settings = layer.build().get("settings", {})
        engines = settings.get("url.searchengines", {})
        self.assertIn("jira", engines)

    def test_invalid_context_falls_back_to_default(self) -> None:
        from layers.context import ContextLayer, ContextMode
        layer = ContextLayer(context="NONEXISTENT_CONTEXT_XYZ")
        self.assertEqual(layer.active_mode, ContextMode.DEFAULT)

    def test_context_keybindings_contain_switch_bindings(self) -> None:
        from layers.context import ContextLayer
        layer = ContextLayer(context="default", leader=",")
        bindings = layer.build().get("keybindings", [])
        keys = {b[0] for b in bindings}
        self.assertIn(",Cd", keys)
        self.assertIn(",Cw", keys)
        self.assertIn(",Cr", keys)

    def test_available_contexts(self) -> None:
        from layers.context import ContextLayer
        avail = ContextLayer.available_contexts()
        self.assertIn("default", avail)
        self.assertIn("dev", avail)
        self.assertIn("work", avail)

    def test_describe(self) -> None:
        from layers.context import ContextLayer
        layer = ContextLayer(context="dev")
        desc = layer.describe()
        self.assertIn("dev", desc)

    def test_env_var_resolution(self) -> None:
        import os
        from layers.context import ContextLayer, ContextMode
        os.environ["QUTE_CONTEXT"] = "media"
        try:
            layer = ContextLayer(context=None)
            self.assertEqual(layer.active_mode, ContextMode.MEDIA)
        finally:
            del os.environ["QUTE_CONTEXT"]

    def test_explicit_override_wins_over_env(self) -> None:
        import os
        from layers.context import ContextLayer, ContextMode
        os.environ["QUTE_CONTEXT"] = "media"
        try:
            layer = ContextLayer(context="dev")
            self.assertEqual(layer.active_mode, ContextMode.DEV)
        finally:
            del os.environ["QUTE_CONTEXT"]

    def test_context_layer_priority(self) -> None:
        from layers.context import ContextLayer
        self.assertEqual(ContextLayer.priority, 45)

    def test_context_layer_in_stack(self) -> None:
        from core.layer import LayerStack
        from layers.base import BaseLayer
        from layers.behavior import BehaviorLayer
        from layers.context import ContextLayer

        stack = LayerStack()
        stack.register(BaseLayer())
        stack.register(BehaviorLayer())
        stack.register(ContextLayer(context="dev"))
        resolved = stack.resolve()
        self.assertIn("context", resolved)


if __name__ == "__main__":
    unittest.main(verbosity=2)
