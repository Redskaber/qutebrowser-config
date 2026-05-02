"""
config.py
=========
qutebrowser Configuration Entry Point  (v8)

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

Architecture wiring order:
  1. LayerStack built with enabled layers (priority-sorted)
  2. ContextLayer injected if context system is enabled (priority=45)
  3. UserLayer injected last (priority=90)
  4. ConfigOrchestrator.build() → resolves layers, runs pipeline
  5. ConfigOrchestrator.apply() → writes to qutebrowser config API
  6. apply_host_policies()      → pattern-scoped config.set()

Strict-mode notes (Pyright):
  - _apply(config, c) parameters annotated as Any — qutebrowser injects
    these at runtime; no stub types are available.
  - Event subscriber functions cast to concrete event type inside each body.
  - Lifecycle decorator return values assigned to _ to suppress
    reportUnusedFunction.

v8 changes:
  - Added USER_FONT_FAMILY / USER_FONT_SIZE / USER_FONT_SIZE_UI — first-class
    font override params (no longer need extra_settings escape hatch for fonts)
  - Wired HealthReportReadyEvent subscriber: logs full report on errors,
    brief summary on warnings/infos, silent on clean
  - Lifecycle hook banner updated to v8
  - UserLayer constructor call includes font_family/font_size/font_size_ui

v7 changes (retained):
  - HOST_POLICY_DEV is now actually passed to build_default_host_registry
    (was silently ignored — bug fix; the flag existed but had no effect)
  - build_default_host_registry called with include_dev=HOST_POLICY_DEV
  - Summary banner shows host policy counts

v6 changes (retained):
  - USER_PROXY type corrected to Optional[str]
  - Added USER_FONT_MONO / USER_FONT_SIZE_UI font override hints
  - Added ACTIVE_CONTEXT "writing" to the documented valid values
  - HOST_POLICY_DEV flag added
  - HealthChecker.default() now runs 15 checks (was 12)
  - Summary banner improved: shows active context + profile
"""

from __future__ import annotations

import logging
import os
import sys
from typing import Any, Optional

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
    HealthReportReadyEvent,
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

# ── Optional: ContextLayer (graceful fallback if context.py absent) ──────────
try:
    from layers.context import ContextLayer, ContextMode
    _CONTEXT_LAYER_AVAILABLE = True
except ImportError:
    _CONTEXT_LAYER_AVAILABLE = False

# ── Extended themes (optional; graceful fallback if themes/ absent) ───────────
try:
    from themes.extended import register_all_themes
    register_all_themes()
except ImportError:
    pass

# ── Host policy registry (optional; graceful fallback) ────────────────────────
try:
    from policies.host import HostPolicyRegistry, build_default_host_registry as _build_host_registry
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
# Extended (14+):
#   nord | dracula | solarized-dark | solarized-light | one-dark
#   everforest-dark | kanagawa | palenight | catppuccin-frappe
#   glass  ← modern · minimal · premium; frosted-glass / cold-blue aesthetic
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

# ── Active Context ────────────────────────────────────────────────────────────
# Situational browser mode.  Injects context-specific search engines,
# keybindings, and behavioral overrides.
#
# Resolution order (highest wins):
#   1. This variable (ACTIVE_CONTEXT)
#   2. QUTE_CONTEXT environment variable
#   3. ~/.config/qutebrowser/.context file (written by ,C* keybindings)
#   4. "default" fallback
#
# Valid values: None | "default" | "work" | "research" | "media" | "dev" | "writing" | "gaming"
#
# Switch at runtime:  ,Cw (work)  ,Cr (research)  ,Cm (media)  ,Cd (dev)
#                     ,Cwt (writing)  ,Cg (gaming)  ,C0 (reset)  ,Ci (show current)
ACTIVE_CONTEXT: Optional[str] = None

# ── Layer enable / disable ────────────────────────────────────────────────────
# False = skip layer entirely.  Useful for debugging.
LAYERS: dict[str, bool] = {
    "base":        True,
    "privacy":     True,
    "appearance":  True,
    "behavior":    True,
    "context":     True,   # situational context layer (priority=45)
    "performance": True,
    "user":        True,
}

# ── Host policy registry ──────────────────────────────────────────────────────
# Controls which built-in host exception categories are loaded.
# These apply *in addition to* BehaviorLayer.host_policies().
HOST_POLICY_LOGIN:  bool = True   # Google, GitHub, GitLab login cookies
HOST_POLICY_SOCIAL: bool = True   # Discord, Notion, Bilibili
HOST_POLICY_MEDIA:  bool = True   # YouTube, Twitch (no-autoplay)
HOST_POLICY_DEV:    bool = True   # localhost, 127.0.0.1, [::1], *.local (JS+cookies)
                                  # NOTE (v7 fix): this flag is now actually used!
                                  # Previously it was declared but never passed to
                                  # build_default_host_registry — see wiring below.


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

