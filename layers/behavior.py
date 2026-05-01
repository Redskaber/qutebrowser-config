"""
layers/behavior.py
==================
Behavior Layer — UX, Workflow, Interaction Patterns

Priority: 40

Responsibilities:
  - Page interaction behaviors
  - Content handling policies
  - Workflow keybindings (Vim-style navigation, leader key)
  - Userscript integration
  - Per-host policy overrides (non-dev categories only)

Pattern: Data-Driven Configuration + Command pattern for keybindings

v7 changes:
  - host_policies() no longer returns dev/localhost rules — these are
    now owned exclusively by policies/host.py DEV_RULES (controlled by
    HOST_POLICY_DEV in config.py).  Previously the same localhost/127.0.0.1
    rules were applied twice: once from BehaviorLayer and once from
    HostPolicyRegistry.ALWAYS_RULES.  Removing the duplication here is the
    canonical fix.
  - All other v6 additions retained (zoom bindings, ctrl-tab, gf/wf,
    tc, prompt ctrl-y, ,b, window management, etc.)

v6 changes (retained):
  - Added zoom keybindings: zi / zo / z0 / zz
  - Added <ctrl-tab> / <ctrl-shift-tab> tab cycling
  - Added gf / wf  (open frame in tab/window)
  - Added leader-based window management: ,n / ,N / ,w
  - Added ,h / ,l  — tab history prev/next for current tab
  - Added ,b  — show downloads
  - Added prompt mode bindings: <ctrl-y> accept, <ctrl-enter> accept
  - HostPolicy frozen-field typing for strict-mode
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Tuple

from core.layer import BaseConfigLayer

ConfigDict = Dict[str, Any]


# ─────────────────────────────────────────────
# Per-Host Policy (data-driven overrides)
# ─────────────────────────────────────────────
@dataclass(frozen=True)
class HostPolicy:
    """
    Declarative per-host configuration override.
    Applied via config.set(..., pattern=host_pattern).

    Frozen so instances can be used as dict keys or in sets.

    NOTE: dev/localhost rules are NOT emitted from BehaviorLayer.
    They are owned by policies/host.py DEV_RULES and controlled
    by HOST_POLICY_DEV in config.py.  This avoids double-application.
    """
    pattern:     str
    settings:    Dict[str, Any]   = field(default_factory=dict, compare=False)
    description: str              = ""
    category:    str              = "general"


# ─────────────────────────────────────────────
# Behavior Layer
# ─────────────────────────────────────────────
class BehaviorLayer(BaseConfigLayer):
    """
    UX behavior configuration.
    Focuses on how qutebrowser acts, not how it looks.
    """

    name = "behavior"
    priority = 40
    description = "UX behaviors, workflow bindings, per-host overrides"

    def __init__(self, leader: str = ",") -> None:
        self._leader = leader

    def _settings(self) -> ConfigDict:
        return {
            # ── Tabs behavior ─────────────────────────────────
            "tabs.background":                True,
            "tabs.last_close":                "startpage",
            "tabs.mousewheel_switching":      False,
            "tabs.close_mouse_button":        "middle",
            "tabs.close_mouse_button_on_bar": "new-tab",

            # ── Motion / reduced motion ───────────────────────
            "content.prefers_reduced_motion": True,

            # ── Load / startup ────────────────────────────────
            "url.start_pages":      ["about:blank"],
            "session.lazy_restore": True,

            # ── Clipboard ─────────────────────────────────────
            "content.javascript.clipboard": "none",

            # ── Media ─────────────────────────────────────────
            "content.autoplay": False,
            "content.mute":     False,

            # ── PDF ───────────────────────────────────────────
            "content.pdfjs": True,

            # ── New tab ───────────────────────────────────────
            "url.default_page": "about:blank",

            # ── Insert mode ───────────────────────────────────
            "input.insert_mode.auto_enter":  True,
            "input.insert_mode.auto_leave":  True,
            "input.insert_mode.plugins":     True,

            # ── Mouse behavior ────────────────────────────────
            "input.mouse.back_forward_buttons": True,
            "input.mouse.rocker_gestures":      False,

            # ── Quickmarks / Bookmarks UX ─────────────────────
            "completion.open_categories": [
                "searchengines",
                "quickmarks",
                "bookmarks",
                "history",
                "filesystem",
            ],
        }

    def _keybindings(self) -> List[Tuple[str, str, str]]:
        L = self._leader   # leader key prefix

        return [
            # ────────────────────────────────────────────────────
            # Normal mode: navigation
            # ────────────────────────────────────────────────────
            ("J",           "tab-prev",                           "normal"),
            ("K",           "tab-next",                           "normal"),
            ("H",           "back",                               "normal"),
            ("L",           "forward",                            "normal"),
            ("r",           "reload",                             "normal"),
            ("R",           "reload -f",                          "normal"),
            ("gd",          "download",                           "normal"),
            ("gD",          "download --dest ~/Desktop/",         "normal"),

            # ── Tab switching with Ctrl+Tab ────────────────────
            ("<ctrl-tab>",       "tab-next",                      "normal"),
            ("<ctrl-shift-tab>", "tab-prev",                      "normal"),

            # ── Open frame in tab / window ─────────────────────
            ("gf",          "hint frames",                        "normal"),
            ("wf",          "hint frames window",                 "normal"),

            # ────────────────────────────────────────────────────
            # Tabs: numbered focus + management
            # ────────────────────────────────────────────────────
            ("<alt-1>",     "tab-focus 1",                        "normal"),
            ("<alt-2>",     "tab-focus 2",                        "normal"),
            ("<alt-3>",     "tab-focus 3",                        "normal"),
            ("<alt-4>",     "tab-focus 4",                        "normal"),
            ("<alt-5>",     "tab-focus 5",                        "normal"),
            ("<alt-6>",     "tab-focus 6",                        "normal"),
            ("<alt-7>",     "tab-focus 7",                        "normal"),
            ("<alt-8>",     "tab-focus 8",                        "normal"),
            ("<alt-9>",     "tab-focus -1",                       "normal"),
            ("th",          "tab-move -",                         "normal"),
            ("tl",          "tab-move +",                         "normal"),
            ("tp",          "tab-pin",                            "normal"),
            ("tm",          "tab-mute",                           "normal"),
            ("tD",          "tab-only --prev",                    "normal"),

            # ── Duplicate tab ──────────────────────────────────
            ("tc",          "tab-clone",                          "normal"),

            # ────────────────────────────────────────────────────
            # Zoom
            # ────────────────────────────────────────────────────
            ("zi",          "zoom-in",                            "normal"),
            ("zo",          "zoom-out",                           "normal"),
            ("z0",          "zoom",                               "normal"),   # reset
            ("zz",          "zoom",                               "normal"),

            # ────────────────────────────────────────────────────
            # Quickmarks / Bookmarks
            # ────────────────────────────────────────────────────
            ("m",           "quickmark-save",                     "normal"),
            ("'",           "cmd-set-text :quickmark-load ",      "normal"),
            ('"',           "cmd-set-text :quickmark-load -t ",   "normal"),
            ("B",           "cmd-set-text :bookmark-load ",       "normal"),

            # ────────────────────────────────────────────────────
            # Hints (extended)
            # ────────────────────────────────────────────────────
            ("f",           "hint",                               "normal"),
            ("F",           "hint all tab",                       "normal"),
            (";d",          "hint links download",                "normal"),
            (";f",          "hint all tab-fg",                    "normal"),
            (";b",          "hint all tab-bg",                    "normal"),
            (";y",          "hint links yank",                    "normal"),
            (";Y",          "hint links yank-primary",            "normal"),
            (";r",          "hint --rapid links tab-bg",          "normal"),
            (";i",          "hint images",                        "normal"),
            (";I",          "hint images tab",                    "normal"),
            (";o",          "hint inputs",                        "normal"),

            # ────────────────────────────────────────────────────
            # Search
            # ────────────────────────────────────────────────────
            ("/",           "cmd-set-text /",                     "normal"),
            ("?",           "cmd-set-text ?",                     "normal"),
            ("n",           "search-next",                        "normal"),
            ("N",           "search-prev",                        "normal"),

            # ────────────────────────────────────────────────────
            # Leader key actions
            # ────────────────────────────────────────────────────
            (f"{L}r",       "config-source",                      "normal"),
            (f"{L}e",       "config-edit",                        "normal"),
            (f"{L}t",       "cmd-set-text :set tabs.position ",   "normal"),
            (f"{L}p",       "open -p",                            "normal"),
            (f"{L}P",       "open -t -- {primary}",               "normal"),
            (f"{L}y",       "yank",                               "normal"),
            (f"{L}Y",       "yank -s",                            "normal"),
            (f"{L}w",       "window-only",                        "normal"),
            (f"{L}d",       "download-clear",                     "normal"),
            (f"{L}D",       "download-delete",                    "normal"),
            (f"{L}x",       "tab-close",                          "normal"),
            (f"{L}X",       "undo",                               "normal"),
            (f"{L}q",       "quit",                               "normal"),
            (f"{L}Q",       "quit --save",                        "normal"),
            # Show downloads panel
            (f"{L}b",       "download-list",                      "normal"),
            # Navigate tab history (within the same tab)
            (f"{L}h",       "back",                               "normal"),
            (f"{L}l",       "forward",                            "normal"),
            # Window management
            (f"{L}n",       "open -w",                            "normal"),
            (f"{L}N",       "open -p -w",                         "normal"),

            # ────────────────────────────────────────────────────
            # Passthrough / insert mode
            # ────────────────────────────────────────────────────
            ("<Escape>",    "mode-leave",                         "insert"),
            ("<ctrl-e>",    "open-editor",                        "insert"),

            # ────────────────────────────────────────────────────
            # Caret mode
            # ────────────────────────────────────────────────────
            ("v",           "mode-enter caret",                   "normal"),
            ("V",           "mode-enter caret ;; selection-toggle --line", "normal"),
            ("<Escape>",    "mode-leave",                         "caret"),
            ("y",           "yank selection",                     "caret"),
            ("Y",           "yank selection -s",                  "caret"),

            # ────────────────────────────────────────────────────
            # Command mode
            # ────────────────────────────────────────────────────
            ("<ctrl-p>",    "completion-item-focus prev",         "command"),
            ("<ctrl-n>",    "completion-item-focus next",         "command"),
            ("<ctrl-j>",    "completion-item-focus next",         "command"),
            ("<ctrl-k>",    "completion-item-focus prev",         "command"),

            # ────────────────────────────────────────────────────
            # Prompt mode
            # ────────────────────────────────────────────────────
            ("<ctrl-p>",    "prompt-item-focus prev",             "prompt"),
            ("<ctrl-n>",    "prompt-item-focus next",             "prompt"),
            ("<ctrl-y>",    "prompt-accept yes",                  "prompt"),
            ("<Escape>",    "mode-leave",                         "prompt"),

            # ────────────────────────────────────────────────────
            # Hint mode extras
            # ────────────────────────────────────────────────────
            ("<Escape>",    "mode-leave",                         "hint"),
        ]

    def host_policies(self) -> List[HostPolicy]:
        """
        Data-driven per-host overrides for non-dev categories.

        Dev/localhost rules are intentionally NOT included here.
        They are owned by policies/host.py DEV_RULES and controlled by
        HOST_POLICY_DEV in config.py via build_default_host_registry(include_dev=...).

        Including them here AND in HostPolicyRegistry would apply the same
        pattern-scoped settings twice, which is harmless but noisy.

        These BehaviorLayer policies remain as a lightweight fallback for
        environments where policies/host.py is not loaded.
        """
        return [
            HostPolicy(
                pattern="*.google.com",
                settings={"content.cookies.accept": "all"},
                description="Google requires cookies for login",
                category="login",
            ),
            HostPolicy(
                pattern="*.github.com",
                settings={"content.cookies.accept": "all"},
                description="GitHub requires cookies",
                category="login",
            ),
            HostPolicy(
                pattern="discord.com",
                settings={
                    "content.cookies.accept":     "all",
                    "content.javascript.enabled": True,
                },
                description="Discord requires JS + cookies",
                category="social",
            ),
            HostPolicy(
                pattern="*.notion.so",
                settings={
                    "content.cookies.accept":     "all",
                    "content.javascript.enabled": True,
                },
                description="Notion requires JS",
                category="social",
            ),
            # NOTE: localhost / 127.0.0.1 rules removed — see DEV_RULES in
            # policies/host.py and HOST_POLICY_DEV in config.py.
        ]
