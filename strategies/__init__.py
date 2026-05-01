"""
strategies/__init__.py
======================
Pluggable algorithm strategies for config processing.
"""
from strategies.merge    import (
    build_merge_registry,
    LastWinsStrategy,
    FirstWinsStrategy,
    DeepMergeStrategy,
    ProfileAwareMergeStrategy,
)
from strategies.search   import build_search_registry
from strategies.download import build_download_registry
from strategies.profile  import UnifiedProfile, ProfileResolution

__all__ = [
    "build_merge_registry",
    "LastWinsStrategy", "FirstWinsStrategy",
    "DeepMergeStrategy", "ProfileAwareMergeStrategy",
    "build_search_registry",
    "build_download_registry",
    "UnifiedProfile", "ProfileResolution",
]
