"""
strategies/merge.py
===================
Config Merge Strategies

Concrete merge algorithms for the LayerStack resolution pipeline.
Each strategy implements a different conflict-resolution semantics.

Architecture:
  StrategyRegistry[ConfigDict]
    ├── "last_wins"     → simple dict update (overlay wins)
    ├── "first_wins"    → base wins; overlay fills gaps
    ├── "deep_merge"    → recursive dict merge (overlay wins leaves)
    └── "profile_aware" → deep merge + profile-specific post-processing

Registered via build_merge_registry() — inject into orchestrator or pipeline.

Strict-mode: all type params explicit; no bare dict usage.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, cast

from core.strategy import ConfigDict, Strategy, StrategyRegistry, recursive_merge

logger = logging.getLogger("qute.strategies.merge")


# ─────────────────────────────────────────────
# Concrete Merge Strategies
# ─────────────────────────────────────────────
class LastWinsStrategy(Strategy[ConfigDict]):
    """
    Simple last-writer-wins: overlay unconditionally replaces base.
    Fast, used for flat settings without nested dicts.
    """
    name = "last_wins"

    def apply(self, context: ConfigDict) -> ConfigDict:
        base:    ConfigDict = cast(ConfigDict, context.get("base", {}))
        overlay: ConfigDict = cast(ConfigDict, context.get("overlay", {}))
        return {**base, **overlay}


class FirstWinsStrategy(Strategy[ConfigDict]):
    """
    First-writer-wins: base takes precedence, overlay fills missing keys.
    Useful for locked defaults that must not be overridden.
    """
    name = "first_wins"

    def apply(self, context: ConfigDict) -> ConfigDict:
        base:    ConfigDict = cast(ConfigDict, context.get("base", {}))
        overlay: ConfigDict = cast(ConfigDict, context.get("overlay", {}))
        return {**overlay, **base}


class DeepMergeStrategy(Strategy[ConfigDict]):
    """
    Recursive deep merge: nested dicts are merged, not replaced.
    Overlay wins at leaf level; intermediate nodes are merged.

    Example:
      base    = {"tabs": {"position": "top", "show": "always"}}
      overlay = {"tabs": {"position": "bottom"}}
      result  = {"tabs": {"position": "bottom", "show": "always"}}
    """
    name = "deep_merge"

    def apply(self, context: ConfigDict) -> ConfigDict:
        base:    ConfigDict = cast(ConfigDict, context.get("base", {}))
        overlay: ConfigDict = cast(ConfigDict, context.get("overlay", {}))
        return recursive_merge(base, overlay)


class ProfileAwareMergeStrategy(Strategy[ConfigDict]):
    """
    Deep merge + profile promotion.

    If the context carries a 'profile' key (e.g. 'hardened', 'laptop'),
    this strategy hoists profile-specific sub-dicts into the result.

    Example context:
      {
        "base":    {...},
        "overlay": {...},
        "profile": "laptop",
        "profiles": {
          "laptop": {"content.cache.size": 67108864},
        }
      }

    Result = deep_merge(base, overlay) deep-merged with profiles["laptop"].
    """
    name = "profile_aware"

    def apply(self, context: ConfigDict) -> ConfigDict:
        base:    ConfigDict = cast(ConfigDict, context.get("base", {}))
        overlay: ConfigDict = cast(ConfigDict, context.get("overlay", {}))
        profile: str        = str(context.get("profile", ""))
        profiles: Dict[str, Any] = cast(
            Dict[str, Any], context.get("profiles", {})
        )

        merged = recursive_merge(base, overlay)
        if profile and profile in profiles:
            profile_delta = cast(ConfigDict, profiles[profile])
            merged = recursive_merge(merged, profile_delta)
            logger.debug("[ProfileAwareMerge] applied profile '%s'", profile)

        return merged

    def can_handle(self, context: ConfigDict) -> bool:
        return "profile" in context


# ─────────────────────────────────────────────
# Registry Factory
# ─────────────────────────────────────────────
def build_merge_registry() -> StrategyRegistry[ConfigDict]:
    """
    Build and return a fully-populated merge strategy registry.
    Default fallback: deep_merge.
    """
    registry: StrategyRegistry[ConfigDict] = StrategyRegistry(
        default=DeepMergeStrategy()
    )
    registry.register(LastWinsStrategy())
    registry.register(FirstWinsStrategy())
    registry.register(DeepMergeStrategy())
    registry.register(ProfileAwareMergeStrategy())

    logger.debug("[MergeRegistry] registered: %s", registry.names())
    return registry