# ── Font overrides ─────────────────────────────────────────────────────────────
# Override the font set by AppearanceLayer/theme.
# USER_FONT_FAMILY:   font family name (e.g. "JetBrainsMono Nerd Font", "Iosevka")
# USER_FONT_SIZE:     UI chrome font size string (e.g. "10pt", "12pt")
#                     → maps to fonts.default_size (Qt string, affects qute chrome)
# USER_FONT_SIZE_WEB: web content default font size (e.g. "16px", "18px", "16")
#                     → maps to fonts.web.size.default (int, affects page text)
#                     Accepts "16px", "18px", or plain "16" — all parsed to int.
# None = keep AppearanceLayer / theme default.
USER_FONT_FAMILY:   str | None = None
USER_FONT_SIZE:     str | None = None
USER_FONT_SIZE_WEB: str | None = None

# ── Spellcheck languages ──────────────────────────────────────────────────────
# e.g. ["en-US"], ["en-US", "zh-CN"].  None = keep base default.
USER_SPELLCHECK: list[str] | None = None

# ── GitHub username (used in :gh alias) ───────────────────────────────────────
USER_GITHUB: str = "redskaber"

# ── Search engine overrides ───────────────────────────────────────────────────
# Merged ON TOP of the base layer's engine dict (UserLayer priority=90).
# Set USER_SEARCH_ENGINES_MERGE=True (default) for additive behavior.
# Set to False to REPLACE the entire engine map.
# None = keep base engines unchanged.
#
# Example — add Jira:
#   USER_SEARCH_ENGINES = {
#       "jira": "https://jira.mycompany.com/issues/?jql=text+~+{}",
#   }
USER_SEARCH_ENGINES: dict[str, str] | None = {
    "gpt":      "https://chatgpt.com/?{}",
    "claude":   "https://claude.ai/new/?{}",
    "deepseek": "https://chat.deepseek.com/?{}",
    "bing":     "https://bing.com/?{}",
}
USER_SEARCH_ENGINES_MERGE: bool = True

# ── Proxy ─────────────────────────────────────────────────────────────────────
# content.proxy accepts a SINGLE string (not a list).
#
# Valid values:
#   "system"                     → use the system proxy (default)
#   "none"                       → direct connection, bypass system proxy
#   "socks5://host:port"         → SOCKS5 proxy  (clash-verge / clash-meta)
#   "socks://host:port"          → SOCKS5 (alias)
#   "http://host:port"           → HTTP CONNECT proxy
#
# Clash-Verge / Clash-Meta mixed-port:
#   SOCKS5 → socks5://127.0.0.1:7897   (preferred; tunnels all TCP+UDP)
#   HTTP   → http://127.0.0.1:7897     (fallback for HTTP-only proxies)
#
# None = keep PrivacyLayer default ("system").
#
# Toggle keybinding: ,px (cycle modes), ,p0 (direct), ,ps (system)
#
USER_PROXY: Optional[str] = "socks5://127.0.0.1:7897"
# USER_PROXY: Optional[str] = "http://127.0.0.1:7897"   # HTTP port (alt)
# USER_PROXY: Optional[str] = "system"                   # use system proxy
# USER_PROXY: Optional[str] = "none"                     # direct, no proxy
# USER_PROXY: Optional[str] = None                       # keep PrivacyLayer default

# ── Extra settings (escape hatch) ─────────────────────────────────────────────
# Any qutebrowser setting not covered by the named layers.
# NOTE: content.proxy must NOT be set here as a list — use USER_PROXY above.
USER_EXTRA_SETTINGS: dict[str, Any] = {
    # Uncomment to override font (normally set by AppearanceLayer theme):
    # "fonts.default_family": "JetBrainsMono Nerd Font",
    # "fonts.default_size":   "10pt",
    #
    # Uncomment to move tabs to the left:
    # "tabs.position": "left",
    #
    # Uncomment to hide the status bar unless in a special mode:
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

    # ── Proxy toggle (clash-verge ↔ direct) ──────────────────────────────
    # ,px  → cycle: socks5 → http → system → none
    (f"{L}px",  "config-cycle content.proxy socks5://127.0.0.1:7897 http://127.0.0.1:7897 system none", "normal"),
    # ,p0  → direct connection (no proxy)
    (f"{L}p0",  "set content.proxy none",                              "normal"),
    # ,ps  → use system proxy settings
    (f"{L}ps",  "set content.proxy system",                            "normal"),

    # ── Clipboard URL ─────────────────────────────────────────────────────
    ("gx",      "open -t -- {clipboard}",                              "normal"),

    # ── Copy as Markdown link ─────────────────────────────────────────────
    (f"{L}lm",  "yank inline [{title}]({url})",                        "normal"),

    # ── Session management (uncomment + customise) ────────────────────────
    # (f"{L}Ss", "spawn --userscript tab_restore.py --save work",       "normal"),
    # (f"{L}Sr", "spawn --userscript tab_restore.py --restore work",    "normal"),
    # (f"{L}Sl", "spawn --userscript tab_restore.py --list",            "normal"),

    # ── Pass password manager (uncomment to enable) ───────────────────────
    # (f"{L}pp", "spawn --userscript password.py",                      "normal"),
    # (f"{L}pP", "spawn --userscript password.py --otp",                "normal"),
]

