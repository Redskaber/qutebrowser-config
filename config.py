"""
config.py
=========
qutebrowser Configuration Entry Point  (v15)

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
  2. NetworkLayer injected if network system is enabled (priority=27)  [v14]
  3. ContextLayer injected if context system is enabled (priority=45)
  4. SessionLayer injected if session system is enabled (priority=55)  [v11]
  5. UserLayer injected last (priority=90)
  6. ConfigOrchestrator.build() → resolves layers, runs pipeline
       → emits ContextSwitchedEvent
       → emits SessionChangedEvent  [v15]
       → emits NetworkModeChangedEvent  [v14/v15]
  7. ConfigOrchestrator.apply() → writes to qutebrowser config API
  8. apply_host_policies()      → pattern-scoped config.set()

Strict-mode notes (Pyright):
  - _apply(config, c) parameters annotated as Any — qutebrowser injects
    these at runtime; no stub types are available.
  - Event subscriber functions cast to concrete event type inside each body.
  - Lifecycle decorator return values assigned to _ to suppress
    reportUnusedFunction.
  - _orchestrator global declared in module scope (type: ignore) so :py
    console sessions can access orchestrator.hot_swap without re-building.

v15 changes:
  - SessionChangedEvent subscriber added: _on_session_changed().
    Logs active session mode/description on startup and hot-swap.
  - SessionChangedEvent imported from core.protocol (new in v15).
  - GetActiveSessionQuery accessible via router.ask().
  - All v14 changes retained (NetworkLayer, UserLayer v14 params, etc).
  - apply_keybindings simplified: tuple unpacking inline (was try/isinstance).
  - _log_apply_done lifecycle hook: message updated to v15.
  - HotSwapCompletedEvent handler: uses len() correctly on lists.

v14 changes (retained):
  - NetworkLayer (priority=27): declarative proxy/DNS/TLS.
    NETWORK_MODE variable in CONFIGURATION SECTION.
  - USER_DARK_MODE, USER_PDF_VIEWER, USER_NEW_TAB_PAGE, USER_TAB_BAR_PADDING.
  - _on_network_changed / _on_hot_swap_completed subscribers.
  - _orchestrator global for :py hot-swap access.

v12 changes (retained):
  - QutebrowserApplier(ConfigApplier) concrete class (bridges qutebrowser API).

v11 changes (retained):
  - SessionLayer (priority=55) integrated.

v9 changes (retained):
  - ConfigReloadedEvent / MetricsEvent / SnapshotTakenEvent subscribers.
"""

from __future__ import annotations

import logging
import os
import sys
from typing import Any, Dict, List, Optional

# ── Architecture ──────────────────────────────────────────────────────────────
from core.layer     import LayerStack
from core.lifecycle import LifecycleHook, LifecycleManager
from core.protocol  import (
    ConfigErrorEvent,
    ConfigReloadedEvent,
    Event,
    HealthReportReadyEvent,
    HotSwapCompletedEvent,
    LayerAppliedEvent,
    MessageRouter,
    MetricsEvent,
    NetworkModeChangedEvent,
    PolicyDeniedEvent,
    SessionChangedEvent,           # v15: first-class session event
    SnapshotTakenEvent,
    ThemeChangedEvent,
)
from core.state     import ConfigStateMachine
from core.types     import Keybind
from orchestrator   import ConfigApplier, ConfigOrchestrator

# ── Layer imports ─────────────────────────────────────────────────────────────
from layers.appearance  import AppearanceLayer
from layers.base        import BaseLayer
from layers.behavior    import BehaviorLayer
from layers.context     import ContextLayer
from layers.performance import PerformanceLayer, PerformanceProfile
from layers.privacy     import PrivacyLayer, PrivacyProfile
from layers.network     import NetworkLayer # v14
from layers.session     import SessionLayer
from layers.user        import UserLayer


# ── Policy / host registry imports ────────────────────────────────────────────
from policies.host import HostPolicyRegistry, build_default_host_registry  # type: ignore[import]

# ── Theme registration ─────────────────────────────────────────────────────────
from themes.extended import register_all_themes
register_all_themes()

