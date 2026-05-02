"""
tests/test_extensions.py
========================
Tests for extension modules:
  - strategies/merge, profile, search, download
  - policies/content, network, security, host
  - themes/extended
  - keybindings/catalog
  - layers/user (parameter-injection model)

v8: Added font override param tests (font_family, font_size),
    empty-editor-list guard test.

Expected: all tests pass with no running qutebrowser instance.
Run:  python3 tests/test_extensions.py
      pytest tests/test_extensions.py -v
"""

from __future__ import annotations

import sys
import os
from typing import Any, List
import unittest

# ── Path setup ───────────────────────────────────────────────────────────────
_here = os.path.dirname(os.path.abspath(__file__))
_root = os.path.dirname(_here)
if _root not in sys.path:
    sys.path.insert(0, _root)


# ═════════════════════════════════════════════════════════════════════════════
# Strategies: Merge
# ═════════════════════════════════════════════════════════════════════════════
class TestMergeStrategies(unittest.TestCase):

    def setUp(self) -> None:
        from strategies.merge import build_merge_registry
        self.registry = build_merge_registry()

    def test_last_wins(self) -> None:
        ctx = {"base": {"a": 1, "b": 2}, "overlay": {"b": 99, "c": 3}}
        result = self.registry.apply("last_wins", ctx)
        self.assertEqual(result["a"], 1)
        self.assertEqual(result["b"], 99)
        self.assertEqual(result["c"], 3)

    def test_first_wins(self) -> None:
        ctx = {"base": {"a": 1, "b": 2}, "overlay": {"b": 99, "c": 3}}
        result = self.registry.apply("first_wins", ctx)
        self.assertEqual(result["b"], 2)  # base wins
        self.assertEqual(result["c"], 3)  # overlay fills gap

    def test_deep_merge(self) -> None:
        ctx = {
            "base":    {"tabs": {"position": "top", "show": "always"}},
            "overlay": {"tabs": {"position": "bottom"}},
        }
        result = self.registry.apply("deep_merge", ctx)
        self.assertEqual(result["tabs"]["position"], "bottom")
        self.assertEqual(result["tabs"]["show"], "always")

    def test_profile_aware_applies_profile(self) -> None:
        ctx = {
            "base":     {"a": 1},
            "overlay":  {"b": 2},
            "profile":  "laptop",
            "profiles": {"laptop": {"cache": 64}},
        }
        result = self.registry.apply("profile_aware", ctx)
        self.assertEqual(result["cache"], 64)

    def test_profile_aware_can_handle(self) -> None:
        from strategies.merge import ProfileAwareMergeStrategy
        s = ProfileAwareMergeStrategy()
        self.assertTrue(s.can_handle({"profile": "laptop"}))
        self.assertFalse(s.can_handle({"no_profile": True}))

    def test_registry_has_all_strategies(self) -> None:
        names = set(self.registry.names())
        self.assertIn("last_wins", names)
        self.assertIn("first_wins", names)
        self.assertIn("deep_merge", names)
        self.assertIn("profile_aware", names)


# ═════════════════════════════════════════════════════════════════════════════
# Strategies: Profile
# ═════════════════════════════════════════════════════════════════════════════
class TestProfileStrategy(unittest.TestCase):

    def test_daily_resolves(self) -> None:
        from strategies.profile import UnifiedProfile, resolve_profile
        from layers.privacy import PrivacyProfile
        from layers.performance import PerformanceProfile
        r = resolve_profile(UnifiedProfile.DAILY)
        self.assertEqual(r.privacy_profile, PrivacyProfile.STANDARD)
        self.assertEqual(r.performance_profile, PerformanceProfile.BALANCED)

    def test_paranoid_resolves(self) -> None:
        from strategies.profile import UnifiedProfile, resolve_profile
        from layers.privacy import PrivacyProfile
        from layers.performance import PerformanceProfile
        r = resolve_profile(UnifiedProfile.PARANOID)
        self.assertEqual(r.privacy_profile, PrivacyProfile.PARANOID)
        self.assertEqual(r.performance_profile, PerformanceProfile.LOW)

    def test_all_profiles_have_description(self) -> None:
        from strategies.profile import UnifiedProfile, resolve_profile
        for profile in UnifiedProfile:
            r = resolve_profile(profile)
            self.assertTrue(len(r.description) > 0, f"{profile.name} has no description")

    def test_strategy_resolves_by_name_string(self) -> None:
        from strategies.profile import build_profile_registry
        from layers.privacy import PrivacyProfile
        registry = build_profile_registry()
        r = registry.apply("unified_profile", {"profile": "SECURE"})
        self.assertEqual(r.privacy_profile, PrivacyProfile.HARDENED)

    def test_strategy_fallback_on_unknown_name(self) -> None:
        from strategies.profile import build_profile_registry
        from layers.privacy import PrivacyProfile
        registry = build_profile_registry()
        # Unknown name should fall back to DAILY → STANDARD + BALANCED
        r = registry.apply("unified_profile", {"profile": "NONEXISTENT_PROFILE"})
        self.assertEqual(r.privacy_profile, PrivacyProfile.STANDARD)


