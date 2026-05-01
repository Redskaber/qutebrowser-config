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
  ,Ci  → show active context in message bar

Design:
  ContextMode (enum)  — named contexts
  ContextSpec (data)  — per-context settings + engines + bindings delta
  ContextLayer        — resolves active spec into config delta

Architecture integration:
  - ContextLayer resolves active context from (in priority order):
      1. ``context`` constructor parameter  (from config.py ACTIVE_CONTEXT)
      2. ``QUTE_CONTEXT`` environment variable
      3. ``~/.config/qutebrowser/.context`` persistent file
      4. ContextMode.DEFAULT fallback
  - All context switching is done via keybindings that call context_switch.py,
    which writes to the .context file and sends :config-source.
  - No qutebrowser restart is needed.

Patterns: Strategy (context as spec), Data-Driven, State (active context).

Strict-mode: all attrs typed; ContextSpec is frozen dataclass.

v6 changes:
  - _resolve_active_mode now reads ~/.config/qutebrowser/.context file
    (previously only env var + constructor param were checked — file was
    written by context_switch.py but never read back)
  - Added WRITING context (focus / reference / no distractions)
  - Added ,Cwr binding for writing context
  - ContextSpec.bindings_extra uses proper List[Tuple[str,str,str]] type
  - _CONTEXT_FILE_ENV for override (useful in tests / NixOS)
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple

from core.layer import BaseConfigLayer

ConfigDict  = Dict[str, Any]
BindingList = List[Tuple[str, str, str]]
EngineMap   = Dict[str, str]

logger = logging.getLogger("qute.layers.context")

# Override context file path in tests via this env var
_CONTEXT_FILE_ENV = "QUTE_CONTEXT_FILE"


# ─────────────────────────────────────────────
# Context Modes (named situations)
# ─────────────────────────────────────────────
class ContextMode(str, Enum):
    """Named situational modes.  String values are also used as display names."""
    DEFAULT  = "default"
    WORK     = "work"
    RESEARCH = "research"
    MEDIA    = "media"
    DEV      = "dev"
    WRITING  = "writing"


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
    mode:           ContextMode
    description:    str                                  = ""
    search_engines: EngineMap                            = field(default_factory=dict)
    settings_delta: ConfigDict                           = field(default_factory=dict)
    bindings_extra: List[Tuple[str, str, str]]           = field(default_factory=list)


# ─────────────────────────────────────────────
# Context Table (data-driven)
# ─────────────────────────────────────────────
_CONTEXT_TABLE: Dict[ContextMode, ContextSpec] = {

    ContextMode.DEFAULT: ContextSpec(
        mode=ContextMode.DEFAULT,
        description="Default — base settings, no overrides",
        search_engines={},
        settings_delta={},
        bindings_extra=[],
    ),

    ContextMode.WORK: ContextSpec(
        mode=ContextMode.WORK,
        description="Work mode — corporate tools, productivity search",
        search_engines={
            "DEFAULT": "https://www.google.com/search?q={}",
            "jira":    "https://jira.atlassian.com/issues/?jql=text+~+{}",
            "conf":    "https://confluence.atlassian.com/dosearchsite.action?queryString={}",
            "gl":      "https://gitlab.com/search?search={}",
            "gh":      "https://github.com/search?q={}&type=repositories",
            "slack":   "https://slack.com/app_redirect?channel={}",
        },
        settings_delta={
            "content.autoplay":              False,
            "content.notifications.enabled": False,
            "tabs.show":                     "multiple",
        },
        bindings_extra=[],
    ),

    ContextMode.RESEARCH: ContextSpec(
        mode=ContextMode.RESEARCH,
        description="Research mode — arXiv, Scholar, Wikipedia, no distractions",
        search_engines={
            "DEFAULT": "https://search.brave.com/search?q={}",
            "arxiv":   "https://arxiv.org/search/?searchtype=all&query={}",
            "scholar": "https://scholar.google.com/scholar?q={}",
            "pubmed":  "https://pubmed.ncbi.nlm.nih.gov/?term={}",
            "doi":     "https://doi.org/{}",
            "wiki":    "https://en.wikipedia.org/w/index.php?search={}",
            "wolfram": "https://www.wolframalpha.com/input?i={}",
            "sem":     "https://www.semanticscholar.org/search?q={}&sort=Relevance",
        },
        settings_delta={
            "content.autoplay":              False,
            "content.notifications.enabled": False,
            "statusbar.show":                "in-mode",
            "tabs.show":                     "multiple",
        },
        bindings_extra=[],
    ),

    ContextMode.MEDIA: ContextSpec(
        mode=ContextMode.MEDIA,
        description="Media mode — YouTube, Bilibili, Twitch; autoplay ON",
        search_engines={
            "DEFAULT": "https://www.youtube.com/results?search_query={}",
            "bili":    "https://search.bilibili.com/all?keyword={}",
            "twitch":  "https://www.twitch.tv/search?term={}",
            "spotify": "https://open.spotify.com/search/{}",
            "sc":      "https://soundcloud.com/search?q={}",
        },
        settings_delta={
            "content.autoplay":              True,
            "content.notifications.enabled": False,
            "tabs.show":                     "always",
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
            "content.autoplay":              False,
            "content.notifications.enabled": False,
            "tabs.show":                     "always",
            "completion.web_history.max_items": 30,
        },
        bindings_extra=[],
    ),

    ContextMode.WRITING: ContextSpec(
        mode=ContextMode.WRITING,
        description="Writing mode — focus, reference tools, minimal UI",
        search_engines={
            "DEFAULT": "https://search.brave.com/search?q={}",
            "dict":    "https://www.merriam-webster.com/dictionary/{}",
            "thes":    "https://www.thesaurus.com/browse/{}",
            "gram":    "https://www.grammarly.com/blog/?s={}",
            "wiki":    "https://en.wikipedia.org/w/index.php?search={}",
        },
        settings_delta={
            "content.autoplay":              False,
            "content.notifications.enabled": False,
            "statusbar.show":                "in-mode",
            "tabs.show":                     "multiple",
        },
        bindings_extra=[],
    ),
}