# ── Path setup (ensure config dir is importable) ──────────────────────────────
_config_dir = os.path.dirname(os.path.abspath(__file__))
if _config_dir not in sys.path:
    sys.path.insert(0, _config_dir)

# ── Logging ───────────────────────────────────────────────────────────────────
logging.basicConfig(level=logging.WARNING)
logger = logging.getLogger("qute.config")

# ── Global orchestrator reference (accessible from :py in qutebrowser) ────────
_orchestrator: Optional[ConfigOrchestrator] = None


# ╔══════════════════════════════════════════════════════════════════════════╗
# ║                     CONFIGURATION SECTION                                ║
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

# ── Active Session  [v11] ─────────────────────────────────────────────────────
# Time/situation-aware configuration mode.
#
# Resolution order (highest wins):
#   1. This variable (ACTIVE_SESSION)
#   2. QUTE_SESSION environment variable
#   3. ~/.config/qutebrowser/.session file (written by ,S* keybindings)
#   4. auto-detect from local time (day/evening/night)
#
# Valid values:
#   None | "auto"    → derive from local time (recommended)
#   "day"            → 08:00–18:00 standard working (full performance)
#   "evening"        → 18:00–22:00 wind-down (larger font, +5% zoom)
#   "night"          → 22:00–06:00 low-light (larger font, minimal chrome)
#   "focus"          → deep-work: hide chrome, no notifications
#   "commute"        → bandwidth-constrained: no images, no autoplay
#   "present"        → screen-share / demo: large text, 125% zoom
#
# Switch at runtime:  ,Sd (day)  ,Se (evening)  ,Sn (night)
#                     ,Sf (focus)  ,Sc (commute)  ,Sp (present)
#                     ,S0 (auto)  ,Si (show current)
ACTIVE_SESSION: Optional[str] = None   # None = auto-detect from time

# ── Active Network Mode  [v14] ────────────────────────────────────────────────
# Declarative proxy/DNS/TLS configuration mode.
#
# Resolution order (highest wins):
#   1. This variable (NETWORK_MODE)
#   2. QUTE_NETWORK environment variable
#   3. ~/.config/qutebrowser/.network file (written by ,N* keybindings)
#   4. "system" fallback
#
# Valid values:
#   None | "system"  → OS-level proxy (qutebrowser default)
#   "direct"         → no proxy; connect directly
#   "socks5"         → SOCKS5 via 127.0.0.1:7897 (Clash/Verge mixed port)
#   "http"           → HTTP proxy via 127.0.0.1:7890
#   "tor"            → Tor SOCKS5 via 127.0.0.1:9050; max privacy
#   "offline"        → local-only; no DNS prefetch; testing/presentations
#
# Switch at runtime:  ,Nn (direct)  ,Ns (system)  ,N5 (socks5)
#                     ,Nh (http)    ,Nt (tor)      ,Ni (show current)
#
# Note: NETWORK_MODE sets the *default* at startup.
#       USER_PROXY (p=90 UserLayer) always overrides NETWORK_MODE.
#       To use Clash: NETWORK_MODE = "socks5"  +  USER_PROXY = None.
NETWORK_MODE: Optional[str] = None   # None = "system" (default)

# ── Layer enable / disable ────────────────────────────────────────────────────
# False = skip layer entirely.  Useful for debugging or minimal profiles.
LAYERS: dict[str, bool] = {
    "base":        True,
    "privacy":     True,
    "network":     True,   # v14: declarative network/proxy layer (priority=27)
    "appearance":  True,
    "behavior":    True,
    "context":     True,
    "performance": True,
    "session":     True,   # v11: time-aware session layer (priority=55)
    "user":        True,
}

# ── Host policy registry ──────────────────────────────────────────────────────
# Controls which built-in host exception categories are loaded.
# These apply *in addition to* BehaviorLayer.host_policies().
HOST_POLICY_LOGIN:  bool = True   # Google, GitHub, GitLab login cookies
HOST_POLICY_SOCIAL: bool = True   # Discord, Notion, Bilibili
HOST_POLICY_MEDIA:  bool = True   # YouTube, Twitch (no-autoplay)
HOST_POLICY_DEV:    bool = True   # localhost, 127.0.0.1, [::1], *.local (JS+cookies)


