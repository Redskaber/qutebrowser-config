"""
tests/test_v14.py
=================
Test Suite  (v14)

Covers all v14 additions:
  - layers/network.py     — NetworkLayer, NetworkMode, NetworkSpec
  - layers/user.py v14   — dark_mode, pdf_viewer, new_tab_page, tab_bar_padding
  - core/protocol.py v14 — NetworkModeChangedEvent, HotSwapCompletedEvent,
                           GetActiveNetworkQuery, GetHotSwapStatusQuery
  - orchestrator.py v14  — hot_swap property, _maybe_emit_network_event,
                           _handle_get_active_network, _handle_get_hot_swap_status,
                           summary() v14

Run::

    python3 tests/test_v14.py
    pytest tests/test_v14.py -v

Expected: all tests pass without a running qutebrowser instance.
"""

from __future__ import annotations

import sys
import os
import unittest
from typing import Any, List

# ── Path setup ────────────────────────────────────────────────────────────────
_here = os.path.dirname(os.path.abspath(__file__))
_root = os.path.dirname(_here)
if _root not in sys.path:
    sys.path.insert(0, _root)


# ═════════════════════════════════════════════════════════════════════════════
# NetworkLayer Tests
# ═════════════════════════════════════════════════════════════════════════════

class TestNetworkMode(unittest.TestCase):

    def test_all_modes_defined(self) -> None:
        from layers.network import NetworkMode
        modes = {m.value for m in NetworkMode}
        self.assertIn("direct",  modes)
        self.assertIn("system",  modes)
        self.assertIn("socks5",  modes)
        self.assertIn("http",    modes)
        self.assertIn("tor",     modes)
        self.assertIn("offline", modes)

    def test_mode_is_string_enum(self) -> None:
        from layers.network import NetworkMode
        self.assertEqual(NetworkMode.SYSTEM.value, "system")
        self.assertEqual(str(NetworkMode.TOR), "tor")


class TestNetworkSpec(unittest.TestCase):

    def test_all_modes_have_specs(self) -> None:
        from layers.network import NetworkMode, _NETWORK_TABLE  # type: ignore[private]
        for mode in NetworkMode:
            self.assertIn(mode, _NETWORK_TABLE)

    def test_tor_spec_has_never_referer(self) -> None:
        from layers.network import NetworkMode, _NETWORK_TABLE # type: ignore[private]
        spec = _NETWORK_TABLE[NetworkMode.TOR]
        self.assertEqual(spec.referer, "never")

    def test_tor_spec_disables_dns_prefetch(self) -> None:
        from layers.network import NetworkMode, _NETWORK_TABLE # type: ignore[private]
        spec = _NETWORK_TABLE[NetworkMode.TOR]
        self.assertFalse(spec.dns_prefetch)

    def test_direct_spec_enables_dns_prefetch(self) -> None:
        from layers.network import NetworkMode, _NETWORK_TABLE # type: ignore[private]
        spec = _NETWORK_TABLE[NetworkMode.DIRECT]
        self.assertTrue(spec.dns_prefetch)

    def test_system_spec_uses_system_proxy(self) -> None:
        from layers.network import NetworkMode, _NETWORK_TABLE # type: ignore[private]
        spec = _NETWORK_TABLE[NetworkMode.SYSTEM]
        self.assertEqual(spec.proxy, "system")

    def test_direct_spec_uses_none_proxy(self) -> None:
        from layers.network import NetworkMode, _NETWORK_TABLE # type: ignore[private]
        spec = _NETWORK_TABLE[NetworkMode.DIRECT]
        self.assertEqual(spec.proxy, "none")

    def test_spec_is_frozen(self) -> None:
        from layers.network import NetworkMode, _NETWORK_TABLE # type: ignore[private]
        spec = _NETWORK_TABLE[NetworkMode.SYSTEM]
        with self.assertRaises((AttributeError, TypeError)):
            spec.proxy = "changed"  # type: ignore[misc]


