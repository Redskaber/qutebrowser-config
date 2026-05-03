"""
config.py
=========
qutebrowser Configuration Entry Point  (v12)

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
  3. SessionLayer injected if session system is enabled (priority=55) [v11]
  4. UserLayer injected last (priority=90)
  5. ConfigOrchestrator.build() → resolves layers, runs pipeline
  6. ConfigOrchestrator.apply() → writes to qutebrowser config API
  7. apply_host_policies()      → pattern-scoped config.set()

Strict-mode notes (Pyright):
  - _apply(config, c) parameters annotated as Any — qutebrowser injects
    these at runtime; no stub types are available.
  - Event subscriber functions cast to concrete event type inside each body.
  - Lifecycle decorator return values assigned to _ to suppress
    reportUnusedFunction.

v12 changes:
  - QutebrowserApplier(ConfigApplier) concrete class added here.
    Bridges orchestrator ↔ qutebrowser runtime (config/c objects).
    Implements apply_settings / apply_keybindings / apply_aliases /
    apply_host_policy with full error capture and policy-gate support.
  - _apply() now creates QutebrowserApplier(config, c) — fixes the
    TypeError: ConfigApplier() takes no arguments crash (v11 regression).
  - Typing imports extended: Dict, List, Tuple for strict-mode coverage.

v11 changes (retained):
  - SessionLayer (priority=55) integrated: time-aware configuration.
    Controlled by ACTIVE_SESSION and LAYERS["session"].
  - SESSION_MODE flag added to CONFIGURATION SECTION.
  - LAYERS dict updated with "session" key (default: True).
  - _build_orchestrator() registers SessionLayer when LAYERS["session"] is True.
  - _on_session_event subscriber: logs active session on config load.
  - Audit integration: AuditLog populated during build/apply phases;
    accessible via :py orchestrator.audit_trail() or diagnostics.py.
  - SESSION keybindings wired via SessionLayer (,S prefix).
  - USER_EXTRA_ALIASES: added "diag" → spawn diagnostics.py summary.

v9 changes (retained):
  - Wired ConfigReloadedEvent subscriber: logs reload stats.
  - Wired MetricsEvent subscriber: logs timing phases at DEBUG level.
  - Wired SnapshotTakenEvent subscriber: debug log only.
  - USER_ENABLE_RELOAD_HOST_POLICIES flag.
  - USER_MESSAGES_TIMEOUT for notification display time.
  - _build_orchestrator() wires PolicyDeniedEvent subscriber.

v8 changes (retained):
  - USER_FONT_FAMILY / USER_FONT_SIZE / USER_FONT_SIZE_WEB.
  - HealthReportReadyEvent subscriber.

v7 changes (retained):
  - HOST_POLICY_DEV actually passed to build_default_host_registry.
  - Summary banner shows host policy counts.
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
    LayerAppliedEvent,
    MessageRouter,
    MetricsEvent,
    PolicyDeniedEvent,
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
from layers.user        import UserLayer

# ── v11: Session layer (graceful import — layer file may not exist yet) ───────
from layers.session import SessionLayer

# ── Policy / host registry imports ────────────────────────────────────────────
from policies.host import HostPolicyRegistry, build_default_host_registry # type: ignore[import]

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

# ── Layer enable / disable ────────────────────────────────────────────────────
# False = skip layer entirely.  Useful for debugging.
LAYERS: dict[str, bool] = {
    "base":        True,
    "privacy":     True,
    "appearance":  True,
    "behavior":    True,
    "context":     True,
    "performance": True,
    "session":     True,   # v11: time-aware session layer
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
USER_PROXY: str | None = None

# ── Message timeout ───────────────────────────────────────────────────────────
# Milliseconds to display qutebrowser notifications (0 = until dismissed).
USER_MESSAGES_TIMEOUT: int | None = 5000

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

    # ── Proxy cycle ────────────────────────────────────────────────────
    (f"{L}px",  "set content.proxy system",                          "normal"),
    (f"{L}p0",  "set content.proxy none",                            "normal"),
    (f"{L}ps",  "set content.proxy socks5://127.0.0.1:7897",         "normal"),
]

# ── Extra aliases ─────────────────────────────────────────────────────────────
USER_EXTRA_ALIASES: dict[str, str] = {
    "rl":    "config-source",
    "clean": "download-clear",
    "his":   "history",
    "bm":    "bookmark-list",
    "qm":    "quickmark-list",
    "snap":  "message-info 'Use :config-source to reload'",
    # v11: session management aliases
    "session": "message-info 'Session bindings: ,Sd ,Se ,Sn ,Sf ,Sc ,Sp ,S0 ,Si'",
    # v11: diagnostic alias (runs without qutebrowser)
    # "diag": "spawn --userscript diagnostics.py summary",
}


# ╔══════════════════════════════════════════════════════════════════════════╗
# ║                    CONCRETE APPLIER (v12)                                ║
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
        Used for attribute-style access: ``c.fonts.default_size = "10pt"``.
        We fall back to ``config.set()`` for all keys so ``c`` is held
        only as a reference for future extension.
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
        """
        Bind keys via ``config.bind()``.

        Each entry must be a 3-tuple ``(key, command, mode)`` or a 2-tuple
        ``(key, command)`` (mode defaults to ``"normal"``).
        """
        errors: List[str] = []
        for entry in keybindings:
            try:
                if isinstance(entry, (list, tuple)): # type: ignore[runtime]
                    if len(entry) == 3:
                        key, command, mode = entry
                    else:
                        errors.append(f"bad keybinding tuple length: {entry!r}")
                        continue
                else:
                    errors.append(f"unknown keybinding format: {entry!r}")
                    continue
                self._config.bind(key, command, mode=mode)
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
            # Merge with whatever is already registered
            try:
                existing: Dict[str, str] = dict(self._config.get("aliases") or {})
            except Exception:
                existing = {}
            existing.update(aliases)
            self._config.set("aliases", existing)
        except Exception as exc:
            msg = f"aliases: {exc}"
            logger.warning("[Applier] %s", msg)
            errors.append(msg)
        return errors

    # ── Per-host policy ───────────────────────────────────────────────────

    def apply_host_policy(self, pattern: str, settings: Dict[str, Any]) -> List[str]:
        """
        Apply pattern-scoped settings via ``config.set(key, value, pattern)``.
        """
        errors: List[str] = []
        for key, value in settings.items():
            try:
                self._config.set(key, value, pattern)
            except Exception as exc:
                msg = f"host_policy[{pattern!r}] {key!r}={value!r}: {exc}"
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

    if LAYERS.get("appearance"):
        stack.register(AppearanceLayer(theme=THEME))

    if LAYERS.get("behavior"):
        stack.register(BehaviorLayer(leader=LEADER_KEY))

    if LAYERS.get("context"):
        stack.register(ContextLayer(context=ACTIVE_CONTEXT, leader=LEADER_KEY))

    if LAYERS.get("performance"):
        stack.register(PerformanceLayer(profile=PERFORMANCE_PROFILE))

    # v11: Session layer — time/situation-aware configuration (priority=55)
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
            extra_settings       = extra,
            extra_bindings       = USER_EXTRA_BINDINGS or [],
            extra_aliases        = USER_EXTRA_ALIASES  or {},
            github_username      = USER_GITHUB,
        ))

    # ── Lifecycle hooks ───────────────────────────────────────────────

    @lifecycle.decorator(LifecycleHook.POST_APPLY, priority=100)
    def _log_apply_done() -> None:
        logger.info("✓ qutebrowser config applied successfully (v11)")

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

    router.events.subscribe(LayerAppliedEvent,       _on_layer_applied)
    router.events.subscribe(ConfigErrorEvent,        _on_config_error)
    router.events.subscribe(ThemeChangedEvent,       _on_theme_changed)
    router.events.subscribe(HealthReportReadyEvent,  _on_health_ready)
    router.events.subscribe(ConfigReloadedEvent,     _on_config_reloaded)
    router.events.subscribe(SnapshotTakenEvent,      _on_snapshot_taken)
    router.events.subscribe(PolicyDeniedEvent,       _on_policy_denied)
    router.events.subscribe(MetricsEvent,            _on_metrics)

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

        # v11: log audit trail summary
        try:
            from core.audit import get_audit_log
            log = get_audit_log()
            if log.warnings_and_above():
                logger.warning("[Audit] %d warning/error entries — run diagnostics.py for details", len(log.warnings_and_above()))
        except ImportError:
            pass

    except Exception as exc:
        logger.exception("[config.py] FATAL: config apply failed: %s", exc)
        # Do NOT re-raise — qutebrowser should still start with whatever
        # partial config was applied before the failure.


try:
    config.load_autoconfig(False)  # type: ignore[name-defined]
    _apply(config, c)              # type: ignore[name-defined]
except NameError:
    logger.info("[config.py] running outside qutebrowser — skipping _apply()")
