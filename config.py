"""
config.py
=========
qutebrowser Configuration Entry Point

This is the **only** file qutebrowser loads directly.
It is intentionally thin: it wires the architecture and delegates
all real work to the ConfigOrchestrator.

╔══════════════════════════════════════════════════════════════════════════╗
║  To customize your qutebrowser, edit the CONFIGURATION SECTION below.    ║
║  That is the ONLY section you need to touch.                             ║
║  All other files are architecture — extend, don't edit them.             ║
╚══════════════════════════════════════════════════════════════════════════╝

Compatible: qutebrowser ≥ 3.0  ·  PyQt6  ·  Python ≥ 3.11
NixOS:      paths resolve via the nix store automatically.

Strict-mode notes (Pyright):
  - _apply(config, c) parameters annotated as Any — qutebrowser injects
    these at runtime; no stub types are available.
  - Event subscriber functions cast to concrete event type inside each body.
  - Lifecycle decorator return values assigned to _ to suppress
    reportUnusedFunction.
"""

from __future__ import annotations

import logging
import os
import sys
from typing import Any

# ── Make all sub-packages importable ──────────────────────────────────────────
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

# ── Extended themes (optional; graceful fallback if themes/ absent) ───────────
try:
    from themes.extended import register_all_themes
    register_all_themes()
except ImportError:
    pass

# ── Host policy registry (optional; graceful fallback) ────────────────────────
try:
    from policies.host import build_default_host_registry as _build_host_registry
    _HOST_REGISTRY_AVAILABLE = True
except ImportError:
    _HOST_REGISTRY_AVAILABLE = False

# ── Logging ───────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="[qute-config] %(name)s %(levelname)s: %(message)s",
)
logger = logging.getLogger("qute.config")


# ╔══════════════════════════════════════════════════════════════════════════╗
# ║                       CONFIGURATION SECTION                              ║
# ║                                                                          ║
# ║  THIS IS THE ONLY SECTION YOU SHOULD EDIT.                               ║
# ║  Every setting here drives the architecture below.                       ║
# ╚══════════════════════════════════════════════════════════════════════════╝

# ── Theme ─────────────────────────────────────────────────────────────────────
# Built-in (5):
#   catppuccin-mocha | catppuccin-latte | gruvbox-dark | tokyo-night | rose-pine
# Extended (13):
#   nord | dracula | solarized-dark | solarized-light | one-dark
#   everforest-dark | gruvbox-light | modus-vivendi
#   catppuccin-macchiato | catppuccin-frappe | kanagawa | palenight
#   glass  ← modern · minimal · premium; frosted-glass / Gaussian-blur aesthetic
# Custom:    add to themes/extended.py, then use the name here
THEME = "glass"

# ── Privacy ───────────────────────────────────────────────────────────────────
# STANDARD  → sensible defaults, minimal breakage
# HARDENED  → stronger protection; some login-required sites need exceptions
# PARANOID  → maximum privacy; JS/images off, expect significant breakage
PRIVACY_PROFILE = PrivacyProfile.STANDARD

# ── Performance ───────────────────────────────────────────────────────────────
# BALANCED  → good for most hardware
# HIGH      → more memory, faster (desktop with ample RAM)
# LOW       → constrained memory
# LAPTOP    → battery-aware: smaller cache, DNS prefetch off
PERFORMANCE_PROFILE = PerformanceProfile.BALANCED

# ── Leader key ────────────────────────────────────────────────────────────────
# Prefix for multi-key bindings.  Change once here; all layers follow.
LEADER_KEY = ","

# ── Layer enable / disable ────────────────────────────────────────────────────
# False = skip layer entirely.  Useful for debugging.
LAYERS: dict[str, bool] = {
    "base":        True,
    "privacy":     True,
    "appearance":  True,
    "behavior":    True,
    "performance": True,
    "user":        True,
}

# ── Host policy registry ──────────────────────────────────────────────────────
# Controls which built-in host exception categories are loaded.
# These apply *in addition to* BehaviorLayer.host_policies().
HOST_POLICY_LOGIN:  bool = True   # Google, GitHub, GitLab login cookies
HOST_POLICY_SOCIAL: bool = True   # Discord, Notion, Bilibili
HOST_POLICY_MEDIA:  bool = True   # YouTube, Twitch (no-autoplay)


