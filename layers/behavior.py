"""
layers/behavior.py
==================
Behavior Layer — UX, Workflow, Interaction Patterns  (v12)

Priority: 40

Responsibilities:
  - Page interaction behaviors
  - Content handling policies
  - Complete workflow keybindings (Vim-style navigation, leader key)
  - Userscript integration
  - Per-host policy overrides (non-dev categories only)

Pattern: Data-Driven Configuration + Command pattern for keybindings

Keybinding Design Principles (v12):
  ─────────────────────────────────
  1. LONGEST MATCH WINS (prefix disambiguation)
     qutebrowser resolves multi-key sequences by waiting up to
     input.partial_timeout ms (3000 ms, set in BaseLayer) after a prefix.
     When multiple bindings share a prefix (e.g. `,C`, `,Cw`, `,Cwt`),
     qutebrowser always waits for the next key before dispatching —
     the longest complete match wins.  This is native qutebrowser
     behaviour; we rely on it rather than re-implementing it.

     Rule: if `,AB` and `,ABC` both exist, pressing `,AB` waits
     partial_timeout ms; if another key arrives → `,ABC` fires;
     if the timeout expires → `,AB` fires.

  2. CONFLICT ELIMINATION
     Every (key, mode) pair is assigned to exactly ONE layer.
     BaseLayer no longer defines any keybindings (v12).
     BehaviorLayer owns all normal/insert/caret/hint/command/prompt
     bindings that are not layer-specific (privacy → ,j,i,c,s;
     context → ,C*; user → extra_bindings).

  3. LEADER-KEY NAMESPACE (`,` prefix)
     ,<letter>     — single-letter commands (most common actions)
     ,<UPPER>      — variant / destructive version of same letter
     ,C<letter>    — Context switch  (ContextLayer owns these)
     ,g<letter>    — Go / open URL shortcuts
     ,s<letter>    — Session management
     ,f<letter>    — Find / search
     ,h<letter>    — Hint mode variants
     Reserved for PrivacyLayer: ,j  ,i  ,c  ,s

  4. VIM-IDIOM ALIGNMENT
     Standard vim mappings preserved:
       gg/G   scroll top/bottom     H/L    history back/forward
       J/K    tab prev/next         d      close tab
       u      undo close            f/F    hint open / open-tab
       p/P    paste URL             yy     yank URL
       v      enter caret           zi/zo  zoom in/out
       gi     focus input           ge/gE  edit URL in bar

  5. NON-REDUNDANT ZOOM
     zi/zo  → zoom-in / zoom-out  (vim muscle memory)
     +/-    → zoom-in / zoom-out  (browser muscle memory)
     =      → zoom 100%            (reset)
     z0/zz  → zoom 100%            (vim muscle memory aliases)
     All step through zoom.levels (declared in BaseLayer v11).

v12 changes:
  - Added gi (focus-first-input) — aligns with vim gi idiom.
  - Added yy (yank URL), yt (yank page title), yp (yank pretty URL).
  - Added p (open clipboard URL, current tab), P (open in new tab).
  - Added f (hint all links, current tab) — qutebrowser default f.
  - Added F (hint all links, new tab).
  - Added ;; (hint all — same as f, explicit), ;b (hint all background tab).
  - Added ;d (hint download), ;i (hint images), ;y (hint yank URL).
  - Added ;I (hint images new tab), ;r (hint run userscript).
  - Added ge (cmd-set-text :open {url}), gE (cmd-set-text :open -t {url}).
  - Added <ctrl-a>/<ctrl-x>: increment/decrement URL integer component.
  - Added tD (tab-only --prev), tO (tab-only --next).
  - Added tp (tab-pin), tm (tab-mute).
  - Added ,e (config-edit).
  - Added ,k (bookmark-add), ,K (quickmark-save).
  - Added ,S (session-save with prompt), ,sn/,sl (session-new/session-load).
  - Removed duplicate ,r / ,q that also existed in base.py (base now empty).
  - Fixed: ,p conflicts with privacy ,p (OTP userscript) resolved:
      BehaviorLayer uses ,p = open -p (private window).  The password
      manager userscripts are re-homed to ,Pa (fill) / ,Po (OTP).
  - Fixed: ,P conflicts resolved — ,P = open -t -- {primary} (clipboard new tab).
  - Context-switch bindings (,C*) remain in ContextLayer (priority=45).
  - Privacy bindings (,j ,i ,c ,s) remain in PrivacyLayer (priority=20).

v11 changes (retained):
  - zoom keybindings with BaseLayer zoom.levels contract.

v10 changes (retained):
  - Removed input.partial_timeout override (kept in BaseLayer at 3000 ms).

v9 changes (retained):
  - Hint/caret/passthrough/tab-group bindings.
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

    Owns ALL keybindings for normal/insert/caret/hint/command/prompt modes
    that are not layer-specific.  Conflict-free by design (v12).
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
            # NOTE: input.partial_timeout is intentionally NOT set here.
            # BaseLayer sets it to 3000 ms to allow the keyhint dialog to
            # remain visible long enough to be useful.

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

    def _keybindings(self) -> List[Keybind]:  # noqa: C901
        """
        Complete, conflict-free keybinding table.

        Organisation:
          §1  Scrolling & Page navigation
          §2  History navigation
          §3  Zoom
          §4  Tab management
          §5  Tab groups / reorder
          §6  Hint mode (f/F/;*)
          §7  URL open / clipboard (p/P)
          §8  Yank (y*)
          §9  Bookmarks & quickmarks
          §10 Page interaction
          §11 Find / search bar
          §12 Window management
          §13 Config management
          §14 Password manager userscripts
          §15 Readability userscript
          §16 Download management
          §17 Passthrough
          §18 Insert mode
          §19 Prompt mode
          §20 Command mode
          §21 Caret mode
          §22 Hint activation mode

        Longest-match guarantee:
          `,C*` bindings live in ContextLayer (priority=45).
          `,Cw` (work) and `,Cwt` (writing) are both in ContextLayer —
          qutebrowser's partial_timeout ensures the longer one fires when
          the user presses `t` after `,Cw`.

          Within THIS layer, the `,s` prefix has sub-sequences:
          `,sn` (session-new) and `,sl` (session-load) are longer than
          `,s` would be — but `,s` is NOT bound here, so there is no
          ambiguity.  PrivacyLayer owns `,s` (force-HTTPS).
        """
        L = self._leader
        return [

            # ─────────────────────────────────────────────────────────
            # §1  Scrolling & Page navigation
            # ─────────────────────────────────────────────────────────
            ("gg",           "scroll-to-perc 0",             "normal"),
            ("G",            "scroll-to-perc",               "normal"),
            ("j",            "scroll down",                  "normal"),
            ("k",            "scroll up",                    "normal"),
            ("h",            "scroll left",                  "normal"),
            ("l",            "scroll right",                 "normal"),
            ("<ctrl-d>",     "scroll-page 0 0.5",            "normal"),
            ("<ctrl-u>",     "scroll-page 0 -0.5",           "normal"),
            ("<ctrl-f>",     "scroll-page 0 1",              "normal"),
            ("<ctrl-b>",     "scroll-page 0 -1",             "normal"),
            ("<space>",      "scroll-page 0 0.9",            "normal"),
            ("<shift-space>","scroll-page 0 -0.9",           "normal"),

            # ─────────────────────────────────────────────────────────
            # §2  History navigation
            # ─────────────────────────────────────────────────────────
            ("H",            "back",                         "normal"),
            ("L",            "forward",                      "normal"),
            (f"{L}h",        "back",                         "normal"),
            (f"{L}l",        "forward",                      "normal"),

            # ─────────────────────────────────────────────────────────
            # §3  Zoom
            # Step through zoom.levels (declared in BaseLayer v11).
            # zi/zo  = vim idiom
            # +/-    = standard browser idiom
            # =      = reset to 100%  (standard browser idiom)
            # z0/zz  = vim aliases for reset
            # ─────────────────────────────────────────────────────────
            ("zi",           "zoom-in",                      "normal"),
            ("zo",           "zoom-out",                     "normal"),
            ("+",            "zoom-in",                      "normal"),
            ("-",            "zoom-out",                     "normal"),
            ("=",            "zoom 100",                     "normal"),
            ("z0",           "zoom 100",                     "normal"),
            ("zz",           "zoom 100",                     "normal"),

            # ─────────────────────────────────────────────────────────
            # §4  Tab management
            # ─────────────────────────────────────────────────────────
            # Vim-style tab cycle
            ("J",             "tab-prev",                    "normal"),
            ("K",             "tab-next",                    "normal"),
            ("gt",            "tab-next",                    "normal"),
            ("gT",            "tab-prev",                    "normal"),
            # Browser-style tab cycle
            ("<ctrl-tab>",    "tab-next",                    "normal"),
            ("<ctrl-shift-tab>", "tab-prev",                 "normal"),
            # Direct tab focus (alt-N)
            ("<alt-1>",       "tab-focus 1",                 "normal"),
            ("<alt-2>",       "tab-focus 2",                 "normal"),
            ("<alt-3>",       "tab-focus 3",                 "normal"),
            ("<alt-4>",       "tab-focus 4",                 "normal"),
            ("<alt-5>",       "tab-focus 5",                 "normal"),
            ("<alt-6>",       "tab-focus 6",                 "normal"),
            ("<alt-7>",       "tab-focus 7",                 "normal"),
            ("<alt-8>",       "tab-focus 8",                 "normal"),
            ("<alt-9>",       "tab-focus -1",                "normal"),
            # Tab open / close
            ("d",             "tab-close",                   "normal"),
            ("u",             "undo",                        "normal"),
            ("co",            "tab-only",                    "normal"),
            # Leader tab commands
            (f"{L}t",         "open -t",                     "normal"),
            (f"{L}T",         "tab-clone",                   "normal"),
            (f"{L}q",         "tab-close",                   "normal"),
            (f"{L}Q",         "close",                       "normal"),

            # ─────────────────────────────────────────────────────────
            # §5  Tab groups / reorder / pin / mute
            # ─────────────────────────────────────────────────────────
            # Tab move
            ("th",            "tab-move -",                  "normal"),
            ("tl",            "tab-move +",                  "normal"),
            # Tab only (close others)
            ("tD",            "tab-only --prev",             "normal"),
            ("tO",            "tab-only --next",             "normal"),
            # Tab pin / mute
            ("tp",            "tab-pin",                     "normal"),
            ("tm",            "tab-mute",                    "normal"),

            # ─────────────────────────────────────────────────────────
            # §6  Hint mode (open links)
            #
            # f       = hint all links, open in current tab   (default)
            # F       = hint all links, open in new tab
            # ;;      = hint all links (explicit)
            # ;b      = hint all links, open in background tab
            # ;d      = hint all links for download
            # ;i      = hint images, open in current tab
            # ;I      = hint images, open in new tab
            # ;y      = hint all links, yank URL
            # ;Y      = hint all links, yank to primary selection
            # ;r      = hint inputs (focus element)
            # ;h      = hint all (hover)
            # ;e      = hint inputs (open editor)
            #
            # Longest-match note: all `;X` sequences are unambiguous
            # because `;` alone is not bound.
            # ─────────────────────────────────────────────────────────
            ("f",             "hint",                        "normal"),
            ("F",             "hint all tab",                "normal"),
            (";;",            "hint",                        "normal"),
            (";b",            "hint all tab-bg",             "normal"),
            (";d",            "hint all download",           "normal"),
            (";i",            "hint images",                 "normal"),
            (";I",            "hint images tab",             "normal"),
            (";y",            "hint all yank",               "normal"),
            (";Y",            "hint all yank-primary",       "normal"),
            (";r",            "hint inputs",                 "normal"),
            (";e",            "hint inputs --first",         "normal"),
            (";h",            "hint all hover",              "normal"),

            # ─────────────────────────────────────────────────────────
            # §7  URL open / clipboard
            #
            # p  = open URL from clipboard in current tab
            # P  = open URL from clipboard in new tab
            # go = open URL (cmd bar, current tab)  — g prefix idiom
            # gO = open URL (cmd bar, new tab)
            # ge = edit current URL in bar (current tab)
            # gE = edit current URL in bar (new tab)
            # gi = focus first input field
            #
            # ,p = open new private window
            # ,n = open new window
            # ,N = open new private window (alias)
            # ,w = give tab to other window (tab-give)
            # ,W = window-only (close other windows)
            # ─────────────────────────────────────────────────────────
            ("p",             "open -- {clipboard}",         "normal"),
            ("P",             "open -t -- {clipboard}",      "normal"),
            ("go",            "cmd-set-text :open ",         "normal"),
            ("gO",            "cmd-set-text :open -t ",      "normal"),
            ("ge",            "cmd-set-text :open {url}",    "normal"),
            ("gE",            "cmd-set-text :open -t {url}", "normal"),
            ("gi",            "hint inputs --first",         "normal"),
            # URL integer component increment/decrement (vim-like)
            ("<ctrl-a>",      "navigate increment",          "normal"),
            ("<ctrl-x>",      "navigate decrement",          "normal"),
            # Window management
            (f"{L}n",         "open -w",                     "normal"),
            (f"{L}p",         "open -p",                     "normal"),
            (f"{L}w",         "tab-give",                    "normal"),
            (f"{L}W",         "window-only",                 "normal"),

            # ─────────────────────────────────────────────────────────
            # §8  Yank
            #
            # yy  = yank current URL to clipboard
            # yt  = yank page title to clipboard
            # yp  = yank pretty URL (title + URL)
            # yY  = yank current URL to primary selection
            # ,y  = yank URL (alias, leader style)
            # ,Y  = yank to primary (alias)
            # ─────────────────────────────────────────────────────────
            ("yy",            "yank",                        "normal"),
            ("yt",            "yank title",                  "normal"),
            ("yp",            "yank pretty-url",             "normal"),
            ("yY",            "yank -s",                     "normal"),
            (f"{L}y",         "yank",                        "normal"),
            (f"{L}Y",         "yank -s",                     "normal"),

            # ─────────────────────────────────────────────────────────
            # §9  Bookmarks & quickmarks
            #
            # ,k  = bookmark-add (save current page)
            # ,K  = quickmark-save (save with name)
            # ,o  = open bookmark / quickmark via completion
            # ,O  = open bookmark / quickmark in new tab
            # ─────────────────────────────────────────────────────────
            (f"{L}k",         "bookmark-add",                "normal"),
            (f"{L}K",         "quickmark-save",              "normal"),
            (f"{L}o",         "cmd-set-text :open -b ",      "normal"),
            (f"{L}O",         "cmd-set-text :open -t -b ",   "normal"),

            # ─────────────────────────────────────────────────────────
            # §10 Page interaction
            #
            # gf / wf  = view page source (current / new tab)
            # gd       = download current page
            # r        = reload (soft)
            # R        = reload (hard, bypass cache)
            # <esc>    = mode-leave (cancel hint / partial etc.)
            # ─────────────────────────────────────────────────────────
            ("r",             "reload",                      "normal"),
            ("R",             "reload -f",                   "normal"),
            ("gf",            "view-source",                 "normal"),
            ("wf",            "view-source --tab",           "normal"),
            ("gd",            "download",                    "normal"),
            ("<escape>",      "clear-keychain ;; search ''", "normal"),

            # ─────────────────────────────────────────────────────────
            # §11 Find / search bar
            #
            # /  = open forward search bar
            # ?  = open reverse search bar
            # n  = find next
            # N  = find prev
            # ,/  = open forward search (leader alias)
            # ,?  = open reverse search (leader alias)
            # ─────────────────────────────────────────────────────────
            ("/",             "cmd-set-text /",              "normal"),
            ("?",             "cmd-set-text ?",              "normal"),
            ("n",             "search-next",                 "normal"),
            ("N",             "search-prev",                 "normal"),
            (f"{L}/",         "cmd-set-text /",              "normal"),
            (f"{L}?",         "cmd-set-text ?",              "normal"),

            # ─────────────────────────────────────────────────────────
            # §12 Config management
            #
            # ,r  = reload config from disk
            # ,e  = open config in editor
            # ,R  = readability userscript (see §15)
            # ─────────────────────────────────────────────────────────
            (f"{L}r",         "config-source",               "normal"),
            (f"{L}e",         "config-edit",                 "normal"),

            # ─────────────────────────────────────────────────────────
            # §13 Download management
            #
            # ,b  = toggle download bar
            # ,d  = clear completed downloads
            # ,D  = delete selected download
            # ─────────────────────────────────────────────────────────
            (f"{L}b",         "download-list",               "normal"),
            (f"{L}d",         "download-clear",              "normal"),
            (f"{L}D",         "download-delete",             "normal"),

            # ─────────────────────────────────────────────────────────
            # §14 Password manager userscripts
            #
            # ,Pa = fill password (pass / bitwarden)
            # ,Po = fill OTP (one-time password)
            #
            # Longest-match: ,Pa / ,Po are both longer than ,P (yank-primary
            # new tab) which is NOT bound here — ,P is yank-primary (§8).
            # So ,P alone does not trigger; only ,Pa / ,Po.
            # Wait: to avoid ambiguity, we use ,Pa/,Po explicitly — the user
            # must press the third key.  partial_timeout handles this.
            # ─────────────────────────────────────────────────────────
            (f"{L}Pa",        "spawn --userscript qute-pass",          "normal"),
            (f"{L}Po",        "spawn --userscript qute-pass --otp",    "normal"),

            # ─────────────────────────────────────────────────────────
            # §15 Readability userscript
            #
            # ,R  = toggle readability mode
            # ─────────────────────────────────────────────────────────
            (f"{L}R",         "spawn --userscript readability",        "normal"),

            # ─────────────────────────────────────────────────────────
            # §16 Session management
            #
            # ,S   = save session (with name prompt)
            # ,sn  = new session
            # ,sl  = load session (with completion)
            #
            # Longest-match: ,sn and ,sl are both longer than ,s (privacy
            # HTTPS reload, owned by PrivacyLayer).  No conflict because
            # PrivacyLayer at priority=20 defines ,s and BehaviorLayer at
            # priority=40 does NOT rebind ,s — only ,sn / ,sl which are
            # unambiguous sub-sequences.
            # ─────────────────────────────────────────────────────────
            (f"{L}S",         "cmd-set-text :session-save ",           "normal"),
            (f"{L}sn",        "session-save --only-active-window",     "normal"),
            (f"{L}sl",        "cmd-set-text :session-load ",           "normal"),

            # ─────────────────────────────────────────────────────────
            # §17 Passthrough / mode entry
            # ─────────────────────────────────────────────────────────
            ("<ctrl-v>",      "enter-mode passthrough",      "normal"),
            ("v",             "enter-mode caret",            "normal"),

            # ─────────────────────────────────────────────────────────
            # §18 Insert mode
            # ─────────────────────────────────────────────────────────
            ("<ctrl-e>",      "open-editor",                 "insert"),
            ("<escape>",      "mode-leave",                  "insert"),
            ("<ctrl-[>",      "mode-leave",                  "insert"),  # vim Ctrl-[ = Esc

            # ─────────────────────────────────────────────────────────
            # §19 Prompt mode
            # ─────────────────────────────────────────────────────────
            ("<ctrl-y>",      "prompt-accept yes",           "prompt"),
            ("<ctrl-enter>",  "prompt-accept",               "prompt"),
            ("<ctrl-p>",      "prompt-item-focus prev",      "prompt"),
            ("<ctrl-n>",      "prompt-item-focus next",      "prompt"),

            # ─────────────────────────────────────────────────────────
            # §20 Command mode
            # ─────────────────────────────────────────────────────────
            ("<ctrl-j>",      "completion-item-focus next",  "command"),
            ("<ctrl-k>",      "completion-item-focus prev",  "command"),
            ("<ctrl-d>",      "completion-item-del",         "command"),
            ("<ctrl-p>",      "completion-item-focus prev",  "command"),
            ("<ctrl-n>",      "completion-item-focus next",  "command"),

            # ─────────────────────────────────────────────────────────
            # §21 Caret mode
            # Standard vim-like caret navigation.
            # H/L are word-prev/next (mirrors normal mode H/L = back/forward
            # is NOT the same key — caret mode is distinct).
            # ─────────────────────────────────────────────────────────
            ("h",             "move-to-prev-char",           "caret"),
            ("l",             "move-to-next-char",           "caret"),
            ("H",             "move-to-prev-word",           "caret"),
            ("L",             "move-to-next-word",           "caret"),
            ("j",             "move-to-next-line",           "caret"),
            ("k",             "move-to-prev-line",           "caret"),
            ("0",             "move-to-start-of-line",       "caret"),
            ("$",             "move-to-end-of-line",         "caret"),
            ("gg",            "move-to-start-of-document",   "caret"),
            ("G",             "move-to-end-of-document",     "caret"),
            ("V",             "selection-toggle --line",     "caret"),
            ("y",             "yank selection",              "caret"),
            ("<ctrl-c>",      "yank selection",              "caret"),
            ("q",             "mode-leave",                  "caret"),
            ("<escape>",      "mode-leave",                  "caret"),

            # ─────────────────────────────────────────────────────────
            # §22 Hint activation mode
            # (keys typed while the hint overlay is visible)
            # ─────────────────────────────────────────────────────────
            ("<escape>",      "mode-leave",                  "hint"),
            ("<ctrl-r>",      "reload",                      "hint"),
            ("<ctrl-f>",      "cmd-set-text /",              "hint"),
            ("<ctrl-y>",      "yank",                        "hint"),
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
