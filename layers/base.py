"""
layers/base.py
==============
Base Layer — Foundational Defaults  (v9.1)

Priority: 10 (lowest, applied first, overridable by all other layers)

This layer establishes the minimum viable qutebrowser configuration.
It defines defaults that make qutebrowser functional and sensible
before any other layers are applied.

Philosophy: explicit > implicit. Every setting here is intentional.

v9.1 changes:
  - _keybindings() now returns two essential base-layer keybindings:
      ,r  → config-source  (reload config — the most critical keybinding)
      ,q  → close          (close current tab — universally useful)
    Previously returned [] so build() never included a "keybindings" key,
    breaking TestBaseLayer.test_has_keybindings.
    More workflow keybindings continue to live in BehaviorLayer (priority=40).

v9 changes:
  - Added ``content.pdfjs``: True
  - Added ``content.javascript.alert``: True
  - Added ``content.javascript.prompt``: True
  - Added ``content.javascript.can_open_tabs_automatically``: False
  - Added ``tabs.title.format_pinned``: "{index}: {current_title}"
  - Added ``tabs.pinned.frozen``: False
  - Added ``content.fullscreen.window``: True
  - Added ``qt.force_software_rendering``: "none"
  - Added ``messages.timeout``: 5000ms
  - Added ``url.default_page``: "about:blank"
  - Added ``content.images``: True

v6 changes (retained):
  - Removed invalid key ``downloads.prevent_mixed_content``
  - Added tabs.favicons.scale, tabs.indicator.*
  - Added tabs.title.alignment, tabs.max_width, tabs.min_width
  - Added content.blocking.enabled = False (privacy layer owns this)
  - Added completion.cmd_history_max_items
  - Added hints.find_implementation
  - Added downloads.location.remember
  - Cleaned up statusbar.widgets
"""

from __future__ import annotations

from typing import Dict, List

from core.types import ConfigDict
from core.layer import BaseConfigLayer
from keybindings.catalog import Keybind