# ╔══════════════════════════════════════════════════════════════════════════╗
# ║                   USER PREFERENCE SECTION                                ║
# ║                                                                          ║
# ║  Fine-grained personal settings injected into UserLayer (priority=90).   ║
# ║  You do NOT need to edit layers/user.py.                                 ║
# ╚══════════════════════════════════════════════════════════════════════════╝

# ── Editor ────────────────────────────────────────────────────────────────────
USER_EDITOR: list[str] | None = ["kitty", "-e", "nvim", "{}"]

# ── Start pages ───────────────────────────────────────────────────────────────
USER_START_PAGES: list[str] | None = ["https://www.bilibili.com"]

# ── Default zoom ──────────────────────────────────────────────────────────────
# e.g. "100%", "110%", "125%".  None = keep BaseLayer/SessionLayer default.
USER_ZOOM: str | None = None

# ── Font overrides ────────────────────────────────────────────────────────────
# USER_FONT_FAMILY:   font family name (e.g. "JetBrainsMono Nerd Font", "Iosevka")
# USER_FONT_SIZE:     UI chrome font size string (e.g. "10pt", "12pt")
#                     → maps to fonts.default_size (Qt string)
# USER_FONT_SIZE_WEB: web content default font size (e.g. "16px", "18px", or "16")
#                     → maps to fonts.web.size.default (int)
#                     NOTE: SessionLayer also sets fonts.web.size.default for
#                     evening/night/present modes; UserLayer (p=90) always wins.
USER_FONT_FAMILY:   str | None = None
USER_FONT_SIZE:     str | None = None
USER_FONT_SIZE_WEB: str | None = None

# ── Spellcheck languages ──────────────────────────────────────────────────────
USER_SPELLCHECK: list[str] | None = None

# ── GitHub username ────────────────────────────────────────────────────────────
USER_GITHUB: str = "redskaber"

# ── Search engine overrides ───────────────────────────────────────────────────
USER_SEARCH_ENGINES: dict[str, str] | None = {
    "gpt":      "https://chatgpt.com/?{}",
    "claude":   "https://claude.ai/new/?{}",
    "deepseek": "https://chat.deepseek.com/?{}",
    "bing":     "https://bing.com/?{}",
}
USER_SEARCH_ENGINES_MERGE: bool = True

# ── Proxy ─────────────────────────────────────────────────────────────────────
# Valid: "system" | "none" | "socks5://host:port" | "http://host:port"
# Example (Clash-Verge mixed port): "http://127.0.0.1:7897"
# Note: USER_PROXY overrides NETWORK_MODE (UserLayer p=90 > NetworkLayer p=27).
#       Set USER_PROXY=None to let NETWORK_MODE control the proxy.
USER_PROXY: str | None = None

# ── Message timeout ───────────────────────────────────────────────────────────
# Milliseconds to display qutebrowser notifications (0 = until dismissed).
USER_MESSAGES_TIMEOUT: int | None = 5000

# ── Dark mode  [v14] ──────────────────────────────────────────────────────────
# Web content dark mode rendering algorithm.
#
# Valid values:
#   None          → keep AppearanceLayer default (no forced inversion)
#   "off"         → disable dark mode (explicit off)
#   "simple"      → InvertBrightness (most compatible, may wash colors)
#   "mediumLight" → InvertLightness  (smoother; recommended for most themes)
#   "aggressive"  → InvertLightness on ALL pages regardless of their scheme
#
# Tip: use "mediumLight" with dark themes (glass, catppuccin-mocha) for the
# best experience on sites that don't have their own dark mode.
USER_DARK_MODE: str | None = None   # None = no forced inversion

# ── PDF viewer  [v14] ─────────────────────────────────────────────────────────
# True  → use built-in PDF.js viewer (content.pdfjs = True)
# False → download PDFs to disk
# None  → keep BaseLayer default (True / PDF.js enabled)
USER_PDF_VIEWER: bool | None = None

