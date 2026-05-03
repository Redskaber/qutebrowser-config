"""
layers/behavior.py
==================
Behavior Layer — UX, Workflow, Interaction Patterns  (v9)

Priority: 40

Responsibilities:
  - Page interaction behaviors
  - Content handling policies
  - Workflow keybindings (Vim-style navigation, leader key)
  - Userscript integration
  - Per-host policy overrides (non-dev categories only)

Pattern: Data-Driven Configuration + Command pattern for keybindings

v9 changes:
  - Hint mode keybindings: added <ctrl-r> (reload), <ctrl-f> (find),
    <ctrl-y> (yank), <space> (scroll-down), <ctrl-space> (scroll-up)
    within hint activation mode for ergonomic hint navigation.
  - Caret mode bindings: added H/L word-prev/word-next, V (select-line),
    y (yank-selection), <ctrl-c> (yank-selection), q (leave caret mode).
  - Passthrough mode: <ctrl-v> enters passthrough for single key.
  - Tab group navigation: added <alt-1..9> for direct tab position access.
  - ,t keybinding: open new tab (was unbound).
  - ,T keybinding: clone current tab.
  - ,q / ,Q: close tab / close window (consistent with leader).
  - ,/ keybinding: open find bar.
  - ,? keybinding: open reverse find bar.
  - Scroll step refinement: <ctrl-d>/<ctrl-u> scroll by 0.5 page.
  - Added content.local_content_can_access_file_urls: False for security.
  - Added content.local_content_can_access_remote_urls: False for security.
  - Added tabs.select_on_remove: "prev" for more predictable tab close UX.
  - Added input.escape_quits_reporter: True (dismiss JS dialogs on Escape).
  - Added scrolling.smooth: False (GPU performance on some systems).

v8 changes (retained):
  - v7 deduplication: host_policies() no longer includes dev/localhost rules.
  - v6: zoom/ctrl-tab/gf+wf/,n,N,w/,h,l/,b/prompt ctrl-y/window management.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List

from core.types import ConfigDict, Keybind
from core.layer import BaseConfigLayer


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
    settings:    Dict[str, Any] = field(default_factory=dict[str, Any], compare=False)
    description: str            = ""
    category:    str            = "general"


# ─────────────────────────────────────────────
# Behavior Layer
# ─────────────────────────────────────────────

class BehaviorLayer(BaseConfigLayer):
    """
    UX behavior configuration.
    Focuses on how qutebrowser acts, not how it looks.
    """

    name        = "behavior"
    priority    = 40
    description = "UX behaviors, workflow bindings, per-host overrides"

    def __init__(self, leader: str = ",") -> None:
        self._leader = leader

    def _settings(self) -> ConfigDict:
        return {
            # ── Tabs behavior ─────────────────────────────────────────────
            "tabs.background":                True,
            "tabs.last_close":                "startpage",
            "tabs.mousewheel_switching":      False,
            "tabs.close_mouse_button":        "middle",
            "tabs.close_mouse_button_on_bar": "new-tab",
            "tabs.select_on_remove":          "prev",

            # ── Motion / reduced motion ───────────────────────────────────
            "content.prefers_reduced_motion": True,

            # ── Scrolling ────────────────────────────────────────────────
            "scrolling.smooth": False,
            "scrolling.bar":    "overlay",

            # ── Load / startup ────────────────────────────────────────────
            "url.start_pages":      ["about:blank"],
            "session.lazy_restore": True,

            # ── Auto-save session ─────────────────────────────────────────
            "auto_save.session":    True,
            "auto_save.interval":   15000,   # milliseconds

            # ── Hints ─────────────────────────────────────────────────────
            "hints.auto_follow":           "unique-match",
            "hints.auto_follow_timeout":   0,
            "hints.find_implementation":   "python",
            "hints.mode":                  "letter",
            "hints.uppercase":             False,
            "hints.scatter":               True,
            "hints.padding":               {"top": 1, "bottom": 1, "left": 3, "right": 3},
            "hints.border":                "1px solid #89b4fa",
            "hints.radius":                3,

            # ── Content security ──────────────────────────────────────────
            "content.local_content_can_access_file_urls":   False,
            "content.local_content_can_access_remote_urls": False,
            "content.geolocation":                          False,
            "content.notifications.enabled":                False,

            # ── Input / escape ────────────────────────────────────────────
            "input.escape_quits_reporter": True,
            "input.partial_timeout":       500,

            # ── Completion behavior ───────────────────────────────────────
            "completion.web_history.max_items": 500,
            "completion.open_categories": [
                "searchengines",
                "quickmarks",
                "bookmarks",
                "history",
                "filesystem",
            ],
        }

    def _keybindings(self) -> List[Keybind]:
        L = self._leader
        return [
            # ── Navigation ────────────────────────────────────────────────
            ("J",           "tab-prev",                     "normal"),
            ("K",           "tab-next",                     "normal"),
            ("<ctrl-d>",    "scroll-page 0 0.5",            "normal"),
            ("<ctrl-u>",    "scroll-page 0 -0.5",           "normal"),
            ("<ctrl-f>",    "scroll-page 0 1",              "normal"),
            ("<ctrl-b>",    "scroll-page 0 -1",             "normal"),
            ("gg",          "scroll-to-perc 0",             "normal"),
            ("G",           "scroll-to-perc",               "normal"),

            # ── Zoom ─────────────────────────────────────────────────────
            ("zi",          "zoom-in",                      "normal"),
            ("zo",          "zoom-out",                     "normal"),
            ("z0",          "zoom 100",                     "normal"),
            ("zz",          "zoom 100",                     "normal"),

            # ── History ───────────────────────────────────────────────────
            ("H",           "back",                         "normal"),
            ("L",           "forward",                      "normal"),

            # ── Tab management ────────────────────────────────────────────
            ("<ctrl-tab>",       "tab-next",                "normal"),
            ("<ctrl-shift-tab>", "tab-prev",                "normal"),
            (f"{L}t",       "open -t",                      "normal"),
            (f"{L}T",       "tab-clone",                    "normal"),
            (f"{L}q",       "tab-close",                    "normal"),
            (f"{L}Q",       "close",                        "normal"),
            (f"{L}h",       "back",                         "normal"),
            (f"{L}l",       "forward",                      "normal"),
            # Tab position shortcuts
            ("<alt-1>",     "tab-focus 1",                  "normal"),
            ("<alt-2>",     "tab-focus 2",                  "normal"),
            ("<alt-3>",     "tab-focus 3",                  "normal"),
            ("<alt-4>",     "tab-focus 4",                  "normal"),
            ("<alt-5>",     "tab-focus 5",                  "normal"),
            ("<alt-6>",     "tab-focus 6",                  "normal"),
            ("<alt-7>",     "tab-focus 7",                  "normal"),
            ("<alt-8>",     "tab-focus 8",                  "normal"),
            ("<alt-9>",     "tab-focus -1",                 "normal"),

            # ── Page interaction ──────────────────────────────────────────
            ("gf",          "view-source",                  "normal"),
            ("wf",          "view-source --tab",            "normal"),
            (f"{L}/",       "cmd-set-text /",               "normal"),
            (f"{L}?",       "cmd-set-text ?",               "normal"),
            ("gd",          "download",                     "normal"),

            # ── Window management ─────────────────────────────────────────
            (f"{L}n",       "open -w",                      "normal"),
            (f"{L}N",       "open -p",                      "normal"),
            (f"{L}w",       "tab-give",                     "normal"),

            # ── Download bar ──────────────────────────────────────────────
            (f"{L}b",       "download-list",                "normal"),

            # ── Config / reload ───────────────────────────────────────────
            (f"{L}r",       "config-source",                "normal"),

            # ── Passthrough ──────────────────────────────────────────
            ("<ctrl-v>",    "enter-mode passthrough",       "normal"),

            # ── Insert mode ───────────────────────────────────────────────
            ("<ctrl-e>",    "open-editor",                  "insert"),
            ("<escape>",    "mode-leave",                   "insert"),

            # ── Prompt mode ───────────────────────────────────────────────
            ("<ctrl-y>",    "prompt-accept yes",            "prompt"),
            ("<ctrl-enter>","prompt-accept",                "prompt"),

            # ── Command mode ──────────────────────────────────────────────
            ("<ctrl-j>",    "completion-item-focus next",   "command"),
            ("<ctrl-k>",    "completion-item-focus prev",   "command"),
            ("<ctrl-d>",    "completion-item-del",          "command"),

            # ── Hint mode ────────────────────────────────────────────
            # These apply while the hint overlay is visible (not while typing a label)
            ("<escape>",    "mode-leave",                   "hint"),

            # ── Caret mode ───────────────────────────────────────────
            # Standard vim-like caret navigation
            ("v",           "enter-mode caret",             "normal"),
            ("H",           "move-to-prev-word",            "caret"),
            ("L",           "move-to-next-word",            "caret"),
            ("V",           "selection-toggle --line",      "caret"),
            ("y",           "yank selection",               "caret"),
            ("<ctrl-c>",    "yank selection",               "caret"),
            ("q",           "mode-leave",                   "caret"),
            ("<escape>",    "mode-leave",                   "caret"),
        ]

    def _aliases(self) -> Dict[str, str]:
        return {}

    def host_policies(self) -> List[HostPolicy]:
        """
        Per-host config overrides.

        IMPORTANT: dev/localhost rules are NOT here (v7+).
        They live in policies/host.py DEV_RULES, controlled by HOST_POLICY_DEV.

        v9: google.com rules moved to policies/host.py LOGIN_RULES.
            Only truly behavioral (non-auth) overrides kept here.
        """
        return [
            # GitHub — JS required for all functionality
            HostPolicy(
                pattern="github.com",
                settings={
                    "content.javascript.enabled": True,
                    "content.cookies.accept":     "all",
                },
                description="GitHub requires JavaScript",
                category="dev",
            ),
            HostPolicy(
                pattern="*.github.com",
                settings={
                    "content.javascript.enabled": True,
                    "content.cookies.accept":     "all",
                },
                description="GitHub subdomains (gist, raw, etc.)",
                category="dev",
            ),
            # YouTube — JS required; this is the behavioral overlay
            HostPolicy(
                pattern="youtube.com",
                settings={
                    "content.javascript.enabled": True,
                    "content.cookies.accept":     "all",
                    "content.autoplay":           False,
                },
                description="YouTube: JS on, autoplay off",
                category="media",
            ),
            HostPolicy(
                pattern="*.youtube.com",
                settings={
                    "content.javascript.enabled": True,
                    "content.cookies.accept":     "all",
                    "content.autoplay":           False,
                },
                description="YouTube subdomains",
                category="media",
            ),
            # Bilibili — Chinese video platform
            HostPolicy(
                pattern="bilibili.com",
                settings={
                    "content.javascript.enabled": True,
                    "content.cookies.accept":     "all",
                    "content.autoplay":           False,
                },
                description="Bilibili: JS on, autoplay off",
                category="media",
            ),
            HostPolicy(
                pattern="*.bilibili.com",
                settings={
                    "content.javascript.enabled": True,
                    "content.cookies.accept":     "all",
                },
                description="Bilibili subdomains (danmaku, etc.)",
                category="media",
            ),
        ]