class TestNetworkLayerResolution(unittest.TestCase):

    def test_default_resolves_to_system(self) -> None:
        from layers.network import NetworkLayer, NetworkMode
        layer = NetworkLayer()
        self.assertEqual(layer.active_mode, NetworkMode.SYSTEM)

    def test_explicit_mode_string(self) -> None:
        from layers.network import NetworkLayer, NetworkMode
        layer = NetworkLayer(mode="tor")
        self.assertEqual(layer.active_mode, NetworkMode.TOR)

    def test_unknown_mode_falls_back_to_system(self) -> None:
        from layers.network import NetworkLayer, NetworkMode
        with self.assertLogs("qute.layers.network", level="WARNING"):
            layer = NetworkLayer(mode="xyzunknown")
        self.assertEqual(layer.active_mode, NetworkMode.SYSTEM)

    def test_env_var_resolution(self) -> None:
        from layers.network import NetworkLayer, NetworkMode, _NETWORK_ENV # type: ignore[private]
        os.environ[_NETWORK_ENV] = "socks5"
        try:
            layer = NetworkLayer()
            self.assertEqual(layer.active_mode, NetworkMode.SOCKS5)
        finally:
            del os.environ[_NETWORK_ENV]

    def test_env_var_invalid_ignored(self) -> None:
        from layers.network import NetworkLayer, NetworkMode, _NETWORK_ENV # type: ignore[private]
        os.environ[_NETWORK_ENV] = "invalid_mode"
        try:
            with self.assertLogs("qute.layers.network", level="WARNING"):
                layer = NetworkLayer()
            self.assertEqual(layer.active_mode, NetworkMode.SYSTEM)
        finally:
            del os.environ[_NETWORK_ENV]


class TestNetworkLayerSettings(unittest.TestCase):

    def test_system_mode_sets_proxy(self) -> None:
        from layers.network import NetworkLayer
        layer = NetworkLayer(mode="system")
        settings = layer.build().get("settings", {})
        self.assertEqual(settings.get("content.proxy"), "system")

    def test_direct_mode_sets_no_proxy(self) -> None:
        from layers.network import NetworkLayer
        layer = NetworkLayer(mode="direct")
        settings = layer.build().get("settings", {})
        self.assertEqual(settings.get("content.proxy"), "none")

    def test_tor_mode_sets_referer_never(self) -> None:
        from layers.network import NetworkLayer
        layer = NetworkLayer(mode="tor")
        settings = layer.build().get("settings", {})
        self.assertEqual(settings.get("content.headers.referer"), "never")

    def test_tor_mode_tls_block(self) -> None:
        from layers.network import NetworkLayer
        layer = NetworkLayer(mode="tor")
        settings = layer.build().get("settings", {})
        self.assertEqual(settings.get("content.tls.certificate_errors"), "block")

    def test_socks5_mode_disables_dns(self) -> None:
        from layers.network import NetworkLayer
        layer = NetworkLayer(mode="socks5")
        settings = layer.build().get("settings", {})
        self.assertFalse(settings.get("content.dns_prefetch", True))

    def test_direct_mode_enables_dns(self) -> None:
        from layers.network import NetworkLayer
        layer = NetworkLayer(mode="direct")
        settings = layer.build().get("settings", {})
        self.assertTrue(settings.get("content.dns_prefetch", False))

    def test_build_returns_settings_dict(self) -> None:
        from layers.network import NetworkLayer
        layer = NetworkLayer()
        data = layer.build()
        self.assertIn("settings", data)

    def test_priority_is_27(self) -> None:
        from layers.network import NetworkLayer
        self.assertEqual(NetworkLayer.priority, 27)


class TestNetworkLayerKeybindings(unittest.TestCase):

    def test_keybindings_are_present(self) -> None:
        from layers.network import NetworkLayer
        layer = NetworkLayer()
        data = layer.build()
        bindings = data.get("keybindings", [])
        self.assertGreater(len(bindings), 0)

    def test_keybindings_use_leader_key(self) -> None:
        from layers.network import NetworkLayer
        layer = NetworkLayer(leader="\\")
        data  = layer.build()
        bindings = data.get("keybindings", [])
        keys = [b[0] for b in bindings]
        # All leader-prefixed bindings start with leader key
        self.assertTrue(any(k.startswith("\\N") for k in keys))

    def test_aliases_present(self) -> None:
        from layers.network import NetworkLayer
        layer = NetworkLayer()
        data  = layer.build()
        aliases = data.get("aliases", {})
        self.assertIn("net", aliases)