# ═════════════════════════════════════════════════════════════════════════════
# Strategies: Search
# ═════════════════════════════════════════════════════════════════════════════
class TestSearchStrategies(unittest.TestCase):

    def setUp(self) -> None:
        from strategies.search import build_search_registry
        self.registry = build_search_registry()

    def test_base_has_default(self) -> None:
        result = self.registry.apply("base", {})
        self.assertIn("DEFAULT", result)

    def test_dev_has_nix_and_mdn(self) -> None:
        result = self.registry.apply("dev", {})
        self.assertIn("nix", result)
        self.assertIn("mdn", result)

    def test_privacy_uses_brave_default(self) -> None:
        result = self.registry.apply("privacy", {})
        self.assertIn("brave.com", result["DEFAULT"])

    def test_chinese_has_bilibili(self) -> None:
        result = self.registry.apply("chinese", {})
        self.assertIn("bili", result)
        self.assertIn("bilibili.com", result["bili"])

    def test_academia_has_arxiv(self) -> None:
        result = self.registry.apply("academia", {})
        self.assertIn("arxiv", result)

    def test_custom_merges_on_base(self) -> None:
        ctx = {
            "base_strategy": "base",
            "custom_engines": {"jira": "https://jira.mycompany.com/?q={}"},
        }
        result = self.registry.apply("custom", ctx)
        self.assertIn("jira", result)
        self.assertIn("DEFAULT", result)  # base is still present


# ═════════════════════════════════════════════════════════════════════════════
# Strategies: Download
# ═════════════════════════════════════════════════════════════════════════════
class TestDownloadStrategies(unittest.TestCase):

    def setUp(self) -> None:
        from strategies.download import build_download_registry
        self.registry = build_download_registry()

    def test_none_dispatcher(self) -> None:
        result = self.registry.apply("none", {})
        self.assertIsNone(result["downloads.open_dispatcher"])

    def test_auto_returns_dict_with_required_keys(self) -> None:
        result = self.registry.apply("auto", {})
        self.assertIn("downloads.location.directory", result)
        self.assertIn("downloads.prevent_mixed_content", result)

    def test_all_strategies_have_required_keys(self) -> None:
        required = {"downloads.location.directory", "downloads.open_dispatcher"}
        for name in self.registry.names():
            with self.subTest(strategy=name):
                result = self.registry.apply(name, {})
                for key in required:
                    self.assertIn(key, result)