# ╔══════════════════════════════════════════════════════════════════════════╗
# ║                   USER PREFERENCE SECTION                                ║
# ║                                                                          ║
# ║  Fine-grained personal settings injected into UserLayer (priority=90).   ║
# ║  You do NOT need to edit layers/user.py.                                 ║
# ╚══════════════════════════════════════════════════════════════════════════╝

# ── Editor ────────────────────────────────────────────────────────────────────
# Command for :open-editor / <ctrl-e> in insert mode.
# "{}" is replaced with the temp file path.
USER_EDITOR: list[str] | None = ["kitty", "-e", "nvim", "{}"]

# ── Start pages ───────────────────────────────────────────────────────────────
USER_START_PAGES: list[str] | None = ["https://www.bilibili.com"]

# ── Default zoom ──────────────────────────────────────────────────────────────
# e.g. "100%", "110%", "125%".  None = keep BaseLayer default.
USER_ZOOM: str | None = None

# ── Spellcheck languages ──────────────────────────────────────────────────────
# e.g. ["en-US"], ["en-US", "zh-CN"].  None = keep base default.
USER_SPELLCHECK: list[str] | None = None

# ── Search engine overrides ───────────────────────────────────────────────────
# Merged on top of the base layer's engine dict (UserLayer wins at priority=90).
# None = keep base engines unchanged.
#
# Example — add Jira:
#   USER_SEARCH_ENGINES = {
#       "jira": "https://jira.mycompany.com/issues/?jql=text+~+{}",
#   }
USER_SEARCH_ENGINES: dict[str, str] | None = None

# ── Extra settings (escape hatch) ─────────────────────────────────────────────
# Any qutebrowser setting not covered by the named layers.
USER_EXTRA_SETTINGS: dict[str, Any] = {
    # Example:
    # "tabs.position": "left",
    # "statusbar.show": "in-mode",
}

# ── Extra keybindings (escape hatch) ──────────────────────────────────────────
# List of (key, command, mode) tuples.  UserLayer priority=90 wins over all.
L = LEADER_KEY
USER_EXTRA_BINDINGS: list[tuple[str, str, str]] = [
    # ── Open with external app (auto-detect) ──────────────────────────────
    (f"{L}o",   "spawn --userscript open_with.py",                     "normal"),
    (f"{L}m",   "spawn --userscript open_with.py --app mpv",           "normal"),
    (";m",      "hint links spawn --userscript open_with.py --app mpv","normal"),

    # ── Search selection ──────────────────────────────────────────────────
    (f"{L}/",   "spawn --userscript search_sel.py --tab",              "normal"),
    (f"{L}sg",  "spawn --userscript search_sel.py --engine g --tab",   "normal"),
    (f"{L}sw",  "spawn --userscript search_sel.py --engine w --tab",   "normal"),

    # ── Reader mode ───────────────────────────────────────────────────────
    (f"{L}R",   "spawn --userscript readability.py",                   "normal"),

    # ── Clipboard URL ─────────────────────────────────────────────────────
    ("gx",      "open -t -- {clipboard}",                              "normal"),

    # ── Copy as Markdown link ─────────────────────────────────────────────
    (f"{L}lm",  "yank inline [{title}]({url})",                        "normal"),

    # ── Session management (uncomment + customise) ────────────────────────
    # (f"{L}Ss", "spawn --userscript tab_restore.py --save work",       "normal"),
    # (f"{L}Sr", "spawn --userscript tab_restore.py --restore work",    "normal"),
    # (f"{L}Sl", "spawn --userscript tab_restore.py --list",            "normal"),

    # ── Pass password manager (uncomment to enable) ───────────────────────
    # (f"{L}p",  "spawn --userscript password.py",                      "normal"),
    # (f"{L}P",  "spawn --userscript password.py --otp",                "normal"),
]

# ── Extra aliases (escape hatch) ──────────────────────────────────────────────
USER_EXTRA_ALIASES: dict[str, str] = {
    "rl":    "config-source",
    "clean": "download-clear",
}


# ╔══════════════════════════════════════════════════════════════════════════╗
# ║                         WIRING SECTION                                   ║
# ║                                                                          ║
# ║  Composition root — do not edit unless extending architecture.           ║
# ╚══════════════════════════════════════════════════════════════════════════╝

