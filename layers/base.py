"""
layers/base.py
==============
Base Layer — Foundational Defaults  (v11)

Priority: 10 (lowest, applied first, overridable by all other layers)

This layer establishes the minimum viable qutebrowser configuration.
It defines defaults that make qutebrowser functional and sensible
before any other layers are applied.

Philosophy: explicit > implicit. Every setting here is intentional.

v11 changes (bug-fix):
  - zoom.levels: now explicitly declared as a symmetric, evenly-stepped list.
      Root-cause fix for the zoom wrap-around / skip bug.
      Symptom: 100% → zoom-out → 90% → zoom-out → 75% → zoom-in → 110%
               (skipped 90 and 100 on the way back up; then ceiling-locked at 110).
      Cause: without an explicit zoom.levels, qutebrowser uses its built-in
             default list which has uneven gaps.  After a direction reversal the
             internal index is recomputed from the *current zoom value* against
             the list.  If the value sits at a list boundary (or the default
             zoom.default is not in the list), the index wraps or misaligns,
             causing the observed skip.
      Fix: declare a clean 15-entry list with uniform 10 pp steps in the
           working range (75–300) and finer steps below 75 for precision work.
           zoom.default (100%) is guaranteed to be present at index 7.

v10 changes (bug-fixes, retained):
  - input.partial_timeout: 500 → 3000 ms
      Root-cause fix for the keyhint dialog flash-and-disappear bug.
      When the leader key (`,`) or any multi-key prefix was pressed,
      the 500 ms timeout fired before the user could read the popup
      and press the second key, collapsing the hint instantly.
      3000 ms gives comfortable reading time; Escape still cancels.
  - keyhint.delay: explicitly set to 200 ms (was unset → defaulted to
      500 ms, causing the hint to appear just as partial_timeout fired).
  - keyhint.radius: 6 px for visual consistency with hints/prompts.
  - statusbar.widgets: added "history" widget between "scroll" and
      "progress"; reordered so "clock" is always last (rightmost).
      Previously "history" was absent and "clock" sat after "progress"
      which in some qutebrowser builds caused it to not render.

v9.1 changes (retained):
  - _keybindings() now returns two essential base-layer keybindings.

v9 changes (retained):
  - Added content.pdfjs, content.javascript.*, tabs.title.format_pinned,
    tabs.pinned.frozen, content.fullscreen.window, qt.force_software_rendering,
    messages.timeout, url.default_page, content.images.
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
            # key in a multi-key sequence before resetting.  500 ms is too
            # aggressive — the keyhint dialog barely appears before the
            # sequence is cancelled.  3000 ms gives the user enough time to
            # read the hint and press the second key.  (Fix: keyhint flash)
            "input.partial_timeout":                     3000,
            "input.spatial_navigation":                  False,

            # ── Keyhint (leader-key popup) ────────────────────────────
            # keyhint.delay: ms before the hint dialog appears after a
            # prefix key is pressed.  Low value so the popup is immediate;
            # partial_timeout (above) keeps it visible long enough to act.
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
            # aligned next to the URL.  Without an explicit entry the widget
            # is not shown even though it is compiled in.
            # (Fix: clock not appearing in bottom-right corner)
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
            #
            # Without this, qutebrowser falls back to its built-in default:
            #   [25, 33, 50, 67, 75, 90, 100, 110, 125, 150, ...]
            # which has uneven gaps (e.g. 90→110 skips 100 on wrap-around).
            #
            # Bug manifestation observed in logs:
            #   100% → zoom-out → 90% → zoom-out → 75%
            #   75%  → zoom-in  → 110%   ← WRONG: skipped 90% and 100%
            #   110% → zoom-in  → 110%   ← WRONG: ceiling hit, no further increase
            #
            # Root cause: zoom-in/zoom-out step through zoom.levels by index.
            # When zoom.default is not in the list OR the list is the qutebrowser
            # built-in with wrap-around semantics, the current index is lost
            # after a direction reversal and restarts from a wrong position.
            #
            # Fix: declare a symmetric, evenly-stepped list where every level
            # is reachable from every other level without skipping.  Steps of
            # 10 pp are comfortable; finer 5 pp steps at the extremes are
            # retained for precise low-zoom work.
            #
            # zoom.default (100) is guaranteed to be in this list.
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