# ═════════════════════════════════════════════════════════════════════════════
# Policies: Content
# ═════════════════════════════════════════════════════════════════════════════
class TestContentPolicies(unittest.TestCase):

    def _chain(self, profile_name: str):  # type: ignore[no-untyped-def]
        from policies.content import build_content_policy_chain
        from layers.privacy import PrivacyProfile
        profile = PrivacyProfile[profile_name]
        return build_content_policy_chain(profile)

    def test_paranoid_denies_js_true(self) -> None:
        from core.strategy import PolicyAction
        chain = self._chain("PARANOID")
        d = chain.evaluate("content.javascript.enabled", True, {})
        self.assertEqual(d.action, PolicyAction.DENY)

    def test_standard_allows_js_true(self) -> None:
        from core.strategy import PolicyAction
        chain = self._chain("STANDARD")
        d = chain.evaluate("content.javascript.enabled", True, {})
        self.assertEqual(d.action, PolicyAction.ALLOW)

    def test_paranoid_modifies_cookies_to_never(self) -> None:
        from core.strategy import PolicyAction
        chain = self._chain("PARANOID")
        d = chain.evaluate("content.cookies.accept", "all", {})
        self.assertEqual(d.action, PolicyAction.MODIFY)
        self.assertEqual(d.modified_value, "never")

    def test_hardened_downgrades_all_cookies(self) -> None:
        from core.strategy import PolicyAction
        chain = self._chain("HARDENED")
        d = chain.evaluate("content.cookies.accept", "all", {})
        self.assertEqual(d.action, PolicyAction.MODIFY)
        self.assertEqual(d.modified_value, "no-3rdparty")

    def test_paranoid_blocks_canvas(self) -> None:
        from core.strategy import PolicyAction
        chain = self._chain("PARANOID")
        d = chain.evaluate("content.canvas_reading", True, {})
        self.assertEqual(d.action, PolicyAction.MODIFY)
        self.assertFalse(d.modified_value)

    def test_unrelated_key_passes_through(self) -> None:
        from core.strategy import PolicyAction
        chain = self._chain("PARANOID")
        d = chain.evaluate("tabs.position", "top", {})
        self.assertEqual(d.action, PolicyAction.ALLOW)


# ═════════════════════════════════════════════════════════════════════════════
# Policies: Network
# ═════════════════════════════════════════════════════════════════════════════
class TestNetworkPolicies(unittest.TestCase):

    def _chain(self, profile_name: str):  # type: ignore[no-untyped-def]
        from policies.network import build_network_policy_chain
        from layers.privacy import PrivacyProfile
        return build_network_policy_chain(PrivacyProfile[profile_name])

    def test_hardened_disables_dns_prefetch(self) -> None:
        from core.strategy import PolicyAction
        chain = self._chain("HARDENED")
        d = chain.evaluate("content.dns_prefetch", True, {})
        self.assertEqual(d.action, PolicyAction.MODIFY)
        self.assertFalse(d.modified_value)

    def test_standard_allows_dns_prefetch(self) -> None:
        from core.strategy import PolicyAction
        chain = self._chain("STANDARD")
        d = chain.evaluate("content.dns_prefetch", True, {})
        self.assertEqual(d.action, PolicyAction.ALLOW)

    def test_paranoid_sets_referrer_never(self) -> None:
        from core.strategy import PolicyAction
        chain = self._chain("PARANOID")
        d = chain.evaluate("content.headers.referer", "always", {})
        self.assertEqual(d.action, PolicyAction.MODIFY)
        self.assertEqual(d.modified_value, "never")


# ═════════════════════════════════════════════════════════════════════════════
# Policies: Security
# ═════════════════════════════════════════════════════════════════════════════
class TestSecurityPolicies(unittest.TestCase):

    def _chain(self, profile_name: str):  # type: ignore[no-untyped-def]
        from policies.security import build_security_policy_chain
        from layers.privacy import PrivacyProfile
        return build_security_policy_chain(PrivacyProfile[profile_name])

    def test_mixed_content_always_blocked(self) -> None:
        from core.strategy import PolicyAction
        for profile in ("STANDARD", "HARDENED", "PARANOID"):
            chain = self._chain(profile)
            d = chain.evaluate("downloads.prevent_mixed_content", False, {})
            self.assertEqual(d.action, PolicyAction.MODIFY, f"Failed for {profile}")
            self.assertTrue(d.modified_value)

    def test_hardened_blocks_geolocation(self) -> None:
        from core.strategy import PolicyAction
        chain = self._chain("HARDENED")
        d = chain.evaluate("content.geolocation", True, {})
        self.assertEqual(d.action, PolicyAction.MODIFY)
        self.assertFalse(d.modified_value)

    def test_paranoid_blocks_clipboard(self) -> None:
        from core.strategy import PolicyAction
        chain = self._chain("PARANOID")
        d = chain.evaluate("content.javascript.clipboard", "access", {})
        self.assertEqual(d.action, PolicyAction.MODIFY)
        self.assertEqual(d.modified_value, "none")