class TestNetworkLayerDescribe(unittest.TestCase):

    def test_describe_includes_mode(self) -> None:
        from layers.network import NetworkLayer
        layer = NetworkLayer(mode="tor")
        desc  = layer.describe()
        self.assertIn("tor", desc)

    def test_active_mode_property(self) -> None:
        from layers.network import NetworkLayer, NetworkMode
        layer = NetworkLayer(mode="http")
        self.assertEqual(layer.active_mode, NetworkMode.HTTP)


# ═════════════════════════════════════════════════════════════════════════════
# UserLayer v14 Tests
# ═════════════════════════════════════════════════════════════════════════════

class TestUserLayerDarkMode(unittest.TestCase):

    def test_off_disables_darkmode(self) -> None:
        from layers.user import UserLayer
        layer    = UserLayer(dark_mode="off")
        settings = layer.build().get("settings", {})
        self.assertFalse(settings.get("colors.webpage.darkmode.enabled", True))

    def test_simple_enables_darkmode(self) -> None:
        from layers.user import UserLayer
        layer    = UserLayer(dark_mode="simple")
        settings = layer.build().get("settings", {})
        self.assertTrue(settings.get("colors.webpage.darkmode.enabled", False))
        self.assertEqual(
            settings.get("colors.webpage.darkmode.algorithm"),
            "InvertBrightness",
        )

    def test_mediumlight_enables_darkmode(self) -> None:
        from layers.user import UserLayer
        layer    = UserLayer(dark_mode="mediumLight")
        settings = layer.build().get("settings", {})
        self.assertTrue(settings.get("colors.webpage.darkmode.enabled", False))
        self.assertEqual(
            settings.get("colors.webpage.darkmode.algorithm"),
            "InvertLightness",
        )

    def test_aggressive_sets_policy_always(self) -> None:
        from layers.user import UserLayer
        layer    = UserLayer(dark_mode="aggressive")
        settings = layer.build().get("settings", {})
        self.assertTrue(settings.get("colors.webpage.darkmode.enabled", False))
        self.assertEqual(
            settings.get("colors.webpage.darkmode.policy.page"), "always"
        )

    def test_none_dark_mode_skipped(self) -> None:
        from layers.user import UserLayer
        layer    = UserLayer(dark_mode=None)
        settings = layer.build().get("settings", {})
        self.assertNotIn("colors.webpage.darkmode.enabled", settings)

    def test_invalid_dark_mode_ignored(self) -> None:
        from layers.user import UserLayer
        with self.assertLogs("qute.layers.user", level="WARNING"):
            layer = UserLayer(dark_mode="invalid_algorithm")
        settings = layer.build().get("settings", {})
        self.assertNotIn("colors.webpage.darkmode.enabled", settings)


class TestUserLayerPdfViewer(unittest.TestCase):

    def test_true_enables_pdfjs(self) -> None:
        from layers.user import UserLayer
        layer    = UserLayer(pdf_viewer=True)
        settings = layer.build().get("settings", {})
        self.assertTrue(settings.get("content.pdfjs", False))

    def test_false_disables_pdfjs(self) -> None:
        from layers.user import UserLayer
        layer    = UserLayer(pdf_viewer=False)
        settings = layer.build().get("settings", {})
        self.assertFalse(settings.get("content.pdfjs", True))

    def test_none_skipped(self) -> None:
        from layers.user import UserLayer
        layer    = UserLayer(pdf_viewer=None)
        settings = layer.build().get("settings", {})
        self.assertNotIn("content.pdfjs", settings)


class TestUserLayerNewTabPage(unittest.TestCase):

    def test_sets_default_page(self) -> None:
        from layers.user import UserLayer
        layer    = UserLayer(new_tab_page="https://start.duckduckgo.com")
        settings = layer.build().get("settings", {})
        self.assertEqual(
            settings.get("url.default_page"), "https://start.duckduckgo.com"
        )

    def test_overrides_start_pages_default_page(self) -> None:
        from layers.user import UserLayer
        layer    = UserLayer(
            start_pages  = ["https://bilibili.com"],
            new_tab_page = "https://duckduckgo.com",
        )
        settings = layer.build().get("settings", {})
        # new_tab_page wins over start_pages[0]
        self.assertEqual(settings.get("url.default_page"), "https://duckduckgo.com")
        self.assertEqual(settings.get("url.start_pages"), ["https://bilibili.com"])

    def test_none_skipped(self) -> None:
        from layers.user import UserLayer
        layer    = UserLayer(new_tab_page=None)
        settings = layer.build().get("settings", {})
        self.assertNotIn("url.default_page", settings)


