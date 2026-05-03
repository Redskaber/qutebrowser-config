"""
strategies/__init__.py
======================
Pluggable algorithm strategies for config processing.
"""
from strategies.download import (
    build_download_registry,
    NoDispatcherStrategy,
    XdgOpenStrategy,
    RifleStrategy,
    HandlrStrategy,
    AutoDetectDownloadStrategy,
)
from strategies.merge    import (
    build_merge_registry,
    LastWinsStrategy,
    FirstWinsStrategy,
    DeepMergeStrategy,
    ProfileAwareMergeStrategy,
)
from strategies.search   import build_search_registry
from strategies.profile  import (
    UnifiedProfile,
    ProfileResolution,
    build_profile_registry,
    resolve_profile,
)

__all__ = [
    # download
    "build_download_registry",
    "NoDispatcherStrategy",
    "XdgOpenStrategy",
    "RifleStrategy",
    "HandlrStrategy",
    "AutoDetectDownloadStrategy",
    # merge
    "build_merge_registry",
    "LastWinsStrategy",
    "FirstWinsStrategy",
    "DeepMergeStrategy",
    "ProfileAwareMergeStrategy",
    # search
    "build_search_registry",
    # profile
    "UnifiedProfile",
    "ProfileResolution",
    "build_profile_registry",
    "resolve_profile",
]