# ── New tab page  [v14] ───────────────────────────────────────────────────────
# URL opened for new blank tabs (:open -t / Ctrl+T).
# Separate from USER_START_PAGES (which controls the startup page).
# None → use USER_START_PAGES[0] if set, else "about:blank".
# Example: "https://start.duckduckgo.com"
USER_NEW_TAB_PAGE: str | None = None

# ── Tab bar padding  [v14] ────────────────────────────────────────────────────
# Pixel padding inside each tab cell.  Dict with keys "top", "bottom",
# "left", "right" (all int).  Partial dicts OK — unset keys keep defaults.
# None → keep AppearanceLayer/theme default.
# Example: {"top": 0, "bottom": 0, "left": 5, "right": 5}
USER_TAB_BAR_PADDING: dict[str, int] | None = None

# ── Extra settings (escape hatch) ─────────────────────────────────────────────
# Applied at priority=90 (UserLayer), after all other layers.
USER_EXTRA_SETTINGS: dict[str, Any] | None = None

# ── Extra keybindings ─────────────────────────────────────────────────────────
L = LEADER_KEY
USER_EXTRA_BINDINGS: list[tuple[str, str, str]] | None = [
    # ── Search selection shortcuts ─────────────────────────────────────
    (f"{L}/",   "spawn --userscript search_sel.py --tab",            "normal"),
    (f"{L}sg",  "spawn --userscript search_sel.py --engine g --tab", "normal"),
    (f"{L}sw",  "spawn --userscript search_sel.py --engine w --tab", "normal"),
    (f"{L}sd",  "spawn --userscript search_sel.py --engine ddg --tab","normal"),

    # ── Readability ────────────────────────────────────────────────────
    (f"{L}R",   "spawn --userscript readability.py",                 "normal"),

    # ── Password manager ───────────────────────────────────────────────
    (f"{L}p",   "spawn --userscript password.py",                    "normal"),
    (f"{L}P",   "spawn --userscript password.py --otp",              "normal"),

    # ── Context: display current context ──────────────────────────────
    (f"{L}ci",  "spawn --userscript context_switch.py --show",       "normal"),

    # ── Proxy cycle (legacy — superseded by ,N* from NetworkLayer) ────
    # These remain for muscle-memory compatibility; ,N* is preferred.
    (f"{L}px",  "set content.proxy system",                          "normal"),
    (f"{L}p0",  "set content.proxy none",                            "normal"),
    (f"{L}ps",  "set content.proxy socks5://127.0.0.1:7897",         "normal"),
]

# ── Extra aliases ─────────────────────────────────────────────────────────────
USER_EXTRA_ALIASES: dict[str, str] = {
    "rl":      "config-source",
    "clean":   "download-clear",
    "his":     "history",
    "bm":      "bookmark-list",
    "qm":      "quickmark-list",
    "snap":    "message-info 'Use :config-source to reload'",
    # v11: session management
    "session": "message-info 'Session bindings: ,Sd ,Se ,Sn ,Sf ,Sc ,Sp ,S0 ,Si'",
    # v14: network management
    "network": "message-info 'Network bindings: ,Nn ,Ns ,N5 ,Nh ,Nt ,Ni'",
}


# ╔══════════════════════════════════════════════════════════════════════════╗
# ║                    CONCRETE APPLIER (v12, v15 polish)                    ║
# ║                                                                          ║
# ║  QutebrowserApplier bridges the orchestrator to qutebrowser's            ║
# ║  runtime `config` / `c` objects.  It lives here (not in orchestrator.py) ║
# ║  so that orchestrator.py stays import-clean (no qutebrowser internals).  ║
# ╚══════════════════════════════════════════════════════════════════════════╝