# ═════════════════════════════════════════════════════════════════════════════
# Policies: Host
# ═════════════════════════════════════════════════════════════════════════════
class TestHostPolicies(unittest.TestCase):

    def test_default_registry_has_rules(self) -> None:
        from policies.host import build_default_host_registry
        registry = build_default_host_registry()
        self.assertGreater(len(registry), 0)

    def test_localhost_always_present(self) -> None:
        from policies.host import build_default_host_registry
        registry = build_default_host_registry()
        localhost_rules = [
            r for r in registry.active()
            if r.pattern == "localhost"
        ]
        self.assertEqual(len(localhost_rules), 1)

    def test_categories_populated(self) -> None:
        from policies.host import build_default_host_registry
        registry = build_default_host_registry()
        cats = registry.categories()
        self.assertIn("dev", cats)
        self.assertIn("login", cats)

    def test_disable_login_rules(self) -> None:
        from policies.host import build_default_host_registry
        registry = build_default_host_registry(include_login=False)
        login_rules = registry.by_category("login")
        self.assertEqual(len(login_rules), 0)

    def test_host_rule_is_frozen(self) -> None:
        from policies.host import HostRule
        rule = HostRule(pattern="*.test.com", settings={"content.javascript.enabled": True})
        with self.assertRaises(Exception):
            rule.pattern = "*.other.com"  # type: ignore[misc]


# ═════════════════════════════════════════════════════════════════════════════
# Themes: Extended
# ═════════════════════════════════════════════════════════════════════════════
class TestExtendedThemes(unittest.TestCase):

    def test_extended_themes_register(self) -> None:
        from themes.extended import register_all_themes, EXTENDED_THEMES
        from layers.appearance import THEMES
        register_all_themes()
        for name in EXTENDED_THEMES:
            self.assertIn(name, THEMES)

    def test_nord_has_correct_bg(self) -> None:
        from themes.extended import EXTENDED_THEMES
        self.assertEqual(EXTENDED_THEMES["nord"].bg, "#2e3440")

    def test_dracula_has_purple_accent(self) -> None:
        from themes.extended import EXTENDED_THEMES
        self.assertEqual(EXTENDED_THEMES["dracula"].accent, "#bd93f9")

    def test_all_extended_themes_have_required_fields(self) -> None:
        from themes.extended import EXTENDED_THEMES
        required_attrs = [
            "bg", "fg", "accent", "success", "error",
            "font_mono", "font_size_ui",
        ]
        for name, scheme in EXTENDED_THEMES.items():
            for attr in required_attrs:
                with self.subTest(theme=name, attr=attr):
                    self.assertTrue(hasattr(scheme, attr))
                    self.assertIsNotNone(getattr(scheme, attr))

    def test_appearance_layer_accepts_extended_theme(self) -> None:
        from themes.extended import register_all_themes
        from layers.appearance import AppearanceLayer
        register_all_themes()
        layer = AppearanceLayer(theme="nord")
        data  = layer.build()
        self.assertIn("settings", data)
        settings = data["settings"]
        self.assertIn("colors.statusbar.normal.bg", settings)

    def test_list_themes_includes_both_builtin_and_extended(self) -> None:
        from themes.extended import register_all_themes, list_themes
        register_all_themes()
        names = list_themes()
        self.assertIn("catppuccin-mocha", names)  # built-in
        self.assertIn("nord", names)              # extended


