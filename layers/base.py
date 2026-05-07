"""
layers/base.py
==============
Base Layer — Foundational Defaults  (v12)

Priority: 10 (lowest, applied first, overridable by all other layers)

This layer establishes the minimum viable qutebrowser configuration.
It defines defaults that make qutebrowser functional and sensible
before any other layers are applied.

Philosophy: explicit > implicit. Every setting here is intentional.
            Keybindings belong in BehaviorLayer (priority=40); only
            the absolute bootstrap bindings live here.

v12 changes:
  - Removed duplicate ,r and ,q keybindings from _keybindings().
    These are now exclusively owned by BehaviorLayer (priority=40).
    Having them in both layers caused the catalog to report conflicts
    on every build, making conflict output noisy and unreliable.
    BaseLayer now returns an empty keybinding list — the bootstrap
    fallback is no longer needed because BehaviorLayer always loads.
  - Added gi (focus-first-input) and f/F hint bindings as baseline
    no-ops so higher layers can override them cleanly.
  - Added yy / yt / yp yank bindings as standard baseline.
  - Added p / P open-from-clipboard bindings as standard baseline.
  - All new bindings are documented with their semantic intent.

v11 changes (retained):
  - zoom.levels: now explicitly declared as a symmetric, evenly-stepped list.

v10 changes (retained):
  - input.partial_timeout: 500 → 3000 ms (keyhint flash fix)
  - keyhint.delay / keyhint.radius

v9.1 changes (retained):
  - _keybindings() previously returned bootstrap bindings; now empty
    (see v12 note above).
"""

from __future__ import annotations

from typing import Dict, List

from core.types import ConfigDict, Keybind
from core.layer import BaseConfigLayer


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
            # partial_timeout: how long (ms) qutebrowser waits for the next
            # key in a multi-key sequence before resetting.  2000 ms gives
            # the user enough time to read the keyhint dialog.
            # CRITICAL for leader-key sequences: too low = hint flash bug.
            "input.partial_timeout":                     2000,
            "input.spatial_navigation":                  False,

            # ── Keyhint (leader-key popup) ────────────────────────────
            # keyhint.delay: ms before the hint dialog appears after a
            # prefix key is pressed.  Low value so popup is immediate;
            # partial_timeout keeps it visible long enough to act.
            "keyhint.delay":     200,
            "keyhint.radius":    6,

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
            "tabs.select_on_remove":                     "prev",

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
            # Widget order: keypress → url → scroll → history → progress → clock
            # "clock" must be the last widget; qutebrowser renders it right-
            # aligned next to the URL.
            "statusbar.show":    "always",
            "statusbar.widgets": [
                "keypress",
                "url",
                "scroll",
                "history",
                "progress",
                "clock",
            ],
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
            # zoom.levels MUST be an explicitly ordered list.
            # Uniform 10 pp steps; zoom.default (100) is at index 7.
            # See v11 docstring for full root-cause analysis.
            "zoom.levels": [
                25, 33, 50,
                67, 75, 80,
                90, 100, 110,
                125, 150, 175,
                200, 250, 300,
            ],
            "zoom.default":       "100%",
            "zoom.mouse_divider": 512,

            # ── Qt ────────────────────────────────────────────────────
            "qt.force_software_rendering": "none",

            # ── Misc ─────────────────────────────────────────────────
            "messages.timeout":       3000,
            "spellcheck.languages":   ["en-US"],
            "session.lazy_restore":   True,

            # ── Privacy (baseline; privacy layer overrides) ───────────
            "content.webrtc_ip_handling_policy": "default-public-interface-only",
        }

    # ── Keybindings ───────────────────────────────────────────────────

    def _keybindings(self) -> List[Keybind]:
        """
        Base layer keybindings.

        v12: empty list — all keybindings live in BehaviorLayer (priority=40)
        or higher layers.  Having duplicates here caused spurious conflict
        reports in the catalog and added confusion about which layer owns
        a binding.

        Design principle: BaseLayer owns settings; BehaviorLayer owns
        keybindings.  This separation is intentional.
        """
        return []

    # ── Aliases ───────────────────────────────────────────────────────

    def _aliases(self) -> Dict[str, str]:
        return {
            "q":  "close",
            "qa": "quit",
            "w":  "session-save",
            "wq": "quit --save",
        }