# ─────────────────────────────────────────────
# Context File Resolution
# ─────────────────────────────────────────────

def _default_context_file() -> str:
    """
    Return the path to the persistent .context file.

    Priority:
      1. QUTE_CONTEXT_FILE env var (tests / NixOS override)
      2. QUTE_CONFIG_DIR env var (set by qutebrowser)
      3. ~/.config/qutebrowser/.context  (default)
    """
    if override := os.environ.get(_CONTEXT_FILE_ENV):
        return override
    config_dir = os.environ.get(
        "QUTE_CONFIG_DIR",
        os.path.expanduser("~/.config/qutebrowser"),
    )
    return os.path.join(config_dir, ".context")


def _read_context_file(path: str) -> Optional[str]:
    """
    Read the context name from the .context file.
    Returns None if the file is missing, empty, or unreadable.
    """
    try:
        raw = open(path).read().strip()
        return raw if raw else None
    except OSError:
        return None


# ─────────────────────────────────────────────
# Context Resolution
# ─────────────────────────────────────────────
def _resolve_active_mode(override: Optional[str]) -> ContextMode:
    """
    Resolve the active ContextMode.

    Priority order:
      1. ``override`` parameter (from config.py ACTIVE_CONTEXT)          ← highest
      2. QUTE_CONTEXT environment variable
      3. ~/.config/qutebrowser/.context file (written by context_switch.py)
      4. ContextMode.DEFAULT fallback                                     ← lowest
    """
    # Source candidates in priority order
    raw: Optional[str] = (
        override
        or os.environ.get("QUTE_CONTEXT")
        or _read_context_file(_default_context_file())
    )

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
        context:       Active context name (or None → auto-detect from env/file).
        leader:        Leader key prefix (default ",").
        base_engines:  Engines already established by lower layers.
                       ContextLayer *merges* its engine delta on top.
    """

    name        = "context"
    priority    = 45
    description = "Situational context — work / research / media / dev / writing"

    def __init__(
        self,
        context:      Optional[str]       = None,
        leader:       str                 = ",",
        base_engines: Optional[EngineMap] = None,
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
            (f"{L}Cd",  "spawn --userscript context_switch.py dev",      "normal"),
            (f"{L}Cw",  "spawn --userscript context_switch.py work",     "normal"),
            (f"{L}Cr",  "spawn --userscript context_switch.py research", "normal"),
            (f"{L}Cm",  "spawn --userscript context_switch.py media",    "normal"),
            (f"{L}Cwt", "spawn --userscript context_switch.py writing",  "normal"),
            (f"{L}C0",  "spawn --userscript context_switch.py default",  "normal"),
            # Show current context in message bar
            (f"{L}Ci",
             f"message-info 'Context: {self._mode.value} — {self._spec.description}'",
             "normal"),
        ]

        # ── Context-specific extra bindings ────────────────────────────
        return switch_bindings + list(self._spec.bindings_extra)

    # ── Introspection ──────────────────────────────────────────────────

    def describe(self) -> str:
        """Human-readable description of active context."""
        return (
            f"Context: {self._mode.value}\n"
            f"  Description : {self._spec.description}\n"
            f"  Engines     : {sorted(self._spec.search_engines.keys())}\n"
            f"  Settings Δ  : {list(self._spec.settings_delta.keys())}\n"
        )