# ── Extra aliases (escape hatch) ──────────────────────────────────────────────
USER_EXTRA_ALIASES: dict[str, str] = {
    "rl":    "config-source",
    "clean": "download-clear",
    "his":   "history",
    "bm":    "bookmark-list",
    "qm":    "quickmark-list",
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
    # v7 fix: HOST_POLICY_DEV is now passed as include_dev= to the factory.
    # Previously the flag was declared in config.py but silently ignored
    # because _build_host_registry was called without it.
    host_registry: Optional[HostPolicyRegistry] = None  # type: ignore[name-defined]
    if _HOST_REGISTRY_AVAILABLE:
        host_registry = _build_host_registry(  # type: ignore[possibly-undefined]
            include_login  = HOST_POLICY_LOGIN,
            include_social = HOST_POLICY_SOCIAL,
            include_media  = HOST_POLICY_MEDIA,
            include_dev    = HOST_POLICY_DEV,   # ← v7 fix: was missing
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

    if LAYERS.get("context") and _CONTEXT_LAYER_AVAILABLE:
        stack.register(ContextLayer(
            context = ACTIVE_CONTEXT,
            leader  = LEADER_KEY,
        ))

    if LAYERS.get("performance"):
        stack.register(PerformanceLayer(profile=PERFORMANCE_PROFILE))

    if LAYERS.get("user"):
        stack.register(UserLayer(
            leader                = LEADER_KEY,
            editor                = USER_EDITOR,
            start_pages           = USER_START_PAGES,
            zoom                  = USER_ZOOM,
            proxy                 = USER_PROXY,
            search_engines        = USER_SEARCH_ENGINES,
            search_engines_merge  = USER_SEARCH_ENGINES_MERGE,
            spellcheck_langs      = USER_SPELLCHECK,
            font_family           = USER_FONT_FAMILY,
            font_size             = USER_FONT_SIZE,
            font_size_web         = USER_FONT_SIZE_WEB,
            extra_settings        = USER_EXTRA_SETTINGS or {},
            extra_bindings        = USER_EXTRA_BINDINGS or [],
            extra_aliases         = USER_EXTRA_ALIASES  or {},
            github_username       = USER_GITHUB,
        ))

    # ── Lifecycle hooks ───────────────────────────────────────────────
    @lifecycle.decorator(LifecycleHook.POST_APPLY, priority=100)
    def _log_apply_done() -> None:
        logger.info("✓ qutebrowser config applied successfully (v8)")

    @lifecycle.decorator(LifecycleHook.ON_ERROR, priority=10)
    def _log_error() -> None:
        logger.error("✗ config apply encountered errors — check :messages")

    _ = _log_apply_done, _log_error   # suppress Pyright reportUnusedFunction

    # ── Event observers ───────────────────────────────────────────────
    def _on_layer_applied(e: Event) -> None:
        if isinstance(e, LayerAppliedEvent):
            logger.info(
                "layer applied: %-12s (%d settings)",
                e.layer_name, e.key_count,
            )

    def _on_config_error(e: Event) -> None:
        if isinstance(e, ConfigErrorEvent):
            logger.error(
                "config error [%s]: %s",
                e.layer_name or "?", e.error_msg,
            )

    def _on_theme_changed(e: Event) -> None:
        if isinstance(e, ThemeChangedEvent):
            logger.info("theme changed: %s", e.theme_name)

    def _on_health_ready(e: Event) -> None:
        """Log a concise health summary; on errors print the full report."""
        if isinstance(e, HealthReportReadyEvent):
            if not e.ok:
                logger.warning(
                    "[Health] %d error(s)  %d warning(s)  %d info(s) — "
                    "run :messages for details",
                    e.error_count, e.warning_count, e.info_count,
                )
            elif e.warning_count or e.info_count:
                logger.info(
                    "[Health] ✓ (0 errors, %d warning(s), %d info(s))",
                    e.warning_count, e.info_count,
                )

    router.events.subscribe(LayerAppliedEvent,      _on_layer_applied)
    router.events.subscribe(ConfigErrorEvent,       _on_config_error)
    router.events.subscribe(ThemeChangedEvent,      _on_theme_changed)
    router.events.subscribe(HealthReportReadyEvent, _on_health_ready)

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