# ═════════════════════════════════════════════════════════════════════════════
# Keybindings: Catalog
# ═════════════════════════════════════════════════════════════════════════════
class TestKeybindingCatalog(unittest.TestCase):

    def _make_catalog(self):  # type: ignore[no-untyped-def]
        from keybindings.catalog import KeybindingCatalog
        from layers.base     import BaseLayer
        from layers.behavior import BehaviorLayer
        from layers.privacy  import PrivacyLayer, PrivacyProfile
        from layers.user     import UserLayer
        return KeybindingCatalog.from_layers([
            BaseLayer(),
            BehaviorLayer(),
            PrivacyLayer(PrivacyProfile.STANDARD),
            UserLayer(),
        ])

    def test_catalog_has_entries(self) -> None:
        catalog = self._make_catalog()
        self.assertGreater(len(catalog), 0)

    def test_lookup_known_key(self) -> None:
        catalog = self._make_catalog()
        entry = catalog.lookup("gg", "normal")
        self.assertIsNotNone(entry)
        self.assertIn("scroll", entry.command)  # type: ignore[union-attr]

    def test_lookup_unknown_key_returns_none(self) -> None:
        catalog = self._make_catalog()
        self.assertIsNone(catalog.lookup("XYZUNKNOWN", "normal"))

    def test_by_mode_deduplicates(self) -> None:
        catalog = self._make_catalog()
        entries = catalog.by_mode("normal")
        keys = [e.key for e in entries]
        self.assertEqual(len(keys), len(set(keys)))  # no duplicate keys

    def test_modes_returns_list(self) -> None:
        catalog = self._make_catalog()
        modes = catalog.modes()
        self.assertIn("normal", modes)
        self.assertIn("insert", modes)

    def test_conflict_report_runs(self) -> None:
        catalog = self._make_catalog()
        report = catalog.conflict_report()
        self.assertIsInstance(report, str)

    def test_reference_table_normal_mode(self) -> None:
        catalog = self._make_catalog()
        table = catalog.reference_table("normal")
        self.assertIn("| Key |", table)
        self.assertIn("`gg`", table)

    def test_reference_all_covers_all_modes(self) -> None:
        catalog = self._make_catalog()
        full = catalog.reference_all()
        for mode in catalog.modes():
            self.assertIn(mode.capitalize(), full)

    def test_higher_priority_wins_on_conflict(self) -> None:
        from keybindings.catalog import KeybindingCatalog, KeybindingEntry
        catalog = KeybindingCatalog()
        catalog.add(KeybindingEntry("J", "tab-prev", "normal", "behavior", 40))
        catalog.add(KeybindingEntry("J", "scroll-down", "normal", "user", 90))
        entry = catalog.lookup("J", "normal")
        self.assertEqual(entry.command, "scroll-down")  # type: ignore[union-attr]
        self.assertEqual(entry.layer, "user")            # type: ignore[union-attr]


