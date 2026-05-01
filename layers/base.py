"""
layers/base.py
==============
Base Layer — Foundational Defaults

Priority: 10 (lowest, applied first, overridable by all other layers)

This layer establishes the minimum viable qutebrowser configuration.
It defines defaults that make qutebrowser functional and sensible
before any other layers are applied.

Philosophy: explicit > implicit. Every setting here is intentional.
"""

from __future__ import annotations

from typing import Any, Dict, List, Tuple

from core.layer import BaseConfigLayer

ConfigDict = Dict[str, Any]


class BaseLayer(BaseConfigLayer):
    """
    Foundation layer: sensible defaults for a functional browser.
    Sets the baseline all other layers build upon.
    """

    name = "base"
    priority = 10
    description = "Foundational defaults — applied first, lowest priority"

    def _settings(self) -> ConfigDict:
        return {
            # ── Editor ──────────────────────────────────────────
            "editor.command": ["alacritty", "-e", "nvim", "{}"],

            # ── Downloads ───────────────────────────────────────
            "downloads.location.directory": "~/Downloads",
            "downloads.location.prompt": False,
            "downloads.open_dispatcher": None,
            "downloads.prevent_mixed_content": True,

            # ── Completion ──────────────────────────────────────
            "completion.delay": 0,
            "completion.height": "30%",
            "completion.quick": True,
            "completion.show": "auto",
            "completion.shrink": True,
            "completion.timestamp_format": "%Y-%m-%d %H:%M",
            "completion.use_best_match": False,

            # ── Input ───────────────────────────────────────────
            "input.insert_mode.auto_enter": True,
            "input.insert_mode.auto_leave": True,
            "input.insert_mode.plugins": False,
            "input.links_included_in_focus_chain": True,
            "input.mouse.rocker_gestures": False,
            "input.partial_timeout": 500,
            "input.spatial_navigation": False,

            # ── Tabs ────────────────────────────────────────────
            "tabs.background": True,
            "tabs.close_mouse_button": "middle",
            "tabs.last_close": "close",
            "tabs.mousewheel_switching": False,
            "tabs.new_position.related": "next",
            "tabs.new_position.unrelated": "last",
            "tabs.position": "top",
            "tabs.select_on_remove": "next",
            "tabs.show": "always",
            "tabs.title.format": "{audio}{index}: {current_title}",
            "tabs.title.format_pinned": "{audio}{index}",
            "tabs.undo_stack_size": 100,
            "tabs.wrap": True,
            "tabs.padding": {"bottom": 2, "left": 5, "right": 5, "top": 2},

            # ── URL / Navigation ─────────────────────────────────
            "url.auto_search": "naive",
            "url.default_page": "about:blank",
            "url.open_base_url": True,
            "url.searchengines": {
                "DEFAULT": "https://search.brave.com/search?q={}",
                "g":   "https://www.google.com/search?q={}",
                "gh":  "https://github.com/search?q={}&type=repositories",
                "yt":  "https://www.youtube.com/results?search_query={}",
                "w":   "https://en.wikipedia.org/w/index.php?search={}",
                "ddg": "https://duckduckgo.com/?q={}",
                "nix": "https://search.nixos.org/packages?query={}",
                "crates": "https://crates.io/search?q={}",
                "pypi": "https://pypi.org/search/?q={}",
                "mdn": "https://developer.mozilla.org/en-US/search?q={}",
            },
            "url.start_pages": ["about:blank"],

            # ── Scrolling ────────────────────────────────────────
            "scrolling.bar": "overlay",
            "scrolling.smooth": False,

            # ── Status Bar ───────────────────────────────────────
            "statusbar.show": "always",
            "statusbar.position": "bottom",
            "statusbar.widgets": ["keypress", "url", "scroll", "history", "tabs", "progress"],

            # ── Session ──────────────────────────────────────────
            "session.lazy_restore": False,
            "auto_save.session": True,
            "auto_save.interval": 15000,

            # ── Messages ─────────────────────────────────────────
            "messages.timeout": 2000,

            # ── Zoom ─────────────────────────────────────────────
            "zoom.default": "100%",
            "zoom.levels": [
                "25%","33%","50%","67%","75%","90%",
                "100%","110%","125%","150%","175%",
                "200%","250%","300%","400%","500%",
            ],

            # ── Hints ─────────────────────────────────────────────
            "hints.auto_follow": "unique-match",
            "hints.auto_follow_timeout": 0,
            "hints.border": "1px solid #E3C39D",
            "hints.chars": "asdfghjklqwertyuiopzxcvbnm",
            "hints.find_implementation": "python",
            "hints.hide_unmatched_rapid_hints": True,
            "hints.leave_on_load": False,
            "hints.min_chars": 1,
            "hints.mode": "letter",
            "hints.next_regexes": [
                "\\bnext\\b", "\\bmore\\b", "\\bnewer\\b",
                "\\b[>→»]\\b", "\\b(>>|»)\\b", "\\bcontinue\\b",
            ],
            "hints.padding": {"bottom": 2, "left": 3, "right": 3, "top": 2},
            "hints.prev_regexes": [
                "\\bprev(ious)?\\b", "\\bback\\b", "\\bolder\\b",
                "\\b[<←«]\\b", "\\b(<<|«)\\b",
            ],
            "hints.radius": 3,
            "hints.scatter": True,
            "hints.uppercase": False,

            # ── Misc ─────────────────────────────────────────────
            "confirm_quit": ["downloads"],
            "new_instance_open_target": "tab",
            "new_instance_open_target_window": "last-focused",
            "prompt.radius": 8,
            "prompt.filebrowser": True,
            "spellcheck.languages": ["en-US"],
        }

    def _keybindings(self) -> List[Tuple[str, str, str]]:
        """
        Returns list of (key, command, mode) tuples.
        Base bindings: minimal and non-opinionated.
        """
        return [
            # ── Normal mode: essential navigation ─────────────
            ("<Escape>",    "mode-enter normal",           "command"),
            ("gg",          "scroll-to-perc 0",            "normal"),
            ("G",           "scroll-to-perc",              "normal"),
            ("<ctrl-d>",    "scroll-page 0 0.5",           "normal"),
            ("<ctrl-u>",    "scroll-page 0 -0.5",          "normal"),
            ("d",           "tab-close",                   "normal"),
            ("u",           "undo",                        "normal"),
            ("co",          "tab-only",                    "normal"),
            ("gt",          "tab-next",                    "normal"),
            ("gT",          "tab-prev",                    "normal"),
            # ── Open ─────────────────────────────────────────
            ("o",           "cmd-set-text :open ",         "normal"),
            ("O",           "cmd-set-text :open -t ",      "normal"),
            ("go",          "cmd-set-text :open {url}",    "normal"),
            ("gO",          "cmd-set-text :open -t {url}", "normal"),
            # ── Yank ─────────────────────────────────────────
            ("yy",          "yank",                        "normal"),
            ("yt",          "yank title",                  "normal"),
            # ── Pass-through ──────────────────────────────────
            ("<ctrl-v>",    "mode-enter passthrough",      "normal"),
        ]

    def _aliases(self) -> ConfigDict:
        return {
            "q":  "quit",
            "qa": "quit --save",
            "w":  "session-save",
            "wq": "quit --save",
        }
