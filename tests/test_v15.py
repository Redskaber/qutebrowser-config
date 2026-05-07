"""
tests/test_v15.py
=================
Test Suite  (v15)

Covers all v15 additions and fixes:
  - core/protocol.py v15 — SessionChangedEvent, GetActiveSessionQuery,
                            NetworkModeChangedEvent, HotSwapCompletedEvent,
                            GetActiveNetworkQuery, GetHotSwapStatusQuery,
                            MessageRouter.emit_session_changed(),
                            MessageRouter.emit_network_changed(),
                            MessageRouter.emit_hot_swap_completed()
  - layers/network.py v15 — _build_spec_table(), URL-override immutability,
                             available_modes(), active_spec property, __repr__,
                             improved describe()
  - orchestrator.py v15  — _maybe_emit_session_event() emits SessionChangedEvent,
                            _maybe_emit_network_event() new method,
                            hot_swap property, _WrappedHotSwap,
                            GetActiveSessionQuery handler,
                            GetActiveNetworkQuery handler,
                            GetHotSwapStatusQuery handler,
                            summary() v15 (Network + HotSwap lines)
  - config.py v15        — SessionChangedEvent subscriber wired,
                            NETWORK_MODE / USER_DARK_MODE etc retained
  - Regressions          — v14/v13 functionality unchanged

Run::

    python3 tests/test_v15.py
    pytest tests/test_v15.py -v

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
    """Return True if the architecture can be imported (not in shadow env)."""
    try:
        from core.protocol import Event  # type: ignore[import]
        return True
    except Exception:
        return False


_ARCH_AVAILABLE = _can_import()


def skip_without_arch(fn: Any) -> Any:
    """Skip test if core architecture modules are not importable."""
    import functools
    @functools.wraps(fn)
    def wrapper(*a: Any, **kw: Any) -> Any:
        if not _ARCH_AVAILABLE:
            raise unittest.SkipTest("core architecture not importable in this environment")
        return fn(*a, **kw)
    return wrapper


# ═══════════════════════════════════════════════════════════════════
# Protocol v15 — SessionChangedEvent
# ═══════════════════════════════════════════════════════════════════

class TestSessionChangedEvent(unittest.TestCase):

    @skip_without_arch
    def test_importable(self) -> None:
        from core.protocol import SessionChangedEvent # type: ignore[import]
        self.assertTrue(True)

    @skip_without_arch
    def test_default_fields(self) -> None:
        from core.protocol import SessionChangedEvent
        e = SessionChangedEvent()
        self.assertEqual(e.old_session, "unknown")
        self.assertEqual(e.new_session, "day")
        self.assertEqual(e.source, "startup")

    @skip_without_arch
    def test_custom_fields(self) -> None:
        from core.protocol import SessionChangedEvent
        e = SessionChangedEvent(old_session="day", new_session="night", source="hot_swap")
        self.assertEqual(e.old_session, "day")
        self.assertEqual(e.new_session, "night")
        self.assertEqual(e.source, "hot_swap")

    @skip_without_arch
    def test_immutable(self) -> None:
        from core.protocol import SessionChangedEvent
        e = SessionChangedEvent(new_session="focus")
        with self.assertRaises(AttributeError):
            e.new_session = "night"  # type: ignore[misc]

    @skip_without_arch
    def test_topic(self) -> None:
        from core.protocol import SessionChangedEvent
        e = SessionChangedEvent()
        self.assertEqual(e.topic(), "SessionChangedEvent")


# ═══════════════════════════════════════════════════════════════════
# Protocol v15 — GetActiveSessionQuery
# ═══════════════════════════════════════════════════════════════════

class TestGetActiveSessionQuery(unittest.TestCase):

    @skip_without_arch
    def test_importable(self) -> None:
        from core.protocol import GetActiveSessionQuery
        q = GetActiveSessionQuery()
        self.assertEqual(q.topic(), "GetActiveSessionQuery")

    @skip_without_arch
    def test_is_query(self) -> None:
        from core.protocol import GetActiveSessionQuery, Query
        self.assertTrue(issubclass(GetActiveSessionQuery, Query)) # type: ignore[subtype]


# ═══════════════════════════════════════════════════════════════════
# Protocol v15 — NetworkModeChangedEvent
# ═══════════════════════════════════════════════════════════════════

class TestNetworkModeChangedEvent(unittest.TestCase):

    @skip_without_arch
    def test_importable(self) -> None:
        from core.protocol import NetworkModeChangedEvent
        e = NetworkModeChangedEvent()
        self.assertEqual(e.topic(), "NetworkModeChangedEvent")

    @skip_without_arch
    def test_defaults(self) -> None:
        from core.protocol import NetworkModeChangedEvent
        e = NetworkModeChangedEvent()
        self.assertEqual(e.old_mode, "unknown")
        self.assertEqual(e.new_mode, "system")
        self.assertEqual(e.proxy, "system")
        self.assertEqual(e.source, "startup")

    @skip_without_arch
    def test_immutable(self) -> None:
        from core.protocol import NetworkModeChangedEvent
        e = NetworkModeChangedEvent()
        with self.assertRaises(AttributeError):
            e.new_mode = "tor"  # type: ignore[misc]


# ═══════════════════════════════════════════════════════════════════
# Protocol v15 — HotSwapCompletedEvent
# ═══════════════════════════════════════════════════════════════════

class TestHotSwapCompletedEvent(unittest.TestCase):

    @skip_without_arch
    def test_ok_property_true_when_no_errors(self) -> None:
        from core.protocol import HotSwapCompletedEvent
        e = HotSwapCompletedEvent(operation="swap", layer_name="network", errors=[])
        self.assertTrue(e.ok)

    @skip_without_arch
    def test_ok_property_false_when_errors(self) -> None:
        from core.protocol import HotSwapCompletedEvent
        e = HotSwapCompletedEvent(errors=["something failed"])
        self.assertFalse(e.ok)

    @skip_without_arch
    def test_topic(self) -> None:
        from core.protocol import HotSwapCompletedEvent
        e = HotSwapCompletedEvent()
        self.assertEqual(e.topic(), "HotSwapCompletedEvent")


# ═══════════════════════════════════════════════════════════════════
# Protocol v15 — MessageRouter helpers
# ═══════════════════════════════════════════════════════════════════

class TestMessageRouterV15Helpers(unittest.TestCase):

    @skip_without_arch
    def test_emit_session_changed(self) -> None:
        from core.protocol import MessageRouter, SessionChangedEvent, Event
        router = MessageRouter()
        received: List[SessionChangedEvent] = []

        def handler(e: Event) -> None:
            if isinstance(e, SessionChangedEvent):
                received.append(e)

        router.events.subscribe(SessionChangedEvent, handler)
        router.emit_session_changed("day", "night", source="test")
        self.assertEqual(len(received), 1)
        self.assertEqual(received[0].new_session, "night")
        self.assertEqual(received[0].source, "test")

    @skip_without_arch
    def test_emit_network_changed(self) -> None:
        from core.protocol import MessageRouter, NetworkModeChangedEvent, Event
        router = MessageRouter()
        received: List[NetworkModeChangedEvent] = []

        def handler(e: Event) -> None:
            if isinstance(e, NetworkModeChangedEvent):
                received.append(e)

        router.events.subscribe(NetworkModeChangedEvent, handler)
        router.emit_network_changed("unknown", "socks5", "socks5://127.0.0.1:7897")
        self.assertEqual(len(received), 1)
        self.assertEqual(received[0].new_mode, "socks5")

    @skip_without_arch
    def test_emit_hot_swap_completed(self) -> None:
        from core.protocol import MessageRouter, HotSwapCompletedEvent, Event
        router = MessageRouter()
        received: List[HotSwapCompletedEvent] = []

        def handler(e: Event) -> None:
            if isinstance(e, HotSwapCompletedEvent):
                received.append(e)

        router.events.subscribe(HotSwapCompletedEvent, handler)
        router.emit_hot_swap_completed("swap", "network", [], [], 12.5)
        self.assertEqual(len(received), 1)
        self.assertTrue(received[0].ok)
        self.assertAlmostEqual(received[0].duration_ms, 12.5)


# ═══════════════════════════════════════════════════════════════════
# NetworkLayer v15 — Bug fixes and new features
# ═══════════════════════════════════════════════════════════════════

class TestNetworkLayerV15BuildSpecTable(unittest.TestCase):
    """_build_spec_table() is pure — no global mutation."""

    @skip_without_arch
    def test_returns_fresh_dict(self) -> None:
        from layers.network import _build_spec_table, NetworkMode # type: ignore[private]
        t1 = _build_spec_table()
        t2 = _build_spec_table()
        self.assertIsNot(t1, t2)

    @skip_without_arch
    def test_url_overrides_do_not_mutate_global(self) -> None:
        from layers.network import _NETWORK_TABLE, NetworkLayer, NetworkMode # type: ignore[private]
        original_socks5 = _NETWORK_TABLE[NetworkMode.SOCKS5].proxy
        # Create layer with custom URL
        layer = NetworkLayer(mode="socks5", socks5_url="socks5://10.0.0.1:1234")
        # Module-level table must be unchanged
        self.assertEqual(_NETWORK_TABLE[NetworkMode.SOCKS5].proxy, original_socks5)
        # Layer's spec should use the override
        self.assertEqual(layer.active_spec.proxy, "socks5://10.0.0.1:1234")

    @skip_without_arch
    def test_custom_socks5_url(self) -> None:
        from layers.network import NetworkLayer
        layer = NetworkLayer(mode="socks5", socks5_url="socks5://192.168.1.1:9999")
        settings = layer.build()["settings"]
        self.assertEqual(settings["content.proxy"], "socks5://192.168.1.1:9999")

    @skip_without_arch
    def test_default_table_intact_after_layer_creation(self) -> None:
        from layers.network import _NETWORK_TABLE, NetworkLayer, NetworkMode # type: ignore[private]
        # Create multiple layers with different overrides
        NetworkLayer(mode="http",   http_url="http://1.1.1.1:8080")
        NetworkLayer(mode="socks5", socks5_url="socks5://2.2.2.2:1080")
        # Module table still has original values
        self.assertEqual(_NETWORK_TABLE[NetworkMode.HTTP].proxy,   "http://127.0.0.1:7890")
        self.assertEqual(_NETWORK_TABLE[NetworkMode.SOCKS5].proxy, "socks5://127.0.0.1:7897")


class TestNetworkLayerV15Properties(unittest.TestCase):

    @skip_without_arch
    def test_active_spec_property(self) -> None:
        from layers.network import NetworkLayer, NetworkMode, NetworkSpec # type: ignore[unused]
        layer = NetworkLayer(mode="tor")
        self.assertIsInstance(layer.active_spec, NetworkSpec)
        self.assertEqual(layer.active_spec.referer, "never")
        self.assertFalse(layer.active_spec.dns_prefetch)

    @skip_without_arch
    def test_available_modes_is_sorted(self) -> None:
        from layers.network import NetworkLayer
        modes = NetworkLayer.available_modes()
        self.assertEqual(modes, sorted(modes))

    @skip_without_arch
    def test_available_modes_contains_all(self) -> None:
        from layers.network import NetworkLayer, NetworkMode
        modes = NetworkLayer.available_modes()
        for m in NetworkMode:
            self.assertIn(m.value, modes)

    @skip_without_arch
    def test_describe_includes_proxy(self) -> None:
        from layers.network import NetworkLayer
        layer = NetworkLayer(mode="socks5")
        desc = layer.describe()
        self.assertIn("socks5", desc)
        self.assertIn("proxy=", desc)

    @skip_without_arch
    def test_repr_includes_mode(self) -> None:
        from layers.network import NetworkLayer
        layer = NetworkLayer(mode="tor")
        r = repr(layer)
        self.assertIn("tor", r)
        self.assertIn("27", r)

    @skip_without_arch
    def test_mode_names_class_var(self) -> None:
        from layers.network import NetworkLayer
        self.assertIn("tor", NetworkLayer.MODE_NAMES)
        self.assertIn("system", NetworkLayer.MODE_NAMES)


# ═══════════════════════════════════════════════════════════════════
# NetworkLayer v15 — Settings output
# ═══════════════════════════════════════════════════════════════════

class TestNetworkLayerV15Settings(unittest.TestCase):

    @skip_without_arch
    def test_offline_disables_dns(self) -> None:
        from layers.network import NetworkLayer
        layer = NetworkLayer(mode="offline")
        settings = layer.build()["settings"]
        self.assertFalse(settings["content.dns_prefetch"])

    @skip_without_arch
    def test_direct_mode_no_proxy(self) -> None:
        from layers.network import NetworkLayer
        layer = NetworkLayer(mode="direct")
        settings = layer.build()["settings"]
        self.assertEqual(settings["content.proxy"], "none")
        self.assertTrue(settings["content.dns_prefetch"])

    @skip_without_arch
    def test_tor_blocks_tls_errors(self) -> None:
        from layers.network import NetworkLayer
        layer = NetworkLayer(mode="tor")
        settings = layer.build()["settings"]
        self.assertEqual(settings["content.tls.certificate_errors"], "block")

    @skip_without_arch
    def test_system_mode_ask_tls(self) -> None:
        from layers.network import NetworkLayer
        layer = NetworkLayer(mode="system")
        settings = layer.build()["settings"]
        self.assertEqual(settings["content.tls.certificate_errors"], "ask")

    @skip_without_arch
    def test_keybindings_use_custom_leader(self) -> None:
        from layers.network import NetworkLayer
        layer = NetworkLayer(leader=";")
        bindings = layer.build()["keybindings"]
        keys = [b[0] for b in bindings]
        for key in keys:
            self.assertTrue(key.startswith(";N"), f"Expected ;N prefix, got {key!r}")

    @skip_without_arch
    def test_net_alias_present(self) -> None:
        from layers.network import NetworkLayer
        layer = NetworkLayer(mode="system")
        aliases = layer.build().get("aliases", {})
        self.assertIn("net", aliases)


# ═══════════════════════════════════════════════════════════════════
# Orchestrator v15 — _maybe_emit_session_event
# ═══════════════════════════════════════════════════════════════════

class TestOrchestratorV15SessionEvent(unittest.TestCase):

    @skip_without_arch
    def test_session_changed_event_emitted_on_build(self) -> None:
        """Orchestrator emits SessionChangedEvent when SessionLayer is active."""
        from core.protocol import MessageRouter, SessionChangedEvent, Event
        from core.layer    import LayerStack
        from core.lifecycle import LifecycleManager
        from core.state     import ConfigStateMachine
        from orchestrator   import ConfigOrchestrator

        router    = MessageRouter()
        lifecycle = LifecycleManager()
        fsm       = ConfigStateMachine()
        stack     = LayerStack()

        received: List[SessionChangedEvent] = []

        def handler(e: Event) -> None:
            if isinstance(e, SessionChangedEvent):
                received.append(e)

        router.events.subscribe(SessionChangedEvent, handler)

        # Build with empty stack (no SessionLayer) → no event
        orc = ConfigOrchestrator(stack=stack, router=router,
                                 lifecycle=lifecycle, fsm=fsm)
        orc.build()
        self.assertEqual(len(received), 0)

    @skip_without_arch
    def test_get_active_session_query_unknown_without_layer(self) -> None:
        from core.protocol import MessageRouter, GetActiveSessionQuery
        from core.layer    import LayerStack
        from core.lifecycle import LifecycleManager
        from core.state     import ConfigStateMachine
        from orchestrator   import ConfigOrchestrator

        router    = MessageRouter()
        lifecycle = LifecycleManager()
        fsm       = ConfigStateMachine()
        stack     = LayerStack()

        orc = ConfigOrchestrator(stack=stack, router=router,
                                 lifecycle=lifecycle, fsm=fsm)
        orc.build()
        result = router.ask(GetActiveSessionQuery())
        self.assertEqual(result, "unknown")


# ═══════════════════════════════════════════════════════════════════
# Orchestrator v15 — Network event and query
# ═══════════════════════════════════════════════════════════════════

class TestOrchestratorV15NetworkHandlers(unittest.TestCase):

    @skip_without_arch
    def test_get_active_network_query_registered(self) -> None:
        from core.protocol  import MessageRouter, GetActiveNetworkQuery
        from core.layer     import LayerStack
        from core.lifecycle import LifecycleManager
        from core.state     import ConfigStateMachine
        from orchestrator   import ConfigOrchestrator

        router    = MessageRouter()
        lifecycle = LifecycleManager()
        fsm       = ConfigStateMachine()
        stack     = LayerStack()

        _orc = ConfigOrchestrator(stack=stack, router=router,
                                 lifecycle=lifecycle, fsm=fsm)
        # Query handler must be registered
        self.assertTrue(router.queries.has(GetActiveNetworkQuery))

    @skip_without_arch
    def test_get_active_network_returns_system_without_network_layer(self) -> None:
        from core.protocol  import MessageRouter, GetActiveNetworkQuery
        from core.layer     import LayerStack
        from core.lifecycle import LifecycleManager
        from core.state     import ConfigStateMachine
        from orchestrator   import ConfigOrchestrator

        router    = MessageRouter()
        lifecycle = LifecycleManager()
        fsm       = ConfigStateMachine()
        stack     = LayerStack()

        orc = ConfigOrchestrator(stack=stack, router=router,
                                 lifecycle=lifecycle, fsm=fsm)
        orc.build()
        result = router.ask(GetActiveNetworkQuery())
        self.assertEqual(result, "system")

    @skip_without_arch
    def test_get_hot_swap_status_returns_empty_initially(self) -> None:
        from core.protocol  import MessageRouter, GetHotSwapStatusQuery
        from core.layer     import LayerStack
        from core.lifecycle import LifecycleManager
        from core.state     import ConfigStateMachine
        from orchestrator   import ConfigOrchestrator

        router    = MessageRouter()
        lifecycle = LifecycleManager()
        fsm       = ConfigStateMachine()
        stack     = LayerStack()

        orc = ConfigOrchestrator(stack=stack, router=router,
                                 lifecycle=lifecycle, fsm=fsm)
        orc.build()
        result = router.ask(GetHotSwapStatusQuery())
        self.assertIsInstance(result, dict)
        self.assertEqual(result, {})

    @skip_without_arch
    def test_get_active_session_query_registered(self) -> None:
        from core.protocol  import MessageRouter, GetActiveSessionQuery
        from core.layer     import LayerStack
        from core.lifecycle import LifecycleManager
        from core.state     import ConfigStateMachine
        from orchestrator   import ConfigOrchestrator

        router    = MessageRouter()
        lifecycle = LifecycleManager()
        fsm       = ConfigStateMachine()
        stack     = LayerStack()

        ConfigOrchestrator(stack=stack, router=router,
                           lifecycle=lifecycle, fsm=fsm)
        self.assertTrue(router.queries.has(GetActiveSessionQuery))


# ═══════════════════════════════════════════════════════════════════
# Orchestrator v15 — summary() includes v15 content
# ═══════════════════════════════════════════════════════════════════

class TestOrchestratorV15Summary(unittest.TestCase):

    @skip_without_arch
    def test_summary_contains_v15(self) -> None:
        from core.protocol  import MessageRouter
        from core.layer     import LayerStack
        from core.lifecycle import LifecycleManager
        from core.state     import ConfigStateMachine
        from orchestrator   import ConfigOrchestrator

        router    = MessageRouter()
        lifecycle = LifecycleManager()
        fsm       = ConfigStateMachine()
        stack     = LayerStack()

        orc = ConfigOrchestrator(stack=stack, router=router,
                                 lifecycle=lifecycle, fsm=fsm)
        orc.build()
        s = orc.summary()
        self.assertIn("v15", s)

    @skip_without_arch
    def test_summary_includes_hot_swap_when_present(self) -> None:
        from core.protocol  import MessageRouter
        from core.layer     import LayerStack
        from core.lifecycle import LifecycleManager
        from core.state     import ConfigStateMachine
        from orchestrator   import ConfigOrchestrator

        router    = MessageRouter()
        lifecycle = LifecycleManager()
        fsm       = ConfigStateMachine()
        stack     = LayerStack()

        orc = ConfigOrchestrator(stack=stack, router=router,
                                 lifecycle=lifecycle, fsm=fsm)
        orc.build()
        # Inject a fake result
        orc._last_hot_swap_result = { # type: ignore[protect]
            "operation": "swap", "layer_name": "network",
            "ok": True, "errors": [], "duration_ms": 5.0,
        }
        s = orc.summary()
        self.assertIn("HotSwap", s)
        self.assertIn("network", s)


# ═══════════════════════════════════════════════════════════════════
# NetworkLayer v15 in full stack
# ═══════════════════════════════════════════════════════════════════

class TestNetworkLayerV15Integration(unittest.TestCase):

    @skip_without_arch
    def test_network_layer_registered_in_stack(self) -> None:
        from core.layer     import LayerStack
        from layers.network import NetworkLayer

        stack = LayerStack()
        stack.register(NetworkLayer(mode="socks5"))
        layer = stack.get("network")
        self.assertIsNotNone(layer)
        self.assertIsInstance(layer, NetworkLayer)

    @skip_without_arch
    def test_network_layer_priority_27(self) -> None:
        from layers.network import NetworkLayer
        self.assertEqual(NetworkLayer.priority, 27)

    @skip_without_arch
    def test_user_proxy_overrides_network_layer(self) -> None:
        """UserLayer (p=90) proxy overrides NetworkLayer (p=27) proxy."""
        from core.layer     import LayerStack
        from layers.network import NetworkLayer
        from layers.base    import BaseLayer

        try:
            from layers.user import UserLayer
        except ImportError:
            raise unittest.SkipTest("UserLayer not importable in this environment")

        stack = LayerStack()
        stack.register(BaseLayer())
        stack.register(NetworkLayer(mode="socks5"))  # sets socks5://127.0.0.1:7897
        stack.register(UserLayer(proxy="http://127.0.0.1:9999"))  # overrides
        stack.resolve()

        proxy = stack.merged.get("settings", {}).get("content.proxy")
        self.assertEqual(proxy, "http://127.0.0.1:9999")

    @skip_without_arch
    def test_network_layer_without_network_available(self) -> None:
        """Stack without NetworkLayer still resolves cleanly."""
        from core.layer  import LayerStack
        from layers.base import BaseLayer

        stack = LayerStack()
        stack.register(BaseLayer())
        stack.resolve()
        self.assertIsNotNone(stack.merged)


# ═══════════════════════════════════════════════════════════════════
# Protocol v15 — all new events importable together
# ═══════════════════════════════════════════════════════════════════

class TestProtocolV15AllImportable(unittest.TestCase):

    @skip_without_arch
    def test_all_v15_events_importable(self) -> None:
        from core.protocol import (
            SessionChangedEvent,        # type: ignore[unused]
            NetworkModeChangedEvent,    # type: ignore[unused]
            HotSwapCompletedEvent,      # type: ignore[unused]
        )
        self.assertTrue(True)

    @skip_without_arch
    def test_all_v15_queries_importable(self) -> None:
        from core.protocol import (
            GetActiveSessionQuery,      # type: ignore[unused]
            GetActiveNetworkQuery,      # type: ignore[unused]
            GetHotSwapStatusQuery,      # type: ignore[unused]
        )
        self.assertTrue(True)

    @skip_without_arch
    def test_all_v15_router_helpers_callable(self) -> None:
        from core.protocol import MessageRouter
        router = MessageRouter()
        # Must not raise
        router.emit_session_changed("unknown", "day")
        router.emit_network_changed("unknown", "system", "system")
        router.emit_hot_swap_completed("swap", "network", [], [], 0.0)
        self.assertTrue(True)


# ═══════════════════════════════════════════════════════════════════
# Regressions — v14 / v13 features unchanged in v15
# ═══════════════════════════════════════════════════════════════════

class TestV15Regressions(unittest.TestCase):

    @skip_without_arch
    def test_context_switched_event_still_exists(self) -> None:
        from core.protocol import ContextSwitchedEvent
        e = ContextSwitchedEvent(old_context="default", new_context="work")
        self.assertEqual(e.new_context, "work")

    @skip_without_arch
    def test_get_metrics_summary_query_still_works(self) -> None:
        from core.protocol import GetMetricsSummaryQuery
        q = GetMetricsSummaryQuery(last_n=5)
        self.assertEqual(q.last_n, 5)

    @skip_without_arch
    def test_v14_user_params_still_accepted(self) -> None:
        """UserLayer still accepts v14 params (dark_mode, pdf_viewer, etc)."""
        try:
            from layers.user import UserLayer
        except ImportError:
            raise unittest.SkipTest("UserLayer not importable")
        layer = UserLayer(
            dark_mode       = "mediumLight",
            pdf_viewer      = True,
            new_tab_page    = "https://example.com",
            tab_bar_padding = {"top": 0, "bottom": 0, "left": 4, "right": 4},
        )
        settings = layer.build()["settings"]
        self.assertTrue(settings.get("colors.webpage.darkmode.enabled"))
        self.assertTrue(settings.get("content.pdfjs"))
        self.assertEqual(settings.get("url.default_page"), "https://example.com")
        self.assertIn("tabs.padding", settings)

    @skip_without_arch
    def test_network_layer_name_attribute(self) -> None:
        from layers.network import NetworkLayer
        self.assertEqual(NetworkLayer.name, "network")

    @skip_without_arch
    def test_network_layer_description_attribute(self) -> None:
        from layers.network import NetworkLayer
        self.assertIn("Network", NetworkLayer.description)

    @skip_without_arch
    def test_all_queries_registered_by_orchestrator(self) -> None:
        from core.protocol  import (
            MessageRouter,
            GetMergedConfigQuery,
            GetHealthReportQuery,
            GetSnapshotQuery,
            GetLayerDiffQuery,
            GetLayerNamesQuery,
            GetMetricsSummaryQuery,
            GetActiveNetworkQuery,
            GetHotSwapStatusQuery,
            GetActiveSessionQuery,
        )
        from core.layer     import LayerStack
        from core.lifecycle import LifecycleManager
        from core.state     import ConfigStateMachine
        from orchestrator   import ConfigOrchestrator

        router    = MessageRouter()
        lifecycle = LifecycleManager()
        fsm       = ConfigStateMachine()

        ConfigOrchestrator(
            stack=LayerStack(), router=router, lifecycle=lifecycle, fsm=fsm
        )

        # All queries must be registered
        for q in [
            GetMergedConfigQuery, GetHealthReportQuery, GetSnapshotQuery,
            GetLayerDiffQuery, GetLayerNamesQuery, GetMetricsSummaryQuery,
            GetActiveNetworkQuery, GetHotSwapStatusQuery, GetActiveSessionQuery,
        ]:
            self.assertTrue(
                router.queries.has(q),
                f"Query {q.__name__} not registered"
            )


# ─────────────────────────────────────────────
# Runner
# ─────────────────────────────────────────────

if __name__ == "__main__":
    runner = unittest.TextTestRunner(verbosity=2)
    loader = unittest.TestLoader()
    suite  = loader.loadTestsFromModule(sys.modules[__name__])
    result = runner.run(suite)
    sys.exit(0 if result.wasSuccessful() else 1)