# ═════════════════════════════════════════════════════════════════════════════
# UserLayer: Parameter-injection model
# ═════════════════════════════════════════════════════════════════════════════
class TestUserLayerParameterInjection(unittest.TestCase):

    def test_default_construction(self) -> None:
        from layers.user import UserLayer
        layer = UserLayer()
        data = layer.build()
        # With all-None params, settings dict is empty so "settings" key is omitted
        # by BaseConfigLayer.build() — this is correct behaviour.
        # Aliases are always present.
        self.assertIn("aliases", data)

    def test_editor_injected(self) -> None:
        from layers.user import UserLayer
        layer = UserLayer(editor=["kitty", "-e", "nvim", "{}"])
        settings = layer.build()["settings"]
        self.assertEqual(settings["editor.command"], ["kitty", "-e", "nvim", "{}"])

    def test_start_pages_injected(self) -> None:
        from layers.user import UserLayer
        layer = UserLayer(start_pages=["https://example.com"])
        settings = layer.build()["settings"]
        self.assertEqual(settings["url.start_pages"], ["https://example.com"])

    def test_zoom_injected(self) -> None:
        from layers.user import UserLayer
        layer = UserLayer(zoom="125%")
        settings = layer.build()["settings"]
        self.assertEqual(settings["zoom.default"], "125%")

    def test_search_engines_injected(self) -> None:
        from layers.user import UserLayer
        engines = {"DEFAULT": "https://brave.com?q={}", "test": "https://test.com?q={}"}
        layer = UserLayer(search_engines=engines)
        settings = layer.build()["settings"]
        self.assertEqual(settings["url.searchengines"], engines)

    def test_extra_settings_merged(self) -> None:
        from layers.user import UserLayer
        layer = UserLayer(extra_settings={"tabs.position": "left"})
        settings = layer.build()["settings"]
        self.assertEqual(settings["tabs.position"], "left")

    def test_extra_bindings_returned(self) -> None:
        from layers.user import UserLayer
        bindings = [("gx", "open -t -- {clipboard}", "normal")]
        layer = UserLayer(extra_bindings=bindings)
        data = layer.build()
        self.assertIn(("gx", "open -t -- {clipboard}", "normal"), data["keybindings"])

    def test_extra_aliases_merged_with_gh(self) -> None:
        from layers.user import UserLayer
        layer = UserLayer(extra_aliases={"update": "config-source"})
        aliases = layer.build()["aliases"]
        self.assertIn("gh", aliases)      # permanent alias always present
        self.assertIn("update", aliases)  # user alias added

    def test_none_editor_not_in_settings(self) -> None:
        from layers.user import UserLayer
        layer = UserLayer(editor=None)
        # No settings keys → "settings" absent from build() result
        data = layer.build()
        settings = data.get("settings", {})
        self.assertNotIn("editor.command", settings)

    def test_none_zoom_not_in_settings(self) -> None:
        from layers.user import UserLayer
        layer = UserLayer(zoom=None)
        data = layer.build()
        settings = data.get("settings", {})
        self.assertNotIn("zoom.default", settings)

    def test_priority_is_90(self) -> None:
        from layers.user import UserLayer
        self.assertEqual(UserLayer.priority, 90)

    def test_injected_collections_are_copies(self) -> None:
        """Mutations to original dicts must not affect the layer."""
        from layers.user import UserLayer
        original = {"tabs.position": "top"}
        layer = UserLayer(extra_settings=original)
        original["tabs.position"] = "left"   # mutate original
        settings = layer.build()["settings"]
        self.assertEqual(settings["tabs.position"], "top")  # layer unchanged

    # ── Font override params (v8) ─────────────────────────────────────
    def test_font_family_injected(self) -> None:
        from layers.user import UserLayer
        layer = UserLayer(font_family="JetBrainsMono Nerd Font")
        settings = layer.build()["settings"]
        self.assertEqual(settings["fonts.default_family"], "JetBrainsMono Nerd Font")

    def test_font_size_injected(self) -> None:
        from layers.user import UserLayer
        layer = UserLayer(font_size="10pt")
        settings = layer.build()["settings"]
        self.assertEqual(settings["fonts.default_size"], "10pt")

    def test_font_size_web_px_injected_as_int(self) -> None:
        """font_size_web='16px' must produce fonts.web.size.default=16 (int)."""
        from layers.user import UserLayer
        layer = UserLayer(font_size_web="16px")
        settings = layer.build()["settings"]
        self.assertEqual(settings["fonts.web.size.default"], 16)
        self.assertIsInstance(settings["fonts.web.size.default"], int)

    def test_font_size_web_plain_int_str(self) -> None:
        """font_size_web='18' (no suffix) also works."""
        from layers.user import UserLayer
        layer = UserLayer(font_size_web="18")
        settings = layer.build()["settings"]
        self.assertEqual(settings["fonts.web.size.default"], 18)

    def test_font_family_none_not_in_settings(self) -> None:
        from layers.user import UserLayer
        layer = UserLayer(font_family=None)
        settings = layer.build().get("settings", {})
        self.assertNotIn("fonts.default_family", settings)

    def test_font_family_whitespace_stripped(self) -> None:
        from layers.user import UserLayer
        layer = UserLayer(font_family="  Iosevka  ")
        settings = layer.build()["settings"]
        self.assertEqual(settings["fonts.default_family"], "Iosevka")

    def test_empty_editor_list_skipped(self) -> None:
        """v8: empty editor=[] must not write an invalid value."""
        from layers.user import UserLayer
        layer = UserLayer(editor=[])
        settings = layer.build().get("settings", {})
        self.assertNotIn("editor.command", settings)

    # ── Layout override params (v9) ───────────────────────────────────
    def test_tabs_position_injected(self) -> None:
        """tabs_position='left' maps to tabs.position."""
        from layers.user import UserLayer
        layer = UserLayer(tabs_position="left")
        settings = layer.build()["settings"]
        self.assertEqual(settings["tabs.position"], "left")

    def test_tabs_position_none_not_in_settings(self) -> None:
        from layers.user import UserLayer
        layer = UserLayer(tabs_position=None)
        settings = layer.build().get("settings", {})
        self.assertNotIn("tabs.position", settings)

    def test_tabs_position_invalid_skipped(self) -> None:
        """Invalid tabs_position is silently skipped (warning only)."""
        from layers.user import UserLayer
        layer = UserLayer(tabs_position="sideways")
        settings = layer.build().get("settings", {})
        self.assertNotIn("tabs.position", settings)

    def test_tabs_position_case_normalised(self) -> None:
        """tabs_position='TOP' is accepted and normalised to lowercase."""
        from layers.user import UserLayer
        layer = UserLayer(tabs_position="TOP")
        settings = layer.build()["settings"]
        self.assertEqual(settings["tabs.position"], "top")

    def test_statusbar_show_injected(self) -> None:
        """statusbar_show='in-mode' maps to statusbar.show."""
        from layers.user import UserLayer
        layer = UserLayer(statusbar_show="in-mode")
        settings = layer.build()["settings"]
        self.assertEqual(settings["statusbar.show"], "in-mode")

    def test_statusbar_show_never(self) -> None:
        from layers.user import UserLayer
        layer = UserLayer(statusbar_show="never")
        settings = layer.build()["settings"]
        self.assertEqual(settings["statusbar.show"], "never")

    def test_statusbar_show_none_not_in_settings(self) -> None:
        from layers.user import UserLayer
        layer = UserLayer(statusbar_show=None)
        settings = layer.build().get("settings", {})
        self.assertNotIn("statusbar.show", settings)

    def test_statusbar_show_invalid_skipped(self) -> None:
        """Invalid statusbar_show value is silently skipped."""
        from layers.user import UserLayer
        layer = UserLayer(statusbar_show="sometimes")
        settings = layer.build().get("settings", {})
        self.assertNotIn("statusbar.show", settings)


