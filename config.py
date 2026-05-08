"""
config.py
=========
qutebrowser Configuration Entry Point  (v18)

This is the ONLY file qutebrowser loads directly.
It wires the architecture and delegates all real work to ConfigOrchestrator.

╔══════════════════════════════════════════════════════════════════════════╗
║  EDIT THE CONFIGURATION SECTION BELOW — that is the only section         ║
║  you need to touch.  All other sections are architecture.                ║
╚══════════════════════════════════════════════════════════════════════════╝

Compatible: qutebrowser ≥ 3.0  ·  PyQt6  ·  Python ≥ 3.11

Architecture wiring order:
  1. LayerStack assembled (priority-sorted)
  2. NetworkLayer     priority=27   declarative proxy/DNS/TLS     [v14]
  3. ContextLayer     priority=45   situational context           [v9]
  4. SessionLayer     priority=55   time-aware session            [v11]
  5. UserLayer        priority=90   personal overrides            [v9]
  6. Orchestrator.build()  → resolves layers, runs pipeline
  7. Orchestrator.apply()  → writes to qutebrowser config API
  8. apply_host_policies() → pattern-scoped config.set()

Keybinding Namespace (hard ownership — see KEYBINDINGS.md):
  PrivacyLayer[20]  → ,j ,i ,c ,s
  NetworkLayer[27]  → ,N*
  BehaviorLayer[40] → all other ,* (,b ,d ,D ,e ,k ,K ,n ,o ,O ,p ,pp ,po
                       ,q ,Q ,r ,R ,t ,T ,w ,W ,y ,Y ,/ ,? ,h ,l)
  ContextLayer[45]  → ,C*
  SessionLayer[55]  → ,S*
  UserLayer[90]     → extra_bindings (,/ ,xg ,xw ,xd ,R ,pp ,po ,ci)

v19 changes:
  [FIX] USER_EXTRA_BINDINGS: removed ,sg/,sw/,sd (violated PrivacyLayer's ,s*
        terminal ownership — caused 3 s delay before ,s HTTPS reload fired).
        Renamed to ,xg/,xw/,xd (,x* = search-eXternal, owned by UserLayer[90]).
  [FIX] behavior.py: enter-mode → mode-enter (correct qutebrowser command;
        was causing "enter-mode: no such command" ERROR on every key press).
  [FIX] base.py: removed hints.find_implementation (not available on
        QtWebEngine; was causing ERROR on every config reload).

v18 changes (retained):
  ContextSwitchedEvent source field; GetActiveContextQuery.

v15 changes (retained):
  SessionChangedEvent subscriber; GetActiveSessionQuery.

v14 changes (retained):
  NetworkLayer (p=27); USER_DARK_MODE/PDF_VIEWER/NEW_TAB_PAGE/TAB_BAR_PADDING;
  _on_network_changed/_on_hot_swap_completed subscribers.

v12 changes (retained):
  QutebrowserApplier concrete class bridging orchestrator to qutebrowser API.

v11 changes (retained):
  SessionLayer (priority=55) integrated.
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
    ContextSwitchedEvent,
    Event,
    HealthReportReadyEvent,
    HotSwapCompletedEvent,
    LayerAppliedEvent,
    MessageRouter,
    MetricsEvent,
    NetworkModeChangedEvent,
    PolicyDeniedEvent,
    SessionChangedEvent,
    SnapshotTakenEvent,
    ThemeChangedEvent,
)
from core.state    import ConfigStateMachine
from core.types    import Keybind
from orchestrator  import ConfigApplier, ConfigOrchestrator
from core.strategy import PolicyAction

# ── Layer imports ─────────────────────────────────────────────────────────────
from layers.appearance  import AppearanceLayer
from layers.base        import BaseLayer
from layers.behavior    import BehaviorLayer
from layers.context     import ContextLayer
from layers.network     import NetworkLayer
from layers.performance import PerformanceLayer, PerformanceProfile
from layers.privacy     import PrivacyLayer, PrivacyProfile
from layers.session     import SessionLayer
from layers.user        import UserLayer

# ── Policy / host registry ────────────────────────────────────────────────────
from policies.host import HostPolicyRegistry, build_default_host_registry  # type: ignore[import]

# ── Theme registration ────────────────────────────────────────────────────────
from themes.extended import register_all_themes
register_all_themes()

# ── Path setup ────────────────────────────────────────────────────────────────
_config_dir = os.path.dirname(os.path.abspath(__file__))
if _config_dir not in sys.path:
    sys.path.insert(0, _config_dir)

# ── Logging ───────────────────────────────────────────────────────────────────
# Default: WARNING (quiet startup).
# Set DEBUG_BINDINGS=True in CONFIGURATION SECTION for INFO/DEBUG verbosity.
logging.basicConfig(level=logging.WARNING)
logger = logging.getLogger("qute.config")

# ── Global orchestrator (accessible from :py in qutebrowser) ─────────────────
_orchestrator: Optional[ConfigOrchestrator] = None


# ╔══════════════════════════════════════════════════════════════════════════╗
# ║                       CONFIGURATION SECTION                              ║
# ║                                                                          ║
# ║  THIS IS THE ONLY SECTION YOU SHOULD EDIT.                               ║
# ╚══════════════════════════════════════════════════════════════════════════╝

# ── Theme ─────────────────────────────────────────────────────────────────────
# Built-in (5):   catppuccin-mocha | catppuccin-latte | gruvbox-dark
#                 tokyo-night | rose-pine
# Extended (14+): nord | dracula | solarized-dark | solarized-light | one-dark
#                 everforest-dark | kanagawa | palenight | catppuccin-frappe
#                 glass  (frosted-glass / cold-blue; modern & minimal)
# Custom:         add to themes/extended.py, reference by name here
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
PERFORMANCE_PROFILE = PerformanceProfile.LAPTOP

# ── Leader key ────────────────────────────────────────────────────────────────
# Prefix for all multi-key leader bindings.
# Change once here — all layers propagate it automatically.
LEADER_KEY = ","

# ── Active Context ────────────────────────────────────────────────────────────
# Situational browser mode: context-specific search engines, keybindings,
# and behavioral overrides.
#
# Resolution order (highest wins):
#   1. ACTIVE_CONTEXT (this variable)
#   2. QUTE_CONTEXT environment variable
#   3. ~/.config/qutebrowser/.context file (written by ,C* bindings)
#   4. "default" fallback
#
# Valid: None | "default" | "work" | "research" | "media" | "dev"
#        "writing" | "gaming"
#
# Runtime switch:
#   ,Cd=dev  ,Cw=work  ,Cwt=writing  ,Cr=research
#   ,Cm=media  ,Cg=gaming  ,C0=reset  ,Ci=show
ACTIVE_CONTEXT: Optional[str] = None

# ── Active Session [v11] ──────────────────────────────────────────────────────
# Time/situation-aware configuration mode.
#
# Resolution order (highest wins):
#   1. ACTIVE_SESSION (this variable)
#   2. QUTE_SESSION environment variable
#   3. ~/.config/qutebrowser/.session file
#   4. auto-detect from local time
#
# Valid: None | "auto" | "day" | "evening" | "night"
#        "focus" | "commute" | "present"
#
# Runtime switch (SessionLayer owns ,S* — BehaviorLayer has NO ,S* bindings):
#   ,Sd=day  ,Se=evening  ,Sn=night  ,Sf=focus
#   ,Sc=commute  ,Sp=present  ,S0=auto  ,Si=show current
ACTIVE_SESSION: Optional[str] = None   # None = auto-detect from time

# ── Active Network Mode [v14] ─────────────────────────────────────────────────
# Declarative proxy/DNS/TLS mode.
#
# Resolution order (highest wins):
#   1. NETWORK_MODE (this variable)
#   2. QUTE_NETWORK environment variable
#   3. ~/.config/qutebrowser/.network file (written by ,N* bindings)
#   4. "system" fallback
#
# Valid: None | "system" | "direct" | "socks5" | "http" | "tor" | "offline"
#
# Runtime switch (NetworkLayer owns ,N*):
#   ,Nn=direct  ,Ns=system  ,N5=socks5  ,Nh=http  ,Nt=tor  ,Ni=show
#
# Note: USER_PROXY (below) overrides NETWORK_MODE (UserLayer p=90 wins).
#       Set USER_PROXY=None to let NETWORK_MODE control proxy.
NETWORK_MODE: Optional[str] = None   # None = "system" default

# ── Layer enable / disable ────────────────────────────────────────────────────
# False = skip layer entirely (useful for debugging or minimal profiles).
LAYERS: dict[str, bool] = {
    "base":        True,
    "privacy":     True,
    "network":     True,    # v14: declarative network/proxy layer (priority=27)
    "appearance":  True,
    "behavior":    True,
    "context":     True,
    "performance": True,
    "session":     True,    # v11: time-aware session layer (priority=55)
    "user":        True,
}

# ── Host policy registry ──────────────────────────────────────────────────────
HOST_POLICY_LOGIN:  bool = True   # Google, GitHub, GitLab login cookies
HOST_POLICY_SOCIAL: bool = True   # Discord, Notion, Bilibili
HOST_POLICY_MEDIA:  bool = True   # YouTube, Twitch (no-autoplay)
HOST_POLICY_DEV:    bool = True   # localhost, 127.0.0.1, [::1], *.local


# ╔══════════════════════════════════════════════════════════════════════════╗
# ║                     USER PREFERENCE SECTION                              ║
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
USER_FONT_FAMILY:   str | None = None   # e.g. "JetBrainsMono Nerd Font"
USER_FONT_SIZE:     str | None = None   # e.g. "10pt", "12pt"
USER_FONT_SIZE_WEB: str | None = None   # e.g. "16px", "18px", or "16"

# ── Spellcheck languages ──────────────────────────────────────────────────────
USER_SPELLCHECK: list[str] | None = None

# ── GitHub username ───────────────────────────────────────────────────────────
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
# NOTE: USER_PROXY overrides NETWORK_MODE (UserLayer p=90 > NetworkLayer p=27).
#       Set USER_PROXY=None to let NETWORK_MODE control the proxy.
USER_PROXY: str | None = "socks5://127.0.0.1:7897"

# ── Message timeout ───────────────────────────────────────────────────────────
# Milliseconds to display status-bar notifications (0 = until dismissed).
USER_MESSAGES_TIMEOUT: int | None = 3000

# ── Dark mode [v14] ───────────────────────────────────────────────────────────
# None          → no forced inversion (keep AppearanceLayer default)
# "off"         → disable dark mode explicitly
# "simple"      → InvertBrightness (most compatible)
# "mediumLight" → InvertLightness  (recommended with dark themes)
# "aggressive"  → InvertLightness on ALL pages
USER_DARK_MODE: str | None = None

# ── PDF viewer [v14] ──────────────────────────────────────────────────────────
# True  → built-in PDF.js viewer
# False → download PDFs to disk
# None  → keep BaseLayer default (True)
USER_PDF_VIEWER: bool | None = None

# ── New tab page [v14] ────────────────────────────────────────────────────────
# URL opened for :open -t.  None → USER_START_PAGES[0] or "about:blank".
USER_NEW_TAB_PAGE: str | None = None

# ── Tab bar padding [v14] ─────────────────────────────────────────────────────
# {"top": N, "bottom": N, "left": N, "right": N}  or  None.
USER_TAB_BAR_PADDING: dict[str, int] | None = None

# ── Extra settings (escape hatch) ─────────────────────────────────────────────
# Applied at priority=90 (UserLayer), after all other layers.
USER_EXTRA_SETTINGS: dict[str, Any] | None = None

# ── Extra keybindings ─────────────────────────────────────────────────────────
# Applied at priority=90 — always wins over any lower-priority layer.
#
# NAMESPACE RULES (v19):
#   - Do NOT define ,s* (PrivacyLayer terminal: ,s)   ← was violated by ,sg/,sw/,sd
#   - Do NOT define ,S* (SessionLayer terminal group)
#   - Do NOT define ,N* (NetworkLayer terminal group)
#   - Do NOT define ,C* (ContextLayer terminal group)
#   - ,pp/,po override BehaviorLayer's qute-pass defaults (intentional)
#   - ,/ overrides BehaviorLayer's cmd-set-text / (intentional: search_sel)
#   - ,x* = search-eXternal shortcuts (UserLayer[90] exclusive, no conflicts)
#
# v18 FIX — removed problematic bindings from v17:
#   REMOVED: ,p  (bare) → was blocking ,pp/,po via 3s prefix wait
#   REMOVED: ,P  (OTP)  → capital-P shift-modifier conflict with native P
#   REMOVED: ,px ,p0 ,ps (proxy shortcuts sharing ,p prefix — caused 3s delay
#            on ALL ,p* bindings).  Use ,N* NetworkLayer bindings instead:
#            ,Nn=direct  ,Ns=system  ,N5=socks5  ,Nh=http  ,Nt=tor
#
L = LEADER_KEY
USER_EXTRA_BINDINGS: list[tuple[str, str, str]] | None = [

    # ── Search selection shortcuts ─────────────────────────────────────────
    # NAMESPACE: ,x* (search-eXternal)
    # Previously ,sg/,sw/,sd — REMOVED: violated PrivacyLayer's ,s* ownership.
    # ,s is a TERMINAL in PrivacyLayer[20]; sub-sequences ,sg/,sw/,sd caused
    # qutebrowser to wait partial_timeout (3 s) before firing ,s, making the
    # HTTPS reload feel broken.  Moved to ,x* prefix (unowned, safe).
    #
    # ,/  overrides BehaviorLayer's ,/ = cmd-set-text / (UserLayer[90] wins)
    # ,xg = search selected text via Google
    # ,xw = search selected text via Wikipedia
    # ,xd = search selected text via DuckDuckGo
    (f"{L}/",   "spawn --userscript search_sel.py --tab",             "normal"),
    (f"{L}xg",  "spawn --userscript search_sel.py --engine g --tab",  "normal"),
    (f"{L}xw",  "spawn --userscript search_sel.py --engine w --tab",  "normal"),
    (f"{L}xd",  "spawn --userscript search_sel.py --engine ddg --tab","normal"),

    # ── Readability ───────────────────────────────────────────────────────
    # Overrides BehaviorLayer's ,R = spawn --userscript readability
    # UserLayer[90] wins with the .py extension version.
    (f"{L}R",   "spawn --userscript readability.py",                  "normal"),

    # ── Password manager ──────────────────────────────────────────────────
    # NAMESPACE: ,pp / ,po  (sub-sequences of ,p — safe within merged table)
    #
    # These override BehaviorLayer[40]'s ,pp/,po (qute-pass defaults).
    # UserLayer[90] wins — uses password.py custom userscript.
    # To revert to qute-pass, remove these two entries.
    #
    # Longest-match behaviour (all three in merged table):
    #   ,p  alone → open -p (private window)    [after 3 s partial_timeout]
    #   ,pp       → spawn password.py           [fires on 2nd 'p']
    #   ,po       → spawn password.py --otp     [fires on 'o']
    # This is safe: all three share prefix within the same flat key table,
    # so qutebrowser's partial_timeout correctly disambiguates them.
    (f"{L}pp",  "spawn --userscript password.py ;; message-info 'Password fill…'",   "normal"),
    (f"{L}po",  "spawn --userscript password.py --otp ;; message-info 'OTP fill…'",  "normal"),

    # ── Context: show current context ─────────────────────────────────────
    (f"{L}ci",  "spawn --userscript context_switch.py --show",        "normal"),

    # ── Proxy quick-switch ────────────────────────────────────────────────
    # Proxy shortcuts are now under ,N* (NetworkLayer owns ,N* prefix).
    # Use these bindings from NetworkLayer:
    #   ,Nn = direct (no proxy)
    #   ,Ns = system proxy
    #   ,N5 = SOCKS5 (127.0.0.1:7897)
    #   ,Nh = HTTP   (127.0.0.1:7890)
    #   ,Nt = Tor    (127.0.0.1:9050)
    #   ,Ni = show current network mode
    # Old ,px/,p0/,ps shortcuts REMOVED (were sharing ,p prefix, causing
    # 3-second delay on ALL ,p* sequences including password fill).

]

# ── Debug / verbosity ─────────────────────────────────────────────────────────
# Set True to enable INFO+DEBUG console logging during config load and
# keybinding application.  Useful for diagnosing binding conflicts.
#
# When True:
#   - Every layer's settings and keybindings are logged at INFO level
#   - Policy decisions (DENY/MODIFY/WARN) are logged at DEBUG level
#   - Metrics and snapshots visible in qutebrowser :messages
#
# Note: qutebrowser's :messages always shows recent entries regardless of
# this flag.  This flag controls Python logger verbosity only.
DEBUG_BINDINGS: bool = True

# ── Extra aliases ─────────────────────────────────────────────────────────────
USER_EXTRA_ALIASES: dict[str, str] = {
    # ── Common shorthands ─────────────────────────────────────────────────
    "rl":       "config-source",
    "clean":    "download-clear",
    "his":      "history",
    "bm":       "bookmark-list",
    "qm":       "quickmark-list",

    # ── Namespace cheatsheets (type :session, :network, :bindings in cmdbar)
    "snap":     "message-info 'Use :config-source or ,r to reload config'",
    "session":  (
        "message-info "
        "'Session: ,Sd=day ,Se=evening ,Sn=night ,Sf=focus "
        ",Sc=commute ,Sp=present ,S0=auto ,Si=show'"
    ),
    "network":  (
        "message-info "
        "'Network: ,Nn=direct ,Ns=system ,N5=socks5 ,Nh=http ,Nt=tor ,Ni=show'"
    ),
    "bindings": (
        "message-info "
        "'Namespaces: ,j/i/c/s=privacy ,C*=context ,S*=session "
        ",N*=network  ,p=private ,pp=pass ,po=otp'"
    ),
}


# ╔══════════════════════════════════════════════════════════════════════════╗
# ║               CONCRETE APPLIER  (v12, v15 polish)                        ║
# ║                                                                          ║
# ║  QutebrowserApplier bridges the orchestrator to qutebrowser's            ║
# ║  runtime `config` / `c` objects.  Lives here (not orchestrator.py)       ║
# ║  so orchestrator.py stays import-clean (no qutebrowser internals).       ║
# ╚══════════════════════════════════════════════════════════════════════════╝

class QutebrowserApplier(ConfigApplier):
    """
    Concrete ConfigApplier that writes to qutebrowser's live config API.

    Parameters
    ----------
    config : Any
        The ``config`` object injected by qutebrowser (ConfigAPI).
        Used for config.set() and config.bind().
    c : Any
        The ``c`` object injected by qutebrowser (ConfigContainer).
        Held for future extension.
    """

    def __init__(self, config: Any, c: Any) -> None:
        self._config = config
        self._c      = c

    def apply_settings(
        self,
        settings:     Dict[str, Any],
        policy_chain: Optional[Any] = None,
        router:       Optional[Any] = None,
    ) -> List[str]:
        """
        Write every key/value pair to qutebrowser via config.set().

        If policy_chain is provided, each key is evaluated:
          DENY   → skip key; emit PolicyDeniedEvent via router
          MODIFY → apply modified value instead
          WARN   → log warning; still apply original value
        """
        errors: List[str] = []
        for key, value in settings.items():
            if policy_chain is not None:
                try:
                    decision = policy_chain.evaluate(key, value, {})
                    if decision.action == PolicyAction.DENY:
                        logger.debug("[Applier] DENY  key=%s  reason=%s", key, decision.reason)
                        if router is not None:
                            try:
                                from core.protocol import PolicyDeniedEvent
                                router.emit(PolicyDeniedEvent(
                                    key=key, reason=decision.reason or "policy denied",
                                ))
                            except Exception:
                                pass
                        continue
                    elif decision.action == PolicyAction.MODIFY:
                        logger.debug("[Applier] MODIFY key=%s  reason=%s", key, decision.reason)
                        value = decision.modified_value
                    elif decision.action == PolicyAction.WARN:
                        logger.warning("[Applier] WARN  key=%s  reason=%s", key, decision.reason)
                except Exception as exc:
                    logger.debug("[Applier] policy_chain.evaluate() error: %s", exc)

            try:
                self._config.set(key, value)
            except Exception as exc:
                msg = f"settings[{key!r}]={value!r}: {exc}"
                logger.warning("[Applier] %s", msg)
                errors.append(msg)
        return errors

    def apply_keybindings(self, keybindings: List[Keybind]) -> List[str]:
        """Bind keys via config.bind()."""
        errors: List[str] = []
        for entry in keybindings:
            try:
                key, command, mode = entry
                self._config.bind(key, command, mode=mode)
                if DEBUG_BINDINGS:
                    logger.debug("[Applier] bind %-20s → %s  [%s]", key, command, mode)
            except (TypeError, ValueError) as exc:
                msg = f"bind({entry!r}): bad format — {exc}"
                logger.warning("[Applier] %s", msg)
                errors.append(msg)
            except Exception as exc:
                msg = f"bind({entry!r}): {exc}"
                logger.warning("[Applier] %s", msg)
                errors.append(msg)
        return errors

    def apply_aliases(self, aliases: Dict[str, str]) -> List[str]:
        """
        Register command aliases via config.set('aliases', ...).
        Merges with existing aliases (incremental — layers contribute freely).
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

    def apply_host_policy(self, pattern: str, settings: Dict[str, Any]) -> List[str]:
        """Apply pattern-scoped settings via config.set(key, value, pattern=...)."""
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
# ║  Composition root — do not edit unless extending the architecture.       ║
# ╚══════════════════════════════════════════════════════════════════════════╝

