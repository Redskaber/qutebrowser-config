"""
strategies/search.py
====================
Search Engine Strategy

Provides composable search engine sets as named strategies.
The orchestrator (or UserLayer) selects a set by name, so users
never have to maintain a giant url.searchengines dict by hand.

Strategy → dict[shortcut → url_template]

Sets are additive: the registry merges the "base" set with a named overlay,
so custom sets only need to declare their *additions* or *overrides*.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, cast

from core.strategy import ConfigDict, Strategy, StrategyRegistry

logger = logging.getLogger("qute.strategies.search")

SearchEngineMap = Dict[str, str]


# ─────────────────────────────────────────────
# Base Engine Set (always present)
# ─────────────────────────────────────────────
_BASE_ENGINES: SearchEngineMap = {
    "DEFAULT": "https://search.brave.com/search?q={}",
    "g":       "https://www.google.com/search?q={}",
    "ddg":     "https://duckduckgo.com/?q={}",
    "w":       "https://en.wikipedia.org/w/index.php?search={}",
    "yt":      "https://www.youtube.com/results?search_query={}",
    "gh":      "https://github.com/search?q={}&type=repositories",
}

_DEV_EXTRAS: SearchEngineMap = {
    "nix":    "https://search.nixos.org/packages?query={}",
    "crates": "https://crates.io/search?q={}",
    "pypi":   "https://pypi.org/search/?q={}",
    "mdn":    "https://developer.mozilla.org/en-US/search?q={}",
    "docs":   "https://devdocs.io/#q={}",
    "rs":     "https://doc.rust-lang.org/std/?search={}",
    "go":     "https://pkg.go.dev/search?q={}",
}

_PRIVACY_EXTRAS: SearchEngineMap = {
    "DEFAULT": "https://search.brave.com/search?q={}",
    "sx":      "https://searx.be/search?q={}",
    "metager": "https://metager.org/meta/meta.ger3?eingabe={}",
}

_ACADEMIA_EXTRAS: SearchEngineMap = {
    "arxiv":  "https://arxiv.org/search/?searchtype=all&query={}",
    "scholar": "https://scholar.google.com/scholar?q={}",
    "pubmed": "https://pubmed.ncbi.nlm.nih.gov/?term={}",
    "doi":    "https://doi.org/{}",
}

_CHINESE_EXTRAS: SearchEngineMap = {
    "DEFAULT": "https://www.baidu.com/s?wd={}",
    "bili":    "https://search.bilibili.com/all?keyword={}",
    "zhihu":   "https://www.zhihu.com/search?type=content&q={}",
    "taobao":  "https://s.taobao.com/search?q={}",
    "jd":      "https://search.jd.com/Search?keyword={}",
}


# ─────────────────────────────────────────────
# Strategy Implementations
# ─────────────────────────────────────────────
class BaseSearchStrategy(Strategy[SearchEngineMap]):
    """Minimal search set: just the universals."""
    name = "base"

    def apply(self, context: ConfigDict) -> SearchEngineMap:
        return dict(_BASE_ENGINES)


class DevSearchStrategy(Strategy[SearchEngineMap]):
    """Developer-oriented: base + package registries + MDN."""
    name = "dev"

    def apply(self, context: ConfigDict) -> SearchEngineMap:
        return {**_BASE_ENGINES, **_DEV_EXTRAS}


class PrivacySearchStrategy(Strategy[SearchEngineMap]):
    """Privacy-first: replaces DEFAULT with Brave/SearX, no tracking."""
    name = "privacy"

    def apply(self, context: ConfigDict) -> SearchEngineMap:
        return {**_BASE_ENGINES, **_PRIVACY_EXTRAS}


class AcademiaSearchStrategy(Strategy[SearchEngineMap]):
    """Research: base + arXiv, Scholar, PubMed, DOI."""
    name = "academia"

    def apply(self, context: ConfigDict) -> SearchEngineMap:
        return {**_BASE_ENGINES, **_DEV_EXTRAS, **_ACADEMIA_EXTRAS}


class ChineseSearchStrategy(Strategy[SearchEngineMap]):
    """Chinese internet: replaces DEFAULT with Baidu, adds Bilibili/Zhihu."""
    name = "chinese"

    def apply(self, context: ConfigDict) -> SearchEngineMap:
        return {**_BASE_ENGINES, **_CHINESE_EXTRAS}


class FullSearchStrategy(Strategy[SearchEngineMap]):
    """Everything: all sets merged, DEFAULT = Brave."""
    name = "full"

    def apply(self, context: ConfigDict) -> SearchEngineMap:
        return {
            **_BASE_ENGINES,
            **_DEV_EXTRAS,
            **_ACADEMIA_EXTRAS,
            **_CHINESE_EXTRAS,
            # Override DEFAULT last to keep Brave
            "DEFAULT": "https://search.brave.com/search?q={}",
        }


class CustomSearchStrategy(Strategy[SearchEngineMap]):
    """
    User-supplied engines merged on top of a named base.

    Context keys:
      "custom_engines": dict[str, str]   — extra engines to add/override
      "base_strategy":  str              — which built-in set to start from
    """
    name = "custom"

    def apply(self, context: ConfigDict) -> SearchEngineMap:
        registry = build_search_registry()
        base_name = str(context.get("base_strategy", "dev"))

        try:
            base = registry.apply(base_name, context)
        except KeyError:
            base = dict(_BASE_ENGINES)

        custom = cast(SearchEngineMap, context.get("custom_engines", {}))
        return {**base, **custom}


# ─────────────────────────────────────────────
# Registry Factory
# ─────────────────────────────────────────────
def build_search_registry() -> StrategyRegistry[SearchEngineMap]:
    """Return a populated search engine strategy registry."""
    registry: StrategyRegistry[SearchEngineMap] = StrategyRegistry(
        default=DevSearchStrategy()
    )
    for s in [
        BaseSearchStrategy(),
        DevSearchStrategy(),
        PrivacySearchStrategy(),
        AcademiaSearchStrategy(),
        ChineseSearchStrategy(),
        FullSearchStrategy(),
        CustomSearchStrategy(),
    ]:
        registry.register(s)

    logger.debug("[SearchRegistry] registered: %s", registry.names())
    return registry


