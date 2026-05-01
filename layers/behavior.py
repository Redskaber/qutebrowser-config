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
  - Per-host policy overrides (data-driven)

Pattern: Data-Driven Configuration + Command pattern for keybindings
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Tuple

from core.layer import BaseConfigLayer

ConfigDict = Dict[str, Any]


# ─────────────────────────────────────────────
# Per-Host Policy (data-driven overrides)
# ─────────────────────────────────────────────
@dataclass
class HostPolicy:
    """
    Declarative per-host configuration override.
    Applied via config.set(..., pattern=host_pattern).
    """
    pattern:     str        # e.g. "*.google.com"
    settings:    ConfigDict = field(default_factory=dict[str, Any])
    description: str        = ""


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

    def __init__(self, leader: str = ","):
        self._leader = leader

    def _settings(self) -> ConfigDict:
        return {
            # ── Tabs behavior ─────────────────────────────────
            "tabs.background": True,
            "tabs.last_close": "startpage",
            "tabs.mousewheel_switching": False,
            "tabs.close_mouse_button": "middle",
            "tabs.close_mouse_button_on_bar": "new-tab",

            # ── Back/forward ──────────────────────────────────
            "content.prefers_reduced_motion": True,

            # ── Load / startup ────────────────────────────────
            "url.start_pages": ["about:blank"],
            "session.lazy_restore": True,

            # ── Clipboard ─────────────────────────────────────
            "content.javascript.clipboard": "none",

            # ── Media ─────────────────────────────────────────
            "content.autoplay": False,
            "content.mute": False,

            # ── PDF ───────────────────────────────────────────
            "content.pdfjs": True,

            # ── New tab ───────────────────────────────────────
            "url.default_page": "about:blank",

            # ── External programs ─────────────────────────────
            "downloads.open_dispatcher": None,

            # ── Caret mode ────────────────────────────────────
            "input.insert_mode.auto_enter": True,
            "input.insert_mode.auto_leave": True,
            "input.insert_mode.plugins": True,

            # ── Mouse behavior ────────────────────────────────
            "input.mouse.back_forward_buttons": True,
            "input.mouse.rocker_gestures": False,

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
            ("J",        "tab-prev",                           "normal"),
            ("K",        "tab-next",                           "normal"),
            ("H",        "back",                               "normal"),
            ("L",        "forward",                            "normal"),
            ("r",        "reload",                             "normal"),
            ("R",        "reload -f",                          "normal"),
            ("gd",       "download",                           "normal"),
            ("gD",       "download --dest ~/Desktop/",         "normal"),

            # ────────────────────────────────────────────────────
            # Tabs
            # ────────────────────────────────────────────────────
            ("<alt-1>",  "tab-focus 1",                        "normal"),
            ("<alt-2>",  "tab-focus 2",                        "normal"),
            ("<alt-3>",  "tab-focus 3",                        "normal"),
            ("<alt-4>",  "tab-focus 4",                        "normal"),
            ("<alt-5>",  "tab-focus 5",                        "normal"),
            ("<alt-6>",  "tab-focus 6",                        "normal"),
            ("<alt-7>",  "tab-focus 7",                        "normal"),
            ("<alt-8>",  "tab-focus 8",                        "normal"),
            ("<alt-9>",  "tab-focus -1",                       "normal"),
            ("th",       "tab-move -",                         "normal"),
            ("tl",       "tab-move +",                         "normal"),
            ("tp",       "tab-pin",                            "normal"),
            ("tm",       "tab-mute",                           "normal"),
            ("tD",       "tab-only --prev",                    "normal"),

            # ────────────────────────────────────────────────────
            # Quickmarks / Bookmarks
            # ────────────────────────────────────────────────────
            ("m",        "quickmark-save",                     "normal"),
            ("'",        "cmd-set-text :quickmark-load ",      "normal"),
            ('"',        "cmd-set-text :quickmark-load -t ",   "normal"),
            ("B",        "cmd-set-text :bookmark-load ",       "normal"),

            # ────────────────────────────────────────────────────
            # Hints (extended)
            # ────────────────────────────────────────────────────
            ("f",        "hint",                               "normal"),
            ("F",        "hint all tab",                       "normal"),
            (";d",       "hint links download",                "normal"),
            (";f",       "hint all tab-fg",                    "normal"),
            (";b",       "hint all tab-bg",                    "normal"),
            (";y",       "hint links yank",                    "normal"),
            (";Y",       "hint links yank-primary",            "normal"),
            (";r",       "hint --rapid links tab-bg",          "normal"),
            (";i",       "hint images",                        "normal"),
            (";I",       "hint images tab",                    "normal"),
            (";o",       "hint inputs",                        "normal"),

            # ────────────────────────────────────────────────────
            # Search
            # ────────────────────────────────────────────────────
            ("/",        "cmd-set-text /",                     "normal"),
            ("?",        "cmd-set-text ?",                     "normal"),
            ("n",        "search-next",                        "normal"),
            ("N",        "search-prev",                        "normal"),

            # ────────────────────────────────────────────────────
            # Leader key actions
            # ────────────────────────────────────────────────────
            (f"{L}r",    "config-source",                      "normal"),
            (f"{L}e",    "config-edit",                        "normal"),
            (f"{L}t",    "cmd-set-text :set tabs.position ",   "normal"),
            (f"{L}p",    "open -p",                            "normal"),
            (f"{L}P",    "open -t -- {primary}",               "normal"),
            (f"{L}y",    "yank",                               "normal"),
            (f"{L}Y",    "yank -s",                            "normal"),
            (f"{L}w",    "window-only",                        "normal"),
            (f"{L}d",    "download-clear",                     "normal"),
            (f"{L}D",    "download-delete",                    "normal"),
            (f"{L}x",    "tab-close",                          "normal"),
            (f"{L}X",    "undo",                               "normal"),
            (f"{L}q",    "quit",                               "normal"),
            (f"{L}Q",    "quit --save",                        "normal"),

            # ────────────────────────────────────────────────────
            # Passthrough / insert mode
            # ────────────────────────────────────────────────────
            ("<Escape>", "mode-leave",                         "insert"),
            ("<ctrl-e>", "open-editor",                        "insert"),

            # ────────────────────────────────────────────────────
            # Caret mode
            # ────────────────────────────────────────────────────
            ("v",        "mode-enter caret",                   "normal"),
            ("V",        "mode-enter caret ;; selection-toggle --line", "normal"),
            ("<Escape>", "mode-leave",                         "caret"),
            ("y",        "yank selection",                     "caret"),
            ("Y",        "yank selection -s",                  "caret"),

            # ────────────────────────────────────────────────────
            # Command mode
            # ────────────────────────────────────────────────────
            ("<ctrl-p>", "completion-item-focus prev",         "command"),
            ("<ctrl-n>", "completion-item-focus next",         "command"),
            ("<ctrl-j>", "completion-item-focus next",         "command"),
            ("<ctrl-k>", "completion-item-focus prev",         "command"),
        ]

    def host_policies(self) -> List[HostPolicy]:
        """
        Data-driven per-host overrides.
        Applied in config.py after all layer merges.
        """
        return [
            HostPolicy(
                pattern="*.google.com",
                settings={"content.cookies.accept": "all"},
                description="Google requires cookies for login",
            ),
            HostPolicy(
                pattern="*.github.com",
                settings={"content.cookies.accept": "all"},
                description="GitHub requires cookies",
            ),
            HostPolicy(
                pattern="discord.com",
                settings={
                    "content.cookies.accept": "all",
                    "content.javascript.enabled": True,
                },
                description="Discord requires JS + cookies",
            ),
            HostPolicy(
                pattern="*.notion.so",
                settings={
                    "content.cookies.accept": "all",
                    "content.javascript.enabled": True,
                },
                description="Notion requires JS",
            ),
            HostPolicy(
                pattern="localhost",
                settings={
                    "content.cookies.accept": "all",
                    "content.javascript.enabled": True,
                    "content.tls.certificate_errors": "load-insecurely",
                },
                description="Local development: allow all",
            ),
            HostPolicy(
                pattern="127.0.0.1",
                settings={
                    "content.cookies.accept": "all",
                    "content.javascript.enabled": True,
                    "content.tls.certificate_errors": "load-insecurely",
                },
                description="Local development: allow all",
            ),
        ]