# ═════════════════════════════════════════════════════════════════════════════
# v9: ConfigReloadedEvent
# ═════════════════════════════════════════════════════════════════════════════
class TestConfigReloadedEvent(unittest.TestCase):

    def test_event_exists(self) -> None:
        from core.protocol import ConfigReloadedEvent
        e = ConfigReloadedEvent()
        self.assertEqual(e.change_count, 0)  # type: ignore
        self.assertEqual(e.error_count, 0)   # type: ignore
        self.assertEqual(e.duration_ms, 0.0) # type: ignore
        self.assertEqual(e.reason, "config-source") # type: ignore

    def test_event_fields(self) -> None:
        from core.protocol import ConfigReloadedEvent
        e = ConfigReloadedEvent(change_count=5, error_count=1, duration_ms=0.2 , reason="test")
        self.assertEqual(e.change_count, 5)     # type: ignore
        self.assertEqual(e.error_count, 1)      # type: ignore
        self.assertEqual(e.duration_ms, 0.2)    # type: ignore
        self.assertEqual(e.reason, "test")      # type: ignore

    def test_event_is_frozen(self) -> None:
        from core.protocol import ConfigReloadedEvent
        e = ConfigReloadedEvent(change_count=3)
        with self.assertRaises(Exception):
            e.change_count = 99  # type: ignore[misc]

    def test_event_subscribed_and_emitted(self) -> None:
        """EventBus receives ConfigReloadedEvent correctly."""
        from core.protocol import ConfigReloadedEvent, MessageRouter
        router = MessageRouter()
        received: List[Any] = []
        router.events.subscribe(ConfigReloadedEvent, received.append)
        router.events.publish(ConfigReloadedEvent(change_count=7))
        self.assertEqual(len(received), 1)
        self.assertEqual(received[0].change_count, 7)  # type: ignore


if __name__ == "__main__":
    print("=" * 65)
    print("qutebrowser config extension tests")
    print("=" * 65)
    unittest.main(verbosity=2)
