"""
layers/user.py
==============
User Layer — Personal Overrides (Highest Priority)

Priority: 90 — applied last; wins over every other layer.

This is your personal escape hatch.  Drop any one-off settings here that
don't belong to a named layer.  Keep it small: if you find yourself adding
many thematically related settings, create a new named layer instead.

Design philosophy:
  - Declarative: settings expressed as dicts, not imperative API calls.
  - Documented: each override carries a comment explaining *why*.
  - Auditable: separated from architecture concerns so diffs are meaningful.

Consistency fix:
  Added the ``leader`` constructor parameter so UserLayer keybindings
  respect the ``LEADER_KEY`` setting in ``config.py``, matching
  BehaviorLayer and PrivacyLayer.
"""

from __future__ import annotations

from typing import Any, Dict, List, Tuple

from core.layer import BaseConfigLayer

ConfigDict = Dict[str, Any]


class UserLayer(BaseConfigLayer):
    """
    Personal overrides — final layer applied.

    Args:
        leader: Leader key prefix (default ``","``).  Used in keybindings so
                custom bindings respect the same leader as built-in layers.

    Edit the methods below freely; this layer is yours.
    """

    name        = "user"
    priority    = 90
    description = "Personal overrides — highest priority"

    def __init__(self, leader: str = ",") -> None:
        self._leader = leader

    def _settings(self) -> ConfigDict:
        return {
            # ── Example: override the terminal used for editor commands ──
            # "editor.command": ["kitty", "-e", "nvim", "{}"],

            # ── Example: override the default start page ────────────────
            # "url.start_pages": ["https://start.duckduckgo.com"],

            # ── Example: bump the default zoom level ────────────────────
            # "zoom.default": "110%",

            # ── NixOS: these are handled by the home-manager module, but
            # included here for reference if you run qutebrowser outside Nix:
            # "qt.environ": {"QTWEBENGINE_CHROMIUM_FLAGS": "--no-sandbox"},
        }

    def _keybindings(self) -> List[Tuple[str, str, str]]:
        # L = self._leader
        return [
            # ── Example: open clipboard URL in new tab ──────────────────
            # ("gx", "open -t -- {clipboard}", "normal"),

            # ── Example: copy page title + URL as Markdown link ─────────
            # (f"{L}M", "yank inline [{title}]({url})", "normal"),
        ]

    def _aliases(self) -> ConfigDict:
        return {
            # ── Example: alias for a frequently used command ────────────
            # "gh": "open -t https://github.com",
        }