def _build_orchestrator() -> ConfigOrchestrator:
    """Build and wire the full orchestrator.  Pure Python, no side effects."""

    # ── Infrastructure ────────────────────────────────────────────────
    router    = MessageRouter()
    lifecycle = LifecycleManager()
    fsm       = ConfigStateMachine()

    # ── Host Policy Registry ──────────────────────────────────────────
    host_registry = None
    if _HOST_REGISTRY_AVAILABLE:
        host_registry = _build_host_registry(
            include_login  = HOST_POLICY_LOGIN,
            include_social = HOST_POLICY_SOCIAL,
            include_media  = HOST_POLICY_MEDIA,
        )

    # ── Layer Stack ───────────────────────────────────────────────────
    stack = LayerStack()

    if LAYERS.get("base"):
        stack.register(BaseLayer())

    if LAYERS.get("privacy"):
        stack.register(PrivacyLayer(profile=PRIVACY_PROFILE, leader=LEADER_KEY))

    if LAYERS.get("appearance"):
        stack.register(AppearanceLayer(theme=THEME))

    if LAYERS.get("behavior"):
        stack.register(BehaviorLayer(leader=LEADER_KEY))

    if LAYERS.get("performance"):
        stack.register(PerformanceLayer(profile=PERFORMANCE_PROFILE))

    if LAYERS.get("user"):
        stack.register(UserLayer(
            leader           = LEADER_KEY,
            editor           = USER_EDITOR,
            start_pages      = USER_START_PAGES,
            zoom             = USER_ZOOM,
            search_engines   = USER_SEARCH_ENGINES,
            spellcheck_langs = USER_SPELLCHECK,
            extra_settings   = USER_EXTRA_SETTINGS or {},
            extra_bindings   = USER_EXTRA_BINDINGS or [],
            extra_aliases    = USER_EXTRA_ALIASES  or {},
        ))

    # ── Lifecycle hooks ───────────────────────────────────────────────
    @lifecycle.decorator(LifecycleHook.POST_APPLY, priority=100)
    def _log_apply_done() -> None:
        logger.info("✓ qutebrowser config applied successfully")

    @lifecycle.decorator(LifecycleHook.ON_ERROR, priority=10)
    def _log_error() -> None:
        logger.error("✗ config apply encountered errors — check :messages")

    _ = _log_apply_done, _log_error   # suppress Pyright reportUnusedFunction

    # ── Event observers ───────────────────────────────────────────────
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
        stack         = stack,
        router        = router,
        lifecycle     = lifecycle,
        fsm           = fsm,
        host_registry = host_registry,
    )


# ╔══════════════════════════════════════════════════════════════════════════╗
# ║                        EXECUTION SECTION                                 ║
# ║                                                                          ║
# ║  Runs when qutebrowser loads config.py.                                  ║
# ║  `config` and `c` are injected by qutebrowser into this namespace.       ║
# ╚══════════════════════════════════════════════════════════════════════════╝

def _apply(config: Any, c: Any) -> None:
    try:
        orchestrator = _build_orchestrator()

        # Phase 1: Build — resolve all layers into merged config
        orchestrator.build()
        logger.info("[config.py]\n%s", orchestrator.summary())

        # Phase 2: Apply — write resolved config to qutebrowser API
        applier = ConfigApplier(config, c)
        errors  = orchestrator.apply(applier)

        # Phase 3: Per-host policy overrides (pattern-scoped config.set)
        host_errors = orchestrator.apply_host_policies(applier)
        errors.extend(host_errors)

        if errors:
            logger.warning(
                "[config.py] %d error(s) during apply — see messages above",
                len(errors),
            )
        else:
            logger.info("[config.py] ✓ all layers applied cleanly")

    except Exception as exc:
        logger.exception("[config.py] FATAL: config apply failed: %s", exc)
        # Do NOT re-raise — qutebrowser should still start with whatever
        # partial config was applied before the failure.


try:
    config.load_autoconfig(False)  # type: ignore[name-defined]
    _apply(config, c)              # type: ignore[name-defined]
except NameError:
    logger.info("[config.py] running outside qutebrowser — skipping _apply()")