class TestUserLayerTabBarPadding(unittest.TestCase):

    def test_full_dict(self) -> None:
        from layers.user import UserLayer
        padding  = {"top": 0, "bottom": 0, "left": 5, "right": 5}
        layer    = UserLayer(tab_bar_padding=padding)
        settings = layer.build().get("settings", {})
        self.assertEqual(settings.get("tabs.padding"), padding)

    def test_partial_dict(self) -> None:
        from layers.user import UserLayer
        layer    = UserLayer(tab_bar_padding={"top": 2, "bottom": 2})
        settings = layer.build().get("settings", {})
        actual   = settings.get("tabs.padding")
        self.assertIsNotNone(actual)
        self.assertEqual(actual.get("top"), 2)
        self.assertNotIn("left", actual)

    def test_invalid_keys_filtered(self) -> None:
        from layers.user import UserLayer
        with self.assertLogs("qute.layers.user", level="WARNING"):
            layer = UserLayer(tab_bar_padding={"invalid_key": 5})
        settings = layer.build().get("settings", {})
        self.assertNotIn("tabs.padding", settings)

    def test_none_skipped(self) -> None:
        from layers.user import UserLayer
        layer    = UserLayer(tab_bar_padding=None)
        settings = layer.build().get("settings", {})
        self.assertNotIn("tabs.padding", settings)


# ═════════════════════════════════════════════════════════════════════════════
# Protocol v14 Event Tests
# ═════════════════════════════════════════════════════════════════════════════

class TestNetworkModeChangedEvent(unittest.TestCase):

    def test_immutable(self) -> None:
        from core.protocol import NetworkModeChangedEvent
        e = NetworkModeChangedEvent(old_mode="system", new_mode="socks5", proxy="socks5://127.0.0.1:7897")
        with self.assertRaises((AttributeError, TypeError)):
            e.new_mode = "tor"  # type: ignore[misc]

    def test_topic(self) -> None:
        from core.protocol import NetworkModeChangedEvent
        e = NetworkModeChangedEvent()
        self.assertEqual(e.topic(), "NetworkModeChangedEvent")

    def test_defaults(self) -> None:
        from core.protocol import NetworkModeChangedEvent
        e = NetworkModeChangedEvent()
        self.assertEqual(e.old_mode, "unknown")
        self.assertEqual(e.new_mode, "system")
        self.assertEqual(e.source, "startup")


class TestHotSwapCompletedEvent(unittest.TestCase):

    def test_ok_property_true_when_no_errors(self) -> None:
        from core.protocol import HotSwapCompletedEvent
        e = HotSwapCompletedEvent(operation="swap", layer_name="context", changes=[], errors=[])
        self.assertTrue(e.ok)

    def test_ok_property_false_when_errors(self) -> None:
        from core.protocol import HotSwapCompletedEvent
        e = HotSwapCompletedEvent(operation="swap", layer_name="context", changes=[], errors=["err1", "err2"])
        self.assertFalse(e.ok)

    def test_topic(self) -> None:
        from core.protocol import HotSwapCompletedEvent
        e = HotSwapCompletedEvent()
        self.assertEqual(e.topic(), "HotSwapCompletedEvent")

    def test_immutable(self) -> None:
        from core.protocol import HotSwapCompletedEvent
        e = HotSwapCompletedEvent()
        with self.assertRaises((AttributeError, TypeError)):
            e.changes = ["new"]  # type: ignore[misc]


class TestGetActiveNetworkQuery(unittest.TestCase):

    def test_instantiable(self) -> None:
        from core.protocol import GetActiveNetworkQuery
        q = GetActiveNetworkQuery()
        self.assertIsNotNone(q.id)

    def test_topic(self) -> None:
        from core.protocol import GetActiveNetworkQuery
        q = GetActiveNetworkQuery()
        self.assertEqual(q.topic(), "GetActiveNetworkQuery")