class BaseLayer(BaseConfigLayer):
    """
    Foundational configuration layer.

    Establishes safe, explicit defaults across all qutebrowser setting
    categories.  Higher-priority layers override individual keys as needed.
    """

    name     = "base"
    priority = 10

    # ── Settings ──────────────────────────────────────────────────────

    def _settings(self) -> ConfigDict:
        return {
            # ── Editor ───────────────────────────────────────────────
            "editor.command": ["alacritty", "-e", "nvim", "{}"],

            # ── Downloads ────────────────────────────────────────────
            "downloads.location.directory": "~/Downloads",
            "downloads.location.prompt":    False,
            "downloads.location.remember":  True,
            "downloads.open_dispatcher":    None,
            "downloads.remove_finished":    0,

            # ── Content ──────────────────────────────────────────────
            "content.pdfjs":   True,   # use built-in PDF viewer
            "content.images":  True,   # images on by default (explicit)

            # ── Completion ───────────────────────────────────────────
            "completion.delay":                  0,
            "completion.height":                 "30%",
            "completion.quick":                  True,
            "completion.show":                   "auto",
            "completion.shrink":                 True,
            "completion.timestamp_format":       "%Y-%m-%d %H:%M",
            "completion.use_best_match":         False,
            "completion.cmd_history_max_items":  100,

            # ── Input ────────────────────────────────────────────────
            "input.insert_mode.auto_enter":              True,
            "input.insert_mode.auto_leave":              True,
            "input.insert_mode.plugins":                 False,
            "input.links_included_in_focus_chain":       True,
            "input.mouse.rocker_gestures":               False,
            "input.partial_timeout":                     500,
            "input.spatial_navigation":                  False,

            # ── Tabs ─────────────────────────────────────────────────
            "tabs.background":                           True,
            "tabs.close_mouse_button":                   "middle",
            "tabs.close_mouse_button_on_bar":            "new-tab",
            "tabs.last_close":                           "startpage",
            "tabs.mousewheel_switching":                 False,
            "tabs.new_position.related":                 "next",
            "tabs.new_position.unrelated":               "last",
            "tabs.position":                             "top",
            "tabs.show":                                 "always",
            "tabs.wrap":                                 True,
            "tabs.favicons.scale":                       1.0,
            "tabs.indicator.width":                      3,
            "tabs.indicator.padding": {
                "top": 0, "bottom": 0, "left": 0, "right": 4,
            },
            "tabs.title.alignment":                      "left",
            "tabs.title.format":         "{index}: {current_title}",
            "tabs.title.format_pinned":  "{index}: {current_title}",
            "tabs.max_width":                            250,
            "tabs.min_width":                            30,
            "tabs.padding": {
                "top": 2, "bottom": 2, "left": 5, "right": 5,
            },
            "tabs.pinned.frozen":                        False,

            # ── URL / Search ──────────────────────────────────────────
            "url.searchengines": {
                "DEFAULT": "https://www.google.com/search?q={}",
                "g":       "https://www.google.com/search?q={}",
                "ddg":     "https://duckduckgo.com/?q={}",
                "brave":   "https://search.brave.com/search?q={}",
                "yt":      "https://www.youtube.com/results?search_query={}",
                "gh":      "https://github.com/search?q={}",
                "mdn":     "https://developer.mozilla.org/search?q={}",
                "pypi":    "https://pypi.org/search/?q={}",
                "wiki":    "https://en.wikipedia.org/wiki/{}",
                "map":     "https://www.openstreetmap.org/search?query={}",
            },
            "url.start_pages":  ["about:blank"],
            "url.default_page": "about:blank",
            "url.auto_search":  "naive",
            "url.open_base_url": False,

            # ── Status bar ────────────────────────────────────────────
            "statusbar.show":    "always",
            "statusbar.widgets": ["keypress", "url", "scroll", "progress", "clock"],
            "statusbar.padding": {
                "top": 1, "bottom": 1, "left": 3, "right": 3,
            },

            # ── Hints ─────────────────────────────────────────────────
            "hints.auto_follow":         "unique-match",
            "hints.auto_follow_timeout": 0,
            "hints.chars":               "asdfghjkl",
            "hints.find_implementation": "python",
            "hints.mode":                "letter",
            "hints.scatter":             True,
            "hints.uppercase":           False,
            "hints.min_chars":           1,
            "hints.padding": {
                "top": 1, "bottom": 1, "left": 3, "right": 3,
            },
            "hints.radius": 3,

            # ── Content defaults (baseline) ───────────────────────────
            # The privacy layer overrides these for its profiles.
            "content.blocking.enabled":                      False,
            "content.javascript.enabled":                    True,
            "content.javascript.alert":                      True,
            "content.javascript.prompt":                     True,
            "content.javascript.can_open_tabs_automatically": False,
            "content.autoplay":                              False,
            "content.cookies.accept":                        "no-3rdparty",
            "content.cookies.store":                         True,
            "content.geolocation":                           False,
            "content.notifications.enabled":                 False,
            "content.fullscreen.window":                     True,
            "content.prefers_reduced_motion":                False,

            # ── Fonts ─────────────────────────────────────────────────
            "fonts.default_family": "monospace",
            "fonts.default_size":   "10pt",
            "fonts.web.size.default": 16,
            "fonts.web.size.minimum":  6,

            # ── Zoom ─────────────────────────────────────────────────
            "zoom.default":       "100%",
            "zoom.mouse_divider": 512,

            # ── Qt ────────────────────────────────────────────────────
            "qt.force_software_rendering": "none",

            # ── Misc ─────────────────────────────────────────────────
            "messages.timeout":       5000,
            "spellcheck.languages":   ["en-US"],
            "session.lazy_restore":   True,

            # ── Privacy (baseline; privacy layer overrides) ───────────
            "content.webrtc_ip_handling_policy": "default-public-interface-only",
        }

    # ── Keybindings ───────────────────────────────────────────────────

    def _keybindings(self) -> List[Keybind]:
        """
        Essential base-layer keybindings.

        Only the most fundamental bindings live here; all workflow and
        navigation bindings belong in BehaviorLayer (priority=40).

        v9.1: previously returned [] which prevented "keybindings" from
        appearing in build() output — now returns the two most critical
        bindings so every installation has at least a config-reload key.
        """
        return [
            # ── Config management ────────────────────────────────────
            # ,r   reload config from disk  (most critical single binding)
            (",r", "config-source", "normal"),
            # ,q   close current tab
            (",q", "close",         "normal"),
        ]

    # ── Aliases ───────────────────────────────────────────────────────

    def _aliases(self) -> Dict[str, str]:
        return {
            "q":  "close",
            "qa": "quit",
            "w":  "session-save",
            "wq": "quit --save",
        }
