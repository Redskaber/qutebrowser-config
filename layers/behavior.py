"""
layers/behavior.py
==================
Behavior Layer — UX, Workflow, Interaction Patterns  (v19)

Priority: 40

Responsibilities:
  - Page interaction behaviors
  - Content handling policies
  - Complete workflow keybindings (Vim-style navigation, leader key)
  - Userscript integration
  - Per-host policy overrides (non-dev categories only)

Pattern: Data-Driven Configuration + Command pattern for keybindings

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Keybinding Design Principles (v18)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

1. CROSS-LAYER PREFIX ISOLATION  ← the cardinal rule (v18)
   qutebrowser merges ALL layers into ONE flat key table.
   Once a key sequence is registered as a TERMINAL (fires a command),
   qutebrowser will NOT wait for additional keys — even if a longer
   sequence exists from a different layer.

   Ownership table (hard contracts):
     PrivacyLayer[20]  → ,j  ,i  ,c  ,s   (exactly these four)
     NetworkLayer[27]  → ,N*              (,Nn ,Ns ,N5 ,Nh ,Nt ,Ni)
     BehaviorLayer[40] → all other ,*     (see §7 for ,p/,pp/,po)
     ContextLayer[45]  → ,C*              (,Cd ,Cw ,Cwt ,Cr ,Cm ,Cg ,C0 ,Ci)
     SessionLayer[55]  → ,S*              (,Sd ,Se ,Sn ,Sf ,Sc ,Sp ,S0 ,Si)
     UserLayer[90]     → extra_bindings   (overrides via priority)

   BehaviorLayer has ZERO ,s* bindings and ZERO ,S* bindings.

2. LONGEST-MATCH WITHIN A SINGLE LAYER (safe)
   When BehaviorLayer registers ,p and ,pp/,po together,
   partial_timeout resolves correctly (all in same layer):
     ,p alone (timeout) → open -p   ,pp → qute-pass   ,po → qute-pass --otp

3. VIM-IDIOM ALIGNMENT
   gg/G=scroll top/bottom  H/L=history back/fwd  J/K=tab prev/next
   d=close tab  u=undo  f/F=hint  p/P=clipboard  yy=yank url
   v=caret  zi/zo=zoom  gi=focus input  ge/gE=edit URL

4. STATUS-BAR FEEDBACK
   Actions with no visible page effect emit message-info.
   Pattern: "actual-command ;; message-info 'text'"

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Changelog
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

v19:
  [FIX] enter-mode → mode-enter (correct qutebrowser command; enter-mode
        caused "no such command" ERROR for <ctrl-v> and v keybindings).

v18 (retained):
  [FIX] hints.find_implementation removed (QtWebEngine does not support it).
  [FIX] download-list (invalid cmd) → cmd-set-text :download
  [FIX] ,sn/,sl and ,S*/,Sn/,Sl COMPLETELY REMOVED. SessionLayer[55]
        exclusively owns ,S*. Any ,S* here would cross-layer conflict.
  [FIX] ,Pa/,Po → ,pp/,po (capital-P shift-modifier ambiguity with P binding).
  [ADD] message-info feedback on ,r (config reload).
  [ADD] ,pp/,po defined here as qute-pass defaults; UserLayer[90] can override.

v12–v17 (retained):
  gi, yy/yt/yp, p/P clipboard, f/F hints, ;;/;b/;d/;i/;I/;y/;Y/;r/;e/;h,
  ge/gE URL edit, <ctrl-a>/<ctrl-x> URL increment, tD/tO tab-only,
  tp/tm tab-pin/mute, ,e config-edit, ,k bookmark-add, ,K quickmark-save.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List

from core.types import ConfigDict, Keybind
from core.layer import BaseConfigLayer


# ─────────────────────────────────────────────────────────────────────────────
# Per-Host Policy
# ─────────────────────────────────────────────────────────────────────────────

@dataclass(frozen=True)
class HostPolicy:
    """
    Declarative per-host configuration override.
    Applied via config.set(..., pattern=host_pattern).
    Frozen so instances can be used as dict keys or in sets.

    Dev/localhost rules live in policies/host.py (HOST_POLICY_DEV flag).
    """
    pattern:     str
    settings:    Dict[str, Any] = field(default_factory=dict[str, Any], compare=False)
    description: str            = ""
    category:    str            = "general"


# ─────────────────────────────────────────────────────────────────────────────
# Behavior Layer
# ─────────────────────────────────────────────────────────────────────────────

class BehaviorLayer(BaseConfigLayer):
    """
    UX behavior configuration layer (priority=40).

    Owns all keybindings for normal/insert/caret/hint/command/prompt modes
    that are not explicitly owned by another layer.
    See module docstring Principle #1 for the full ownership contract.
    """

    name        = "behavior"
    priority    = 40
    description = "UX behaviors, workflow bindings, per-host overrides"

    def __init__(self, leader: str = ",") -> None:
        self._leader = leader

    def _settings(self) -> ConfigDict:
        return {
            # ── Tabs ──────────────────────────────────────────────────────────
            "tabs.background":                True,
            "tabs.last_close":                "startpage",
            "tabs.mousewheel_switching":      False,
            "tabs.close_mouse_button":        "middle",
            "tabs.close_mouse_button_on_bar": "new-tab",
            "tabs.select_on_remove":          "prev",

            # ── Motion ────────────────────────────────────────────────────────
            "content.prefers_reduced_motion": True,

            # ── Scrolling ─────────────────────────────────────────────────────
            "scrolling.smooth": False,
            "scrolling.bar":    "overlay",

            # ── Load / startup ────────────────────────────────────────────────
            "url.start_pages":      ["about:blank"],
            "session.lazy_restore": True,

            # ── Auto-save session ─────────────────────────────────────────────
            "auto_save.session":  True,
            "auto_save.interval": 15000,

            # ── Hints ─────────────────────────────────────────────────────────
            # hints.find_implementation intentionally OMITTED:
            # Not available with QtWebEngine; setting it causes ERROR on reload.
            "hints.auto_follow":         "unique-match",
            "hints.auto_follow_timeout": 0,
            "hints.mode":                "letter",
            "hints.uppercase":           False,
            "hints.scatter":             True,
            "hints.padding":             {"top": 1, "bottom": 1, "left": 3, "right": 3},
            "hints.border":              "1px solid #89b4fa",
            "hints.radius":              3,

            # ── Content security ──────────────────────────────────────────────
            "content.local_content_can_access_file_urls":   False,
            "content.local_content_can_access_remote_urls": False,
            "content.geolocation":                          False,
            "content.notifications.enabled":                False,

            # ── Input ─────────────────────────────────────────────────────────
            "input.escape_quits_reporter": True,
            # input.partial_timeout set in BaseLayer (3000 ms) — do not override.

            # ── Completion ────────────────────────────────────────────────────
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

        Namespace contracts enforced (NO bindings for these prefixes here):
          ,s* → PrivacyLayer    ,S* → SessionLayer
          ,N* → NetworkLayer    ,C* → ContextLayer
          ,j ,i ,c → PrivacyLayer
        """
        L = self._leader
        return [

            # ═══════════════════════════════════════════════════════════
            # §1  Scrolling & page navigation
            # ═══════════════════════════════════════════════════════════
            ("gg",            "scroll-to-perc 0",            "normal"),
            ("G",             "scroll-to-perc",              "normal"),
            ("j",             "scroll down",                 "normal"),
            ("k",             "scroll up",                   "normal"),
            ("h",             "scroll left",                 "normal"),
            ("l",             "scroll right",                "normal"),
            ("<ctrl-d>",      "scroll-page 0 0.5",           "normal"),
            ("<ctrl-u>",      "scroll-page 0 -0.5",          "normal"),
            ("<ctrl-f>",      "scroll-page 0 1",             "normal"),
            ("<ctrl-b>",      "scroll-page 0 -1",            "normal"),
            ("<space>",       "scroll-page 0 0.9",           "normal"),
            ("<shift-space>", "scroll-page 0 -0.9",          "normal"),

            # ═══════════════════════════════════════════════════════════
            # §2  History navigation
            # ═══════════════════════════════════════════════════════════
            ("H",             "back",                        "normal"),
            ("L",             "forward",                     "normal"),
            (f"{L}h",         "back",                        "normal"),
            (f"{L}l",         "forward",                     "normal"),

            # ═══════════════════════════════════════════════════════════
            # §3  Zoom
            # zi/zo=vim  +/-=browser  =/z0/zz=reset(100%)
            # ═══════════════════════════════════════════════════════════
            ("zi",            "zoom-in",                     "normal"),
            ("zo",            "zoom-out",                    "normal"),
            ("+",             "zoom-in",                     "normal"),
            ("-",             "zoom-out",                    "normal"),
            ("=",             "zoom 100",                    "normal"),
            ("z0",            "zoom 100",                    "normal"),
            ("zz",            "zoom 100",                    "normal"),

            # ═══════════════════════════════════════════════════════════
            # §4  Tab management
            # ═══════════════════════════════════════════════════════════
            ("J",                "tab-prev",                 "normal"),
            ("K",                "tab-next",                 "normal"),
            ("gt",               "tab-next",                 "normal"),
            ("gT",               "tab-prev",                 "normal"),
            ("<ctrl-tab>",       "tab-next",                 "normal"),
            ("<ctrl-shift-tab>", "tab-prev",                 "normal"),
            ("<alt-1>",          "tab-focus 1",              "normal"),
            ("<alt-2>",          "tab-focus 2",              "normal"),
            ("<alt-3>",          "tab-focus 3",              "normal"),
            ("<alt-4>",          "tab-focus 4",              "normal"),
            ("<alt-5>",          "tab-focus 5",              "normal"),
            ("<alt-6>",          "tab-focus 6",              "normal"),
            ("<alt-7>",          "tab-focus 7",              "normal"),
            ("<alt-8>",          "tab-focus 8",              "normal"),
            ("<alt-9>",          "tab-focus -1",             "normal"),
            ("d",                "tab-close",                "normal"),
            ("u",                "undo",                     "normal"),
            ("co",               "tab-only",                 "normal"),
            (f"{L}t",            "open -t",                  "normal"),
            (f"{L}T",            "tab-clone",                "normal"),
            (f"{L}q",            "tab-close",                "normal"),
            (f"{L}Q",            "close",                    "normal"),

            # ═══════════════════════════════════════════════════════════
            # §5  Tab groups / reorder / pin / mute
            # ═══════════════════════════════════════════════════════════
            ("th",            "tab-move -",                  "normal"),
            ("tl",            "tab-move +",                  "normal"),
            ("tD",            "tab-only --prev",             "normal"),
            ("tO",            "tab-only --next",             "normal"),
            ("tp",            "tab-pin",                     "normal"),
            ("tm",            "tab-mute",                    "normal"),

            # ═══════════════════════════════════════════════════════════
            # §6  Hint mode
            # f=current  F=new-tab  ;;=all  ;b=bg  ;d=dl  ;i=img
            # ;I=img-tab  ;y=yank  ;Y=yank-primary  ;r=input  ;e=editor
            # ;h=hover
            # Longest-match: all ;X are unambiguous (bare ; is unbound).
            # ═══════════════════════════════════════════════════════════
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

            # ═══════════════════════════════════════════════════════════
            # §7  URL open / clipboard / window management
            #
            # p    = open clipboard → current tab
            # P    = open clipboard → new tab
            # go   = open URL (cmd bar, current tab)
            # gO   = open URL (cmd bar, new tab)
            # ge   = edit URL (current tab)
            # gE   = edit URL (new tab)
            # gi   = focus first input field
            #
            # ,n   = new window
            # ,p   = new PRIVATE window   ← terminal; prefix of ,pp/,po
            # ,pp  = password fill        ← sub-seq of ,p (longest-match)
            # ,po  = OTP fill             ← sub-seq of ,p (longest-match)
            # ,w   = give tab to other window
            # ,W   = close other windows
            #
            # ,p / ,pp / ,po are ALL in BehaviorLayer → single-layer
            # longest-match is safe. qutebrowser waits partial_timeout
            # (3 s) after ,p; if pp or po follows → fires that binding.
            # UserLayer[90] overrides ,pp/,po if password.py is preferred.
            # ═══════════════════════════════════════════════════════════
            ("p",             "open -- {clipboard}",         "normal"),
            ("P",             "open -t -- {clipboard}",      "normal"),
            ("go",            "cmd-set-text :open ",         "normal"),
            ("gO",            "cmd-set-text :open -t ",      "normal"),
            ("ge",            "cmd-set-text :open {url}",    "normal"),
            ("gE",            "cmd-set-text :open -t {url}", "normal"),
            ("gi",            "hint inputs --first",         "normal"),
            ("<ctrl-a>",      "navigate increment",          "normal"),
            ("<ctrl-x>",      "navigate decrement",          "normal"),
            (f"{L}n",         "open -w",                     "normal"),
            (f"{L}p",         "open -p",                     "normal"),
            (f"{L}pp",        "spawn --userscript qute-pass",          "normal"),
            (f"{L}po",        "spawn --userscript qute-pass --otp",    "normal"),
            (f"{L}w",         "tab-give",                    "normal"),
            (f"{L}W",         "window-only",                 "normal"),

            # ═══════════════════════════════════════════════════════════
            # §8  Yank
            # yy=url  yt=title  yp=pretty  yY=primary  ,y=url  ,Y=primary
            # ═══════════════════════════════════════════════════════════
            ("yy",            "yank",                        "normal"),
            ("yt",            "yank title",                  "normal"),
            ("yp",            "yank pretty-url",             "normal"),
            ("yY",            "yank -s",                     "normal"),
            (f"{L}y",         "yank",                        "normal"),
            (f"{L}Y",         "yank -s",                     "normal"),

            # ═══════════════════════════════════════════════════════════
            # §9  Bookmarks & quickmarks
            # ,k=add  ,K=quickmark-save  ,o=open(bg)  ,O=open(new-tab)
            # ═══════════════════════════════════════════════════════════
            (f"{L}k",         "bookmark-add",                "normal"),
            (f"{L}K",         "quickmark-save",              "normal"),
            (f"{L}o",         "cmd-set-text :open -b ",      "normal"),
            (f"{L}O",         "cmd-set-text :open -t -b ",   "normal"),

            # ═══════════════════════════════════════════════════════════
            # §10 Page interaction
            # r=reload  R=hard-reload  gf=source  wf=source(tab)
            # gd=download  <esc>=cancel/clear
            # ═══════════════════════════════════════════════════════════
            ("r",             "reload",                      "normal"),
            ("R",             "reload -f",                   "normal"),
            ("gf",            "view-source",                 "normal"),
            ("wf",            "view-source --tab",           "normal"),
            ("gd",            "download",                    "normal"),
            ("<escape>",      "clear-keychain ;; search ''", "normal"),

            # ═══════════════════════════════════════════════════════════
            # §11 Find / search bar
            # / ? n N — standard vi bindings
            # ,/ ,?   — leader aliases (UserLayer may override ,/)
            # ═══════════════════════════════════════════════════════════
            ("/",             "cmd-set-text /",              "normal"),
            ("?",             "cmd-set-text ?",              "normal"),
            ("n",             "search-next",                 "normal"),
            ("N",             "search-prev",                 "normal"),
            (f"{L}/",         "cmd-set-text /",              "normal"),
            (f"{L}?",         "cmd-set-text ?",              "normal"),

            # ═══════════════════════════════════════════════════════════
            # §12 Config management
            # ,r = reload (with status-bar feedback)
            # ,e = open config.py in $EDITOR
            # ═══════════════════════════════════════════════════════════
            (f"{L}r",  "config-source ;; message-info 'Config reloaded ✓'",  "normal"),
            (f"{L}e",  "config-edit",                                          "normal"),

            # ═══════════════════════════════════════════════════════════
            # §13 Download management
            # ,b = open download cmd bar   ,d = clear done   ,D = delete
            # NOTE: no "download-list" command exists in qutebrowser.
            # ═══════════════════════════════════════════════════════════
            (f"{L}b",         "cmd-set-text :download ",     "normal"),
            (f"{L}d",         "download-clear",              "normal"),
            (f"{L}D",         "download-delete",             "normal"),

            # ═══════════════════════════════════════════════════════════
            # §14 Password manager (qute-pass defaults)
            # UserLayer[90] overrides these with password.py if configured.
            # See §7 comment for longest-match explanation.
            # ═══════════════════════════════════════════════════════════
            # (already registered in §7 alongside ,p — listed there for
            # clarity; the entries above in §7 are the canonical location)

            # ═══════════════════════════════════════════════════════════
            # §15 Readability userscript
            # ═══════════════════════════════════════════════════════════
            (f"{L}R",         "spawn --userscript readability",        "normal"),

            # ═══════════════════════════════════════════════════════════
            # §16 [RESERVED] Session management
            # BehaviorLayer registers NO ,S* bindings.
            # SessionLayer[55] owns ,S* exclusively.
            # Session persistence: :w (session-save)  :wq (quit --save)
            # ═══════════════════════════════════════════════════════════

            # ═══════════════════════════════════════════════════════════
            # §17 Passthrough / mode entry
            # ═══════════════════════════════════════════════════════════
            ("<ctrl-v>",      "mode-enter passthrough",      "normal"),
            ("v",             "mode-enter caret",            "normal"),

            # ═══════════════════════════════════════════════════════════
            # §18 Insert mode
            # ═══════════════════════════════════════════════════════════
            ("<ctrl-e>",      "open-editor",                 "insert"),
            ("<escape>",      "mode-leave",                  "insert"),
            ("<ctrl-[>",      "mode-leave",                  "insert"),

            # ═══════════════════════════════════════════════════════════
            # §19 Prompt mode
            # ═══════════════════════════════════════════════════════════
            ("<ctrl-y>",      "prompt-accept yes",           "prompt"),
            ("<ctrl-enter>",  "prompt-accept",               "prompt"),
            ("<ctrl-p>",      "prompt-item-focus prev",      "prompt"),
            ("<ctrl-n>",      "prompt-item-focus next",      "prompt"),

            # ═══════════════════════════════════════════════════════════
            # §20 Command mode
            # ═══════════════════════════════════════════════════════════
            ("<ctrl-j>",      "completion-item-focus next",  "command"),
            ("<ctrl-k>",      "completion-item-focus prev",  "command"),
            ("<ctrl-d>",      "completion-item-del",         "command"),
            ("<ctrl-p>",      "completion-item-focus prev",  "command"),
            ("<ctrl-n>",      "completion-item-focus next",  "command"),

            # ═══════════════════════════════════════════════════════════
            # §21 Caret mode (vim-like text selection)
            # H/L here = word-prev/next (not history — that is normal mode)
            # ═══════════════════════════════════════════════════════════
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

            # ═══════════════════════════════════════════════════════════
            # §22 Hint-activation mode
            # ═══════════════════════════════════════════════════════════
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
        Dev/localhost → policies/host.py DEV_RULES.
        Google/GitHub login → policies/host.py LOGIN_RULES.
        Only non-auth behavioral overrides here.
        """
        return [
            HostPolicy(
                pattern="github.com",
                settings={"content.javascript.enabled": True, "content.cookies.accept": "all"},
                description="GitHub requires JavaScript",
                category="dev",
            ),
            HostPolicy(
                pattern="*.github.com",
                settings={"content.javascript.enabled": True, "content.cookies.accept": "all"},
                description="GitHub subdomains (gist, raw, etc.)",
                category="dev",
            ),
            HostPolicy(
                pattern="youtube.com",
                settings={"content.javascript.enabled": True, "content.cookies.accept": "all",
                          "content.autoplay": False},
                description="YouTube: JS on, autoplay off",
                category="media",
            ),
            HostPolicy(
                pattern="*.youtube.com",
                settings={"content.javascript.enabled": True, "content.cookies.accept": "all",
                          "content.autoplay": False},
                description="YouTube subdomains",
                category="media",
            ),
            HostPolicy(
                pattern="bilibili.com",
                settings={"content.javascript.enabled": True, "content.cookies.accept": "all",
                          "content.autoplay": False},
                description="Bilibili: JS on, autoplay off",
                category="media",
            ),
            HostPolicy(
                pattern="*.bilibili.com",
                settings={"content.javascript.enabled": True, "content.cookies.accept": "all"},
                description="Bilibili subdomains (danmaku, etc.)",
                category="media",
            ),
        ]