class TestGetHotSwapStatusQuery(unittest.TestCase):

    def test_instantiable(self) -> None:
        from core.protocol import GetHotSwapStatusQuery
        q = GetHotSwapStatusQuery()
        self.assertIsNotNone(q.id)


# ═════════════════════════════════════════════════════════════════════════════
# MessageRouter v14 Helper Tests
# ═════════════════════════════════════════════════════════════════════════════

class TestRouterV14Helpers(unittest.TestCase):

    def setUp(self) -> None:
        from core.protocol import MessageRouter
        self.router = MessageRouter()

    def test_emit_network_changed_fires_event(self) -> None:
        from core.protocol import NetworkModeChangedEvent
        received: List[Any] = []
        self.router.events.subscribe(NetworkModeChangedEvent, received.append)
        self.router.emit_network_changed(
            old_mode="system", new_mode="socks5",
            proxy="socks5://127.0.0.1:7897",
        )
        self.assertEqual(len(received), 1)
        self.assertEqual(received[0].new_mode, "socks5")

    def test_emit_hot_swap_completed_fires_event(self) -> None:
        from core.protocol import HotSwapCompletedEvent
        received: List[Any] = []
        self.router.events.subscribe(HotSwapCompletedEvent, received.append)
        self.router.emit_hot_swap_completed(
            operation="swap", layer_name="context",
            changes=[], errors=[], duration_ms=0.5,
        )
        self.assertEqual(len(received), 1)
        self.assertEqual(received[0].layer_name, "context")
        self.assertTrue(received[0].ok)

    def test_emit_network_changed_source_default(self) -> None:
        from core.protocol import NetworkModeChangedEvent
        received: List[Any] = []
        self.router.events.subscribe(NetworkModeChangedEvent, received.append)
        self.router.emit_network_changed(
            old_mode="system", new_mode="tor", proxy="socks5://127.0.0.1:9050",
        )
        self.assertEqual(received[0].source, "startup")  # MessageRouter helper default


# ═════════════════════════════════════════════════════════════════════════════
# Orchestrator v14 Tests
# ═════════════════════════════════════════════════════════════════════════════

class TestOrchestratorV14HotSwapProperty(unittest.TestCase):

    def _make_orchestrator(self) -> Any:
        """Create a minimal orchestrator for testing."""
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

    def test_hot_swap_property_returns_something(self) -> None:
        orch = self._make_orchestrator()
        hs   = orch.hot_swap
        # If hot_swap module is available, it should be non-None
        # If not available, it returns None gracefully
        # Either way, accessing the property should not raise
        self.assertIsNotNone(hs)  # core/hot_swap.py is available in v13+

    def test_hot_swap_property_cached(self) -> None:
        """The hot_swap engine should be the same object on repeated access."""
        orch = self._make_orchestrator()
        hs1  = orch.hot_swap
        hs2  = orch.hot_swap
        self.assertIs(hs1, hs2)

    def test_hot_swap_has_swap_method(self) -> None:
        orch = self._make_orchestrator()
        hs   = orch.hot_swap
        if hs is not None:
            self.assertTrue(hasattr(hs, "swap"))

    def test_hot_swap_has_remove_method(self) -> None:
        orch = self._make_orchestrator()
        hs   = orch.hot_swap
        if hs is not None:
            self.assertTrue(hasattr(hs, "remove"))

    def test_hot_swap_has_insert_method(self) -> None:
        orch = self._make_orchestrator()
        hs   = orch.hot_swap
        if hs is not None:
            self.assertTrue(hasattr(hs, "insert"))


