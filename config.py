"""
config.py
=========
qutebrowser Configuration Entry Point

This is the **only** file qutebrowser loads directly.
It is intentionally thin: it wires the architecture and delegates
all real work to the ``ConfigOrchestrator``.

To customize your qutebrowser, edit the **CONFIGURATION SECTION** below.
Do not touch the architecture modules unless you intend to extend them.

Compatible: qutebrowser ≥ 3.0  ·  PyQt6  ·  Python ≥ 3.11
NixOS:      paths resolve via the nix store automatically.

Strict-mode notes (Pyright):
  - ``_apply(config, c)`` parameters annotated as ``Any`` — qutebrowser
    injects these objects at runtime; no stub types are available.
  - Event subscriber lambdas cast to the concrete event type so Pyright
    can resolve the subclass-specific attributes (layer_name, key_count, …).
  - Lifecycle decorator functions are assigned to ``_`` to suppress the
    ``reportUnusedFunction`` diagnostic (the decorator already registers them;
    the local name is intentionally discarded).
  - ``ConfigEvent`` import removed — it was imported but not used in this file.
  - ``ThemeChangedEvent`` subscriber cast similarly to ``ThemeChangedEvent``.
"""

from __future__ import annotations

import logging
import os
import sys
from typing import Any

# ── Make core/ and layers/ importable ─────────────────────────────────────────
_config_dir = os.path.dirname(os.path.abspath(__file__))
if _config_dir not in sys.path:
    sys.path.insert(0, _config_dir)

# ── Architecture ──────────────────────────────────────────────────────────────
from core.layer     import LayerStack
from core.lifecycle import LifecycleHook, LifecycleManager
from core.protocol  import (
    ConfigErrorEvent,
    Event,
    LayerAppliedEvent,
    MessageRouter,
    ThemeChangedEvent,
)
from core.state import ConfigStateMachine

from layers.appearance  import AppearanceLayer
from layers.base        import BaseLayer
from layers.behavior    import BehaviorLayer
from layers.performance import PerformanceLayer, PerformanceProfile
from layers.privacy     import PrivacyLayer, PrivacyProfile
from layers.user        import UserLayer

from orchestrator import ConfigApplier, ConfigOrchestrator

# ── Logging ───────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="[qute-config] %(name)s %(levelname)s: %(message)s",
)
logger = logging.getLogger("qute.config")


# ╔══════════════════════════════════════════════════════════════════════════╗
# ║                       CONFIGURATION SECTION                              ║
# ║                                                                          ║
# ║  Edit this section to personalise your qutebrowser.                      ║
# ║  All other files are architecture — extend, don't modify them.           ║
# ╚══════════════════════════════════════════════════════════════════════════╝

# ── Theme ─────────────────────────────────────────────────────────────────────
# Options: catppuccin-mocha | catppuccin-latte | gruvbox-dark | tokyo-night | rose-pine
THEME = "catppuccin-mocha"

# ── Privacy ───────────────────────────────────────────────────────────────────
# Options: PrivacyProfile.STANDARD | HARDENED | PARANOID
PRIVACY_PROFILE = PrivacyProfile.STANDARD

# ── Performance ───────────────────────────────────────────────────────────────
# Options: PerformanceProfile.BALANCED | HIGH | LOW | LAPTOP
PERFORMANCE_PROFILE = PerformanceProfile.BALANCED

# ── Leader key ────────────────────────────────────────────────────────────────
# Used as prefix for multi-key bindings (e.g. ",r" reloads config).
LEADER_KEY = ","

# ── Layer enable / disable ────────────────────────────────────────────────────
# Set a value to False to completely skip that layer.
LAYERS: dict[str, bool] = {
    "base":        True,
    "privacy":     True,
    "appearance":  True,
    "behavior":    True,
    "performance": True,
    "user":        True,   # personal overrides — always keep True unless debugging
}


# ╔══════════════════════════════════════════════════════════════════════════╗
# ║                         WIRING SECTION                                   ║
# ║                                                                          ║
# ║  Composition root — dependencies assembled here.                         ║
# ╚══════════════════════════════════════════════════════════════════════════╝