class QutebrowserApplier(ConfigApplier):
    """
    Concrete ConfigApplier that writes to qutebrowser's live config API.

    Parameters
    ----------
    config : Any
        The ``config`` object injected by qutebrowser (ConfigAPI).
        Used for ``config.set(key, value, pattern)`` and
        ``config.bind(key, command, mode)``.
    c : Any
        The ``c`` object injected by qutebrowser (ConfigContainer).
        Held for future extension; all keys written via config.set().
    """

    def __init__(self, config: Any, c: Any) -> None:
        self._config = config
        self._c      = c

    # ── Settings ──────────────────────────────────────────────────────────

    def apply_settings(
        self,
        settings:     Dict[str, Any],
        policy_chain: Optional[Any] = None,
        router:       Optional[Any] = None,
    ) -> List[str]:
        """
        Write every key/value pair to qutebrowser via ``config.set()``.

        If a *policy_chain* is provided, each key is evaluated before writing:
        a PolicyDeniedEvent is emitted (via router) and the key skipped when
        the chain rejects it.
        """
        errors: List[str] = []
        for key, value in settings.items():
            # Policy gate (optional)
            if policy_chain is not None:
                try:
                    allowed, reason = policy_chain.evaluate(key, value)
                    if not allowed:
                        logger.debug("[Applier] DENY  key=%s  reason=%s", key, reason)
                        if router is not None:
                            try:
                                from core.protocol import PolicyDeniedEvent
                                router.emit(PolicyDeniedEvent(
                                    key=key, reason=reason or "policy denied",
                                ))
                            except Exception:
                                pass
                        continue
                except Exception as exc:
                    logger.debug("[Applier] policy_chain.evaluate() error: %s", exc)

            # Write to qutebrowser
            try:
                self._config.set(key, value)
            except Exception as exc:
                msg = f"settings[{key!r}]={value!r}: {exc}"
                logger.warning("[Applier] %s", msg)
                errors.append(msg)
        return errors

    # ── Keybindings ───────────────────────────────────────────────────────

    def apply_keybindings(self, keybindings: List[Keybind]) -> List[str]:
        """Bind keys via ``config.bind()``."""
        errors: List[str] = []
        for entry in keybindings:
            try:
                key, command, mode = entry   # type: ignore[misc]
                self._config.bind(key, command, mode=mode)
            except (TypeError, ValueError) as exc:
                msg = f"bind({entry!r}): bad format — {exc}"
                logger.warning("[Applier] %s", msg)
                errors.append(msg)
            except Exception as exc:
                msg = f"bind({entry!r}): {exc}"
                logger.warning("[Applier] %s", msg)
                errors.append(msg)
        return errors

    # ── Aliases ───────────────────────────────────────────────────────────

    def apply_aliases(self, aliases: Dict[str, str]) -> List[str]:
        """
        Register command aliases via ``config.set('aliases', ...)``.

        Merges with existing aliases so that layers can contribute
        incrementally without clobbering each other.
        """
        errors: List[str] = []
        if not aliases:
            return errors
        try:
            existing: Dict[str, str] = {}
            try:
                existing = dict(self._config.get("aliases") or {})
            except Exception:
                pass
            self._config.set("aliases", {**existing, **aliases})
        except Exception as exc:
            msg = f"aliases: {exc}"
            logger.warning("[Applier] %s", msg)
            errors.append(msg)
        return errors

    # ── Per-host policy ───────────────────────────────────────────────────

    def apply_host_policy(self, pattern: str, settings: Dict[str, Any]) -> List[str]:
        """Apply pattern-scoped settings via ``config.set(key, value, pattern=...)``."""
        errors: List[str] = []
        for key, value in settings.items():
            try:
                self._config.set(key, value, pattern=pattern)
            except Exception as exc:
                msg = f"host[{pattern!r}] {key!r}={value!r}: {exc}"
                logger.warning("[Applier] %s", msg)
                errors.append(msg)
        return errors


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
    host_registry = build_default_host_registry(
        include_login  = HOST_POLICY_LOGIN,
        include_social = HOST_POLICY_SOCIAL,
        include_media  = HOST_POLICY_MEDIA,
        include_dev    = HOST_POLICY_DEV,
    )

    # ── Layer Stack ───────────────────────────────────────────────────
    stack = LayerStack()

    if LAYERS.get("base"):
        stack.register(BaseLayer())

    if LAYERS.get("privacy"):
        stack.register(PrivacyLayer(profile=PRIVACY_PROFILE, leader=LEADER_KEY))

    # v14: NetworkLayer (p=27) — between privacy[20] and appearance[30]
    if LAYERS.get("network"):
        stack.register(NetworkLayer(mode=NETWORK_MODE, leader=LEADER_KEY))

    if LAYERS.get("appearance"):
        stack.register(AppearanceLayer(theme=THEME))

    if LAYERS.get("behavior"):
        stack.register(BehaviorLayer(leader=LEADER_KEY))

    if LAYERS.get("context"):
        stack.register(ContextLayer(context=ACTIVE_CONTEXT, leader=LEADER_KEY))

    if LAYERS.get("performance"):
        stack.register(PerformanceLayer(profile=PERFORMANCE_PROFILE))

    # v11: SessionLayer — time/situation-aware configuration (priority=55)
    if LAYERS.get("session"):
        stack.register(SessionLayer(session=ACTIVE_SESSION, leader=LEADER_KEY))

    if LAYERS.get("user"):
        extra = dict(USER_EXTRA_SETTINGS or {})
        if USER_MESSAGES_TIMEOUT is not None:
            extra.setdefault("messages.timeout", USER_MESSAGES_TIMEOUT)

        stack.register(UserLayer(
            leader               = LEADER_KEY,
            editor               = USER_EDITOR,
            start_pages          = USER_START_PAGES,
            zoom                 = USER_ZOOM,
            proxy                = USER_PROXY,
            search_engines       = USER_SEARCH_ENGINES,
            search_engines_merge = USER_SEARCH_ENGINES_MERGE,
            spellcheck_langs     = USER_SPELLCHECK,
            font_family          = USER_FONT_FAMILY,
            font_size            = USER_FONT_SIZE,
            font_size_web        = USER_FONT_SIZE_WEB,
            dark_mode            = USER_DARK_MODE,        # v14
            pdf_viewer           = USER_PDF_VIEWER,       # v14
            new_tab_page         = USER_NEW_TAB_PAGE,     # v14
            tab_bar_padding      = USER_TAB_BAR_PADDING,  # v14
            extra_settings       = extra,
            extra_bindings       = USER_EXTRA_BINDINGS or [],
            extra_aliases        = USER_EXTRA_ALIASES  or {},
            github_username      = USER_GITHUB,
        ))

    # ── Lifecycle hooks ───────────────────────────────────────────────

    @lifecycle.decorator(LifecycleHook.POST_APPLY, priority=100)
    def _log_apply_done() -> None:
        logger.info("✓ qutebrowser config applied successfully (v15)")

    @lifecycle.decorator(LifecycleHook.ON_ERROR, priority=10)
    def _log_error() -> None:
        logger.error("✗ config apply encountered errors — check :messages")

    @lifecycle.decorator(LifecycleHook.POST_RELOAD, priority=100)
    def _log_reload_done() -> None:
        logger.info("↺ qutebrowser config hot-reloaded")

    _ = _log_apply_done, _log_error, _log_reload_done

    # ── Event observers ───────────────────────────────────────────────

    def _on_layer_applied(e: Event) -> None:
        if isinstance(e, LayerAppliedEvent):
            logger.info(
                "layer applied: %-12s (%d settings)",
                e.layer_name, e.key_count,
            )

    def _on_config_error(e: Event) -> None:
        if isinstance(e, ConfigErrorEvent):
            logger.error("config error [%s]: %s", e.layer_name or "?", e.error_msg)

    def _on_theme_changed(e: Event) -> None:
        if isinstance(e, ThemeChangedEvent):
            logger.info("theme changed: %s", e.theme_name)

    def _on_health_ready(e: Event) -> None:
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

    def _on_config_reloaded(e: Event) -> None:
        if isinstance(e, ConfigReloadedEvent):
            if e.error_count:
                logger.warning(
                    "[Reload] ↺ done: %d change(s), %d error(s), %.1fms",
                    e.change_count, e.error_count, e.duration_ms,
                )
            else:
                logger.info(
                    "[Reload] ↺ done: %d change(s), %.1fms",
                    e.change_count, e.duration_ms,
                )

    def _on_snapshot_taken(e: Event) -> None:
        if isinstance(e, SnapshotTakenEvent):
            logger.debug(
                "[Snapshot] recorded: label=%r  keys=%d  version=%d",
                e.label, e.key_count, e.version,
            )

    def _on_policy_denied(e: Event) -> None:
        if isinstance(e, PolicyDeniedEvent):
            logger.warning(
                "[Policy] DENY  key=%s  reason=%s  layer=%s",
                e.key, e.reason, e.layer_name or "?",
            )

    def _on_metrics(e: Event) -> None:
        if isinstance(e, MetricsEvent):
            logger.debug(
                "[Metrics] phase=%-16s  %.1fms  keys=%d",
                e.phase, e.duration_ms, e.key_count,
            )

    # v14: network mode changed
    def _on_network_changed(e: Event) -> None:
        if isinstance(e, NetworkModeChangedEvent):
            logger.info(
                "[Network] mode=%s  proxy=%s  source=%s",
                e.new_mode, e.proxy, e.source,
            )

    # v14: hot-swap completed
    def _on_hot_swap_completed(e: Event) -> None:
        if isinstance(e, HotSwapCompletedEvent):
            if e.ok:
                logger.info(
                    "[HotSwap] %s(%s)  changes=%d  OK  %.1fms",
                    e.operation, e.layer_name, len(e.changes), e.duration_ms,
                )
            else:
                logger.warning(
                    "[HotSwap] %s(%s)  changes=%d  errors=%d  %.1fms",
                    e.operation, e.layer_name,
                    len(e.changes), len(e.errors), e.duration_ms,
                )

    # v15: session changed — mirrors _on_network_changed for session system
    def _on_session_changed(e: Event) -> None:
        if isinstance(e, SessionChangedEvent):
            logger.info(
                "[Session] mode=%s  source=%s",
                e.new_session, e.source,
            )

    # ── Subscribe all observers ────────────────────────────────────────
    router.events.subscribe(LayerAppliedEvent,       _on_layer_applied)
    router.events.subscribe(ConfigErrorEvent,        _on_config_error)
    router.events.subscribe(ThemeChangedEvent,       _on_theme_changed)
    router.events.subscribe(HealthReportReadyEvent,  _on_health_ready)
    router.events.subscribe(ConfigReloadedEvent,     _on_config_reloaded)
    router.events.subscribe(SnapshotTakenEvent,      _on_snapshot_taken)
    router.events.subscribe(PolicyDeniedEvent,       _on_policy_denied)
    router.events.subscribe(MetricsEvent,            _on_metrics)
    router.events.subscribe(NetworkModeChangedEvent, _on_network_changed)    # v14
    router.events.subscribe(HotSwapCompletedEvent,   _on_hot_swap_completed) # v14
    router.events.subscribe(SessionChangedEvent,     _on_session_changed)    # v15

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
    global _orchestrator
    try:
        orchestrator = _build_orchestrator()

        # Phase 1: Build — resolve all layers into merged config
        #   → emits ContextSwitchedEvent, SessionChangedEvent, NetworkModeChangedEvent
        orchestrator.build()
        logger.info("[config.py]\n%s", orchestrator.summary())

        # Phase 2: Apply — write resolved config to qutebrowser API
        applier = QutebrowserApplier(config, c)
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

        # Audit trail summary
        try:
            from core.audit import get_audit_log
            log = get_audit_log()
            warn_entries = log.warnings_and_above()
            if warn_entries:
                logger.warning(
                    "[Audit] %d warning/error entries — run diagnostics.py for details",
                    len(warn_entries),
                )
        except ImportError:
            pass

        # Store orchestrator globally for :py console access and hot-swap
        _orchestrator = orchestrator

    except Exception as exc:
        logger.exception("[config.py] FATAL: config apply failed: %s", exc)
        # Do NOT re-raise — qutebrowser should still start with whatever
        # partial config was applied before the failure.


try:
    config.load_autoconfig(False)  # type: ignore[name-defined]
    _apply(config, c)              # type: ignore[name-defined]
except NameError:
    logger.info("[config.py] running outside qutebrowser — skipping _apply()")