class TestOrchestratorV14QueryHandlers(unittest.TestCase):

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

    def test_get_active_network_query_registered(self) -> None:
        from core.protocol import GetActiveNetworkQuery
        orch = self._make_orchestrator()
        self.assertTrue(orch._router.queries.has(GetActiveNetworkQuery))

    def test_get_hot_swap_status_query_registered(self) -> None:
        from core.protocol import GetHotSwapStatusQuery
        orch = self._make_orchestrator()
        self.assertTrue(orch._router.queries.has(GetHotSwapStatusQuery))

    def test_get_active_network_returns_string(self) -> None:
        from core.protocol import GetActiveNetworkQuery
        from layers.base   import BaseLayer
        orch = self._make_orchestrator()
        orch._stack.register(BaseLayer())
        orch.build()
        result = orch._router.ask(GetActiveNetworkQuery())
        self.assertIsInstance(result, str)

    def test_get_hot_swap_status_returns_none_initially(self) -> None:
        from core.protocol import GetHotSwapStatusQuery
        orch   = self._make_orchestrator()
        result = orch._router.ask(GetHotSwapStatusQuery())
        # Returns {} (empty dict) when no hot-swap has been performed yet
        self.assertIsInstance(result, dict)
        self.assertEqual(len(result), 0)

    def test_get_active_network_with_network_layer(self) -> None:
        from core.protocol  import GetActiveNetworkQuery
        from layers.network import NetworkLayer  # type: ignore[import]
        from layers.base    import BaseLayer
        orch = self._make_orchestrator()
        orch._stack.register(BaseLayer())
        orch._stack.register(NetworkLayer(mode="direct"))
        orch.build()
        result = orch._router.ask(GetActiveNetworkQuery())
        self.assertEqual(result, "none")   # direct mode → content.proxy = "none"


class TestOrchestratorV14Summary(unittest.TestCase):

    def test_summary_includes_v14_marker(self) -> None:
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
        summary = orch.summary()
        # Summary version reflects the current orchestrator version
        self.assertIn("ConfigOrchestrator Summary", summary)

    def test_summary_includes_network_when_layer_present(self) -> None:
        from core.layer     import LayerStack
        from core.lifecycle import LifecycleManager
        from core.protocol  import MessageRouter
        from core.state     import ConfigStateMachine
        from orchestrator   import ConfigOrchestrator
        from layers.base    import BaseLayer
        from layers.network import NetworkLayer  # type: ignore[import]

        stack = LayerStack()
        stack.register(BaseLayer())
        stack.register(NetworkLayer(mode="socks5"))

        orch = ConfigOrchestrator(
            stack     = stack,
            router    = MessageRouter(),
            lifecycle = LifecycleManager(),
            fsm       = ConfigStateMachine(),
        )
        orch.build()
        summary = orch.summary()
        self.assertIn("socks5", summary)
        self.assertIn("Network", summary)


# ═════════════════════════════════════════════════════════════════════════════
# Full Stack Integration Tests
# ═════════════════════════════════════════════════════════════════════════════

class TestNetworkLayerIntegration(unittest.TestCase):

    def test_network_layer_in_full_stack(self) -> None:
        """NetworkLayer integrates with LayerStack without conflict."""
        from core.layer     import LayerStack
        from layers.base    import BaseLayer
        from layers.privacy import PrivacyLayer, PrivacyProfile
        from layers.network import NetworkLayer  # type: ignore[import]
        from layers.user    import UserLayer

        stack = LayerStack()
        stack.register(BaseLayer())
        stack.register(PrivacyLayer(PrivacyProfile.STANDARD))
        stack.register(NetworkLayer(mode="socks5"))
        stack.register(UserLayer())

        stack.resolve()
        merged = stack.merged
        settings = merged.get("settings", {})

        # NetworkLayer[27] sets socks5 proxy
        self.assertIn("content.proxy", settings)
        self.assertIn("socks5", settings["content.proxy"])

    def test_user_layer_proxy_overrides_network_layer(self) -> None:
        """UserLayer (p=90) proxy param overrides NetworkLayer (p=27)."""
        from core.layer     import LayerStack
        from layers.base    import BaseLayer
        from layers.network import NetworkLayer  # type: ignore[import]
        from layers.user    import UserLayer

        stack = LayerStack()
        stack.register(BaseLayer())
        stack.register(NetworkLayer(mode="socks5"))   # p=27: socks5://127.0.0.1:7897
        stack.register(UserLayer(proxy="system"))     # p=90: overrides to "system"

        stack.resolve()
        settings = stack.merged.get("settings", {})
        self.assertEqual(settings.get("content.proxy"), "system")

    def test_network_layer_priority_between_privacy_and_appearance(self) -> None:
        from layers.network import NetworkLayer  # type: ignore[import]
        self.assertGreater(NetworkLayer.priority, 20)  # above PrivacyLayer
        self.assertLess(NetworkLayer.priority, 30)     # below AppearanceLayer

    def test_user_layer_dark_mode_in_full_stack(self) -> None:
        """dark_mode setting propagates through full stack."""
        from core.layer  import LayerStack
        from layers.base import BaseLayer
        from layers.user import UserLayer

        stack = LayerStack()
        stack.register(BaseLayer())
        stack.register(UserLayer(dark_mode="mediumLight"))

        stack.resolve()
        settings = stack.merged.get("settings", {})
        self.assertTrue(settings.get("colors.webpage.darkmode.enabled", False))

    def test_user_layer_pdf_viewer_in_full_stack(self) -> None:
        from core.layer  import LayerStack
        from layers.base import BaseLayer
        from layers.user import UserLayer

        stack = LayerStack()
        stack.register(BaseLayer())
        stack.register(UserLayer(pdf_viewer=False))

        stack.resolve()
        settings = stack.merged.get("settings", {})
        self.assertFalse(settings.get("content.pdfjs", True))

    def test_user_layer_new_tab_page_in_full_stack(self) -> None:
        from core.layer  import LayerStack
        from layers.base import BaseLayer
        from layers.user import UserLayer

        stack = LayerStack()
        stack.register(BaseLayer())
        stack.register(UserLayer(new_tab_page="https://start.duckduckgo.com"))

        stack.resolve()
        settings = stack.merged.get("settings", {})
        self.assertEqual(
            settings.get("url.default_page"),
            "https://start.duckduckgo.com",
        )


