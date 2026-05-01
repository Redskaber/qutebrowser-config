"""
layers/context.py
=================
Context Layer — Situational Browser Modes

Priority: 45  (between behavior[40] and performance[50])

A "context" is a named situation with its own search engines, keybindings,
and behavioral overrides.  Switching contexts is a single-key action:
  ,Cw  → work   (Jira, Confluence, corporate search)
  ,Cr  → research (arXiv, Scholar, Wikipedia-heavy, no distractions)
  ,Cm  → media  (YouTube, Bilibili, autoplay on)
  ,Cd  → dev    (GitHub, npm, MDN, crates, DevDocs)
  ,C0  → reset  (return to default / base context)

Design:
  ContextMode (enum)  — named contexts
  ContextSpec (data)  — per-context settings + engines + bindings delta
  ContextLayer        — resolves active spec into config delta

Architecture integration:
  - ContextLayer reads context from environment (QUTE_CONTEXT env var) or
    defaults to ContextMode.DEFAULT.
  - config.py can pass ACTIVE_CONTEXT to override.
  - All context switching is done via keybindings that spawn a shell command
    setting an env var and reloading: no qutebrowser restart needed.

Patterns: Strategy (context as spec), Data-Driven, State (active context).

Strict-mode: all attrs typed; ContextSpec is frozen dataclass.
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Any, Dict, List, Optional, Tuple

from core.layer import BaseConfigLayer

ConfigDict  = Dict[str, Any]
BindingList = List[Tuple[str, str, str]]
EngineMap   = Dict[str, str]

logger = logging.getLogger("qute.layers.context")


# ─────────────────────────────────────────────
# Context Modes (named situations)
# ─────────────────────────────────────────────
class ContextMode(str, Enum):
    """Named situational modes.  Values are also used as display names."""
    DEFAULT  = "default"
    WORK     = "work"
    RESEARCH = "research"
    MEDIA    = "media"
    DEV      = "dev"


# ─────────────────────────────────────────────
# Context Specification (data)
# ─────────────────────────────────────────────
@dataclass(frozen=True)
class ContextSpec:
    """
    Immutable specification for a single context.

    Attributes:
        mode:           The ContextMode this spec describes.
        description:    Human-readable label.
        search_engines: Engines to *merge* on top of base engines.
                        Set "DEFAULT" to change the primary engine.
        settings_delta: qutebrowser settings to *override* in this context.
        bindings_extra: Additional (key, command, mode) tuples for this context.
    """
    mode:            ContextMode
    description:     str        = ""
    search_engines:  EngineMap  = field(default_factory=dict)
    settings_delta:  ConfigDict = field(default_factory=dict)
    bindings_extra:  BindingList= field(default_factory=list)


# ─────────────────────────────────────────────
# Built-in Context Specs
# ─────────────────────────────────────────────
_CONTEXT_TABLE: Dict[ContextMode, ContextSpec] = {

    ContextMode.DEFAULT: ContextSpec(
        mode=ContextMode.DEFAULT,
        description="General browsing — all defaults active",
        search_engines={},          # no override
        settings_delta={},
        bindings_extra=[],
    ),

    ContextMode.WORK: ContextSpec(
        mode=ContextMode.WORK,
        description="Work mode — corporate tools, focused tab bar",
        search_engines={
            # Override DEFAULT to company search or leave as Brave
            # Add common work platforms
            "jira":  "https://jira.atlassian.com/browse/{}",
            "conf":  "https://www.atlassian.com/software/confluence/search?text={}",
            "gh":    "https://github.com/search?q={}&type=repositories",
            "gl":    "https://gitlab.com/search?search={}",
            "liner": "https://getliner.com/en/search?q={}",
        },
        settings_delta={
            "tabs.show":                  "always",
            "tabs.position":              "top",
            "content.notifications.enabled": False,  # no notification spam
            "content.autoplay":           False,
            "session.lazy_restore":       False,
            "statusbar.widgets": [
                "keypress", "url", "scroll", "history", "tabs", "progress"
            ],
        },
        bindings_extra=[],
    ),

    ContextMode.RESEARCH: ContextSpec(
        mode=ContextMode.RESEARCH,
        description="Research mode — academia search, distraction-free",
        search_engines={
            "DEFAULT":  "https://search.brave.com/search?q={}",
            "arxiv":    "https://arxiv.org/search/?searchtype=all&query={}",
            "scholar":  "https://scholar.google.com/scholar?q={}",
            "pubmed":   "https://pubmed.ncbi.nlm.nih.gov/?term={}",
            "doi":      "https://doi.org/{}",
            "ssrn":     "https://ssrn.com/search?q={}",
            "sem":      "https://www.semanticscholar.org/search?q={}",
            "w":        "https://en.wikipedia.org/w/index.php?search={}",
            "wikt":     "https://en.wiktionary.org/w/index.php?search={}",
        },
        settings_delta={
            "content.autoplay":           False,
            "content.notifications.enabled": False,
            "tabs.show":                  "multiple",
            "statusbar.show":             "in-mode",  # distraction-free
        },
        bindings_extra=[],
    ),

    ContextMode.MEDIA: ContextSpec(
        mode=ContextMode.MEDIA,
        description="Media mode — video/music focused, autoplay allowed",
        search_engines={
            "DEFAULT": "https://www.youtube.com/results?search_query={}",
            "yt":      "https://www.youtube.com/results?search_query={}",
            "bili":    "https://search.bilibili.com/all?keyword={}",
            "twitch":  "https://www.twitch.tv/search?term={}",
            "sp":      "https://open.spotify.com/search/{}",
            "sc":      "https://soundcloud.com/search?q={}",
            "nia":     "https://www.netflix.com/search?q={}",
        },
        settings_delta={
            "content.autoplay":           True,
            "content.mute":               False,
            "content.notifications.enabled": False,
            "tabs.show":                  "multiple",
        },
        bindings_extra=[],
    ),

    ContextMode.DEV: ContextSpec(
        mode=ContextMode.DEV,
        description="Dev mode — code search, docs, package registries",
        search_engines={
            "DEFAULT": "https://github.com/search?q={}&type=repositories",
            "gh":      "https://github.com/search?q={}&type=repositories",
            "gl":      "https://gitlab.com/search?search={}",
            "mdn":     "https://developer.mozilla.org/en-US/search?q={}",
            "docs":    "https://devdocs.io/#q={}",
            "nix":     "https://search.nixos.org/packages?query={}",
            "crates":  "https://crates.io/search?q={}",
            "pypi":    "https://pypi.org/search/?q={}",
            "npm":     "https://www.npmjs.com/search?q={}",
            "dh":      "https://hub.docker.com/search?q={}",
            "rs":      "https://doc.rust-lang.org/std/?search={}",
            "go":      "https://pkg.go.dev/search?q={}",
            "tf":      "https://registry.terraform.io/search/modules?q={}",
            "az":      "https://learn.microsoft.com/en-us/search/?terms={}",
            "so":      "https://stackoverflow.com/search?q={}",
        },
        settings_delta={
            "content.autoplay":           False,
            "content.notifications.enabled": False,
            "tabs.show":                  "always",
            "completion.web_history.max_items": 30,
        },
        bindings_extra=[],
    ),
}


# ─────────────────────────────────────────────
# Context Resolution
# ─────────────────────────────────────────────
def _resolve_active_mode(override: Optional[str]) -> ContextMode:
    """
    Resolve the active ContextMode.

    Priority order:
      1. ``override`` parameter (from config.py ACTIVE_CONTEXT)
      2. QUTE_CONTEXT environment variable
      3. ContextMode.DEFAULT fallback
    """
    raw: Optional[str] = override or os.environ.get("QUTE_CONTEXT")
    if raw is None:
        return ContextMode.DEFAULT

    try:
        return ContextMode(raw.lower())
    except ValueError:
        logger.warning(
            "[ContextLayer] unknown context %r; valid: %s — using default",
            raw,
            [m.value for m in ContextMode],
        )
        return ContextMode.DEFAULT


# ─────────────────────────────────────────────
# Context Layer
# ─────────────────────────────────────────────
class ContextLayer(BaseConfigLayer):
    """
    Situational context layer.

    Injects context-specific search engines, settings, and keybindings.
    Also registers the context-switching keybindings under the leader key.

    Args:
        context:       Active context name (or None → auto-detect from env).
        leader:        Leader key prefix (default ",").
        base_engines:  Engines already established by lower layers.
                       ContextLayer *merges* its engine delta on top.
    """

    name        = "context"
    priority    = 45
    description = "Situational context — work / research / media / dev"

    def __init__(
        self,
        context:      Optional[str]       = None,
        leader:       str                  = ",",
        base_engines: Optional[EngineMap]  = None,
    ) -> None:
        self._mode:         ContextMode = _resolve_active_mode(context)
        self._leader:       str         = leader
        self._base_engines: EngineMap   = dict(base_engines) if base_engines else {}

        spec = _CONTEXT_TABLE.get(self._mode)
        self._spec: ContextSpec = spec if spec is not None else _CONTEXT_TABLE[ContextMode.DEFAULT]

        logger.info(
            "[ContextLayer] active context: %s (%s)",
            self._mode.value, self._spec.description
        )

    # ── Properties ────────────────────────────────────────────────────

    @property
    def active_mode(self) -> ContextMode:
        return self._mode

    @property
    def active_spec(self) -> ContextSpec:
        return self._spec

    # ── Layer Implementation ───────────────────────────────────────────

    def _settings(self) -> ConfigDict:
        settings: ConfigDict = {}

        # Merge search engines: base + context delta
        if self._spec.search_engines:
            merged_engines: EngineMap = {**self._base_engines, **self._spec.search_engines}
            settings["url.searchengines"] = merged_engines

        # Apply context-specific settings delta
        settings.update(self._spec.settings_delta)

        return settings

    def _keybindings(self) -> BindingList:
        L = self._leader

        # ── Context switching bindings (always registered) ─────────────
        switch_bindings: BindingList = [
            # ,C prefix = Context switch
            (f"{L}Cd", f"spawn --userscript context_switch.py dev",      "normal"),
            (f"{L}Cw", f"spawn --userscript context_switch.py work",     "normal"),
            (f"{L}Cr", f"spawn --userscript context_switch.py research", "normal"),
            (f"{L}Cm", f"spawn --userscript context_switch.py media",    "normal"),
            (f"{L}C0", f"spawn --userscript context_switch.py default",  "normal"),
            # Show current context in messages
            (f"{L}Ci", "message-info 'Context: {env[QUTE_CONTEXT]}'",    "normal"),
        ]

        # ── Context-specific extra bindings ────────────────────────────
        return switch_bindings + list(self._spec.bindings_extra)

    # ── Introspection ──────────────────────────────────────────────────

    def describe(self) -> str:
        """Human-readable description of active context."""
        return (
            f"Context: {self._mode.value!r}  "
            f"({self._spec.description})\n"
            f"  engines: {sorted(self._spec.search_engines.keys())}\n"
            f"  settings: {sorted(self._spec.settings_delta.keys())}"
        )

    @staticmethod
    def available_contexts() -> List[str]:
        return [m.value for m in ContextMode]