def _build_orchestrator() -> ConfigOrchestrator:
    """Build and wire the full orchestrator.  Pure Python, no side effects."""

    router    = MessageRouter()
    lifecycle = LifecycleManager()
    fsm       = ConfigStateMachine()

    host_registry = build_default_host_registry(
        include_login  = HOST_POLICY_LOGIN,
        include_social = HOST_POLICY_SOCIAL,
        include_media  = HOST_POLICY_MEDIA,
        include_dev    = HOST_POLICY_DEV,
    )

    # ── Layer Stack (priority-ordered) ────────────────────────────────────
    stack = LayerStack()

    if LAYERS.get("base"):
        stack.register(BaseLayer())

    if LAYERS.get("privacy"):
        stack.register(PrivacyLayer(profile=PRIVACY_PROFILE, leader=LEADER_KEY))

    # NetworkLayer p=27 — between privacy[20] and appearance[30]
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

    # SessionLayer p=55 — time/situation-aware; owns ,S* prefix
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
            dark_mode            = USER_DARK_MODE,
            pdf_viewer           = USER_PDF_VIEWER,
            new_tab_page         = USER_NEW_TAB_PAGE,
            tab_bar_padding      = USER_TAB_BAR_PADDING,
            extra_settings       = extra,
            extra_bindings       = USER_EXTRA_BINDINGS or [],
            extra_aliases        = USER_EXTRA_ALIASES  or {},
            github_username      = USER_GITHUB,
        ))

    # ── Lifecycle hooks ───────────────────────────────────────────────────

    @lifecycle.decorator(LifecycleHook.POST_APPLY, priority=100)
    def _log_apply_done() -> None:
        logger.info("✓ qutebrowser config applied successfully (v18)")

    @lifecycle.decorator(LifecycleHook.ON_ERROR, priority=10)
    def _log_error() -> None:
        logger.error("✗ config apply encountered errors — check :messages")

    @lifecycle.decorator(LifecycleHook.POST_RELOAD, priority=100)
    def _log_reload_done() -> None:
        logger.info("↺ qutebrowser config hot-reloaded (v18)")

    _ = _log_apply_done, _log_error, _log_reload_done

    # ── Event observers ───────────────────────────────────────────────────

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

    def _on_network_changed(e: Event) -> None:
        if isinstance(e, NetworkModeChangedEvent):
            logger.info(
                "[Network] mode=%s  proxy=%s  source=%s",
                e.new_mode, e.proxy, e.source,
            )

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

    def _on_session_changed(e: Event) -> None:
        if isinstance(e, SessionChangedEvent):
            logger.info("[Session] mode=%s  source=%s", e.new_session, e.source)

    def _on_context_switched(e: Event) -> None:
        if isinstance(e, ContextSwitchedEvent):
            logger.info("[Context] context=%s  source=%s", e.new_context, e.source)

    # ── Subscribe all observers ───────────────────────────────────────────
    router.events.subscribe(LayerAppliedEvent,       _on_layer_applied)
    router.events.subscribe(ConfigErrorEvent,        _on_config_error)
    router.events.subscribe(ThemeChangedEvent,       _on_theme_changed)
    router.events.subscribe(HealthReportReadyEvent,  _on_health_ready)
    router.events.subscribe(ConfigReloadedEvent,     _on_config_reloaded)
    router.events.subscribe(SnapshotTakenEvent,      _on_snapshot_taken)
    router.events.subscribe(PolicyDeniedEvent,       _on_policy_denied)
    router.events.subscribe(MetricsEvent,            _on_metrics)
    router.events.subscribe(NetworkModeChangedEvent, _on_network_changed)
    router.events.subscribe(HotSwapCompletedEvent,   _on_hot_swap_completed)
    router.events.subscribe(SessionChangedEvent,     _on_session_changed)
    router.events.subscribe(ContextSwitchedEvent,    _on_context_switched)

    return ConfigOrchestrator(
        stack         = stack,
        router        = router,
        lifecycle     = lifecycle,
        fsm           = fsm,
        host_registry = host_registry,
    )


# ╔══════════════════════════════════════════════════════════════════════════╗
# ║                         EXECUTION SECTION                                ║
# ║                                                                          ║
# ║  Runs when qutebrowser loads config.py.                                  ║
# ║  `config` and `c` are injected by qutebrowser into this namespace.       ║
# ╚══════════════════════════════════════════════════════════════════════════╝

def _apply(config: Any, c: Any) -> None:
    global _orchestrator
    try:
        # ── Debug verbosity (controlled by DEBUG_BINDINGS flag above) ──────
        if DEBUG_BINDINGS:
            logging.getLogger().setLevel(logging.DEBUG)
            logging.getLogger("qute").setLevel(logging.DEBUG)
            logging.getLogger("qute.config").setLevel(logging.DEBUG)
            logger.info("[config.py] DEBUG_BINDINGS=True — verbose logging active")

        orchestrator = _build_orchestrator()

        # Phase 1: Build — resolve all layers into merged config
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

        # Audit trail
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