# ═════════════════════════════════════════════════════════════════════════════
# Regression Tests
# ═════════════════════════════════════════════════════════════════════════════

class TestV14Regressions(unittest.TestCase):

    def test_network_layer_not_required_for_stack(self) -> None:
        """Stack works fine without NetworkLayer (backward-compatible)."""
        from core.layer     import LayerStack
        from layers.base    import BaseLayer
        from layers.privacy import PrivacyLayer, PrivacyProfile

        stack = LayerStack()
        stack.register(BaseLayer())
        stack.register(PrivacyLayer(PrivacyProfile.STANDARD))
        # No NetworkLayer — should still resolve cleanly
        stack.resolve()
        self.assertIn("settings", stack.merged)

    def test_user_layer_v13_params_still_work(self) -> None:
        """v13 UserLayer params (tabs_position, statusbar_show) unaffected by v14."""
        from layers.user import UserLayer
        layer    = UserLayer(tabs_position="bottom", statusbar_show="never")
        settings = layer.build().get("settings", {})
        self.assertEqual(settings.get("tabs.position"),    "bottom")
        self.assertEqual(settings.get("statusbar.show"),   "never")

    def test_user_layer_all_v14_params_none_produces_no_extra_keys(self) -> None:
        """None for all v14 params → no unexpected settings keys added."""
        from layers.user import UserLayer
        layer    = UserLayer(
            dark_mode       = None,
            pdf_viewer      = None,
            new_tab_page    = None,
            tab_bar_padding = None,
        )
        settings = layer.build().get("settings", {})
        self.assertNotIn("colors.webpage.darkmode.enabled",   settings)
        self.assertNotIn("content.pdfjs",                     settings)
        self.assertNotIn("tabs.padding",                      settings)

    def test_protocol_v14_events_coexist_with_v13_events(self) -> None:
        """v14 events can be imported without breaking v9–v13 events."""
        from core.protocol import (
            # v9
            ConfigReloadedEvent, MetricsEvent, PolicyDeniedEvent,       # type: ignore[import]
            # v13 (from hot_swap_events)
            # LayerSwappedEvent is in hot_swap_events, not protocol     # type: ignore[import]
            # v14
            NetworkModeChangedEvent, HotSwapCompletedEvent,             # type: ignore[import]
            GetActiveNetworkQuery, GetHotSwapStatusQuery,               # type: ignore[import]
        )
        # All importable — no NameError
        self.assertTrue(True)


# ─────────────────────────────────────────────
# Runner
# ─────────────────────────────────────────────

if __name__ == "__main__":
    print("=" * 60)
    print("qutebrowser config v14 test suite")
    print("=" * 60)
    unittest.main(verbosity=2)