def _build_orchestrator() -> ConfigOrchestrator:
    """Build and wire the full orchestrator.  Pure Python, no side effects."""

    # ── Infrastructure ────────────────────────────────────────────────
    router    = MessageRouter()
    lifecycle = LifecycleManager()
    fsm       = ConfigStateMachine()

    # ── Layer Stack ───────────────────────────────────────────────────
    stack = LayerStack()

    if LAYERS.get("base"):
        stack.register(BaseLayer())

    if LAYERS.get("privacy"):
        # Pass leader so privacy keybindings (,j ,i ,c ,s) respect LEADER_KEY.
        stack.register(PrivacyLayer(profile=PRIVACY_PROFILE, leader=LEADER_KEY))

    if LAYERS.get("appearance"):
        stack.register(AppearanceLayer(theme=THEME))

    if LAYERS.get("behavior"):
        stack.register(BehaviorLayer(leader=LEADER_KEY))

    if LAYERS.get("performance"):
        stack.register(PerformanceLayer(profile=PERFORMANCE_PROFILE))

    if LAYERS.get("user"):
        # UserLayer is registered last (priority=90) so it wins over everything.
        stack.register(UserLayer(leader=LEADER_KEY))

    # ── Lifecycle hooks ───────────────────────────────────────────────
    # Assign to _ to avoid Pyright's reportUnusedFunction.  The decorator
    # registers the function internally; the local binding is not needed.
    @lifecycle.decorator(LifecycleHook.POST_APPLY, priority=100)
    def _log_apply_done() -> None:
        logger.info("✓ qutebrowser config applied successfully")

    @lifecycle.decorator(LifecycleHook.ON_ERROR, priority=10)
    def _log_error() -> None:
        logger.error("✗ config apply encountered errors — check :messages")

    # ── Event observers ───────────────────────────────────────────────
    # Cast the generic Event to the concrete subtype inside each lambda so
    # Pyright can resolve the subclass-specific attributes without raising
    # reportAttributeAccessIssue / reportUnknownMemberType.

    def _on_layer_applied(e: Event) -> None:
        evt = e if isinstance(e, LayerAppliedEvent) else LayerAppliedEvent()
        logger.info("layer applied: %-12s (%d settings)", evt.layer_name, evt.key_count)

    def _on_config_error(e: Event) -> None:
        evt = e if isinstance(e, ConfigErrorEvent) else ConfigErrorEvent()
        logger.error("config error [%s]: %s", evt.layer_name or "?", evt.error_msg)

    def _on_theme_changed(e: Event) -> None:
        evt = e if isinstance(e, ThemeChangedEvent) else ThemeChangedEvent()
        logger.info("theme changed: %s", evt.theme_name)

    router.events.subscribe(LayerAppliedEvent, _on_layer_applied)
    router.events.subscribe(ConfigErrorEvent,  _on_config_error)
    router.events.subscribe(ThemeChangedEvent, _on_theme_changed)

    return ConfigOrchestrator(
        stack=stack,
        router=router,
        lifecycle=lifecycle,
        fsm=fsm,
    )


# ╔══════════════════════════════════════════════════════════════════════════╗
# ║                        EXECUTION SECTION                                 ║
# ║                                                                          ║
# ║  Runs when qutebrowser loads config.py.                                  ║
# ║  `config` and `c` are injected by qutebrowser into this namespace.       ║
# ╚══════════════════════════════════════════════════════════════════════════╝

def _apply(config: Any, c: Any) -> None:
    """
    Main entry point called by qutebrowser.

    Args:
        config: qutebrowser config object — provides ``.set()``, ``.bind()``, etc.
        c:      qutebrowser config container — attribute-style access.
    """
    try:
        orchestrator = _build_orchestrator()

        # Phase 1: Build — resolve all layers into merged config
        orchestrator.build()
        logger.info("[config.py] \n%s", orchestrator.summary())

        # Phase 2: Apply — write to qutebrowser API
        applier = ConfigApplier(config, c)
        errors = orchestrator.apply(applier)

        # Phase 3: Per-host policy overrides
        host_errors = orchestrator.apply_host_policies(applier)
        errors.extend(host_errors)

        if errors:
            logger.warning(
                "[config.py] %d error(s) during apply — see individual messages above",
                len(errors),
            )
        else:
            logger.info("[config.py] ✓ all layers applied cleanly")

    except Exception as exc:
        logger.exception("[config.py] FATAL: config apply failed: %s", exc)
        # Do NOT re-raise: qutebrowser should still start with whatever
        # partial config was applied before the failure.


# ── qutebrowser injects `config` and `c` into this module's global namespace.
try:
    # Load (or explicitly skip) GUI-configured autoconfig.yml.
    # False = don't load autoconfig; all settings are managed by this file.
    config.load_autoconfig(False)  # type: ignore[name-defined]
    _apply(config, c)              # type: ignore[name-defined]
except NameError:
    # Running outside qutebrowser (e.g. linting, tests) — skip apply.
    logger.info("[config.py] running outside qutebrowser — skipping _apply()")
