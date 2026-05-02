"""
strategies/profile.py
=====================
Unified Profile Strategy

Coordinates multiple per-domain profiles (privacy + performance + behavior)
into a single named "mode" selection.  This lifts the UX from two separate
enum choices to a single semantic intent:

  "I want a hardened+low-power configuration" → UnifiedProfile.SECURE_MOBILE
  "I want maximum speed, trust this machine"  → UnifiedProfile.PERFORMANCE

UnifiedProfile is NOT a replacement for PrivacyProfile/PerformanceProfile.
It is a *composite resolver* that returns (privacy, perf) tuples — leaving
the actual layer construction to the orchestrator.

Design:
  UnifiedProfile (enum) → ProfileStrategy.apply() → ProfileResolution
  ProfileResolution carries (privacy_profile, performance_profile, hint)

This allows config.py to expose a single PROFILE = "secure_mobile" knob
instead of two separate enum choices.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from enum import Enum, auto
from typing import Any, Dict

from core.types import ConfigDict
from core.strategy import Strategy, StrategyRegistry
from layers.privacy import PrivacyProfile
from layers.performance import PerformanceProfile

logger = logging.getLogger("qute.strategies.profile")


class UnifiedProfile(Enum):
    """
    High-level named profiles.  Each resolves to a (privacy, perf) pair.

    DAILY        → STANDARD + BALANCED   — everyday browsing
    FOCUSED      → STANDARD + HIGH       — developer / power user
    SECURE       → HARDENED + BALANCED   — security-conscious
    SECURE_MOBILE→ HARDENED + LAPTOP     — secure + battery-aware
    PARANOID     → PARANOID  + LOW       — maximum privacy, minimum footprint
    KIOSK        → HARDENED + LOW        — shared / locked-down terminal
    RESEARCH     → STANDARD + HIGH       — open tabs, fast, minimal friction
    """
    DAILY         = auto()
    FOCUSED       = auto()
    SECURE        = auto()
    SECURE_MOBILE = auto()
    PARANOID      = auto()
    KIOSK         = auto()
    RESEARCH      = auto()


@dataclass(frozen=True)
class ProfileResolution:
    """Result of resolving a UnifiedProfile."""
    privacy_profile:     PrivacyProfile
    performance_profile: PerformanceProfile
    description:         str


# ─────────────────────────────────────────────
# Resolution Table  (data-driven)
# ─────────────────────────────────────────────
_RESOLUTION_TABLE: Dict[UnifiedProfile, ProfileResolution] = {
    UnifiedProfile.DAILY: ProfileResolution(
        PrivacyProfile.STANDARD,
        PerformanceProfile.BALANCED,
        "Everyday browsing — sensible defaults",
    ),
    UnifiedProfile.FOCUSED: ProfileResolution(
        PrivacyProfile.STANDARD,
        PerformanceProfile.HIGH,
        "Developer / power user — fast, minimal restrictions",
    ),
    UnifiedProfile.SECURE: ProfileResolution(
        PrivacyProfile.HARDENED,
        PerformanceProfile.BALANCED,
        "Security-conscious — hardened privacy, normal speed",
    ),
    UnifiedProfile.SECURE_MOBILE: ProfileResolution(
        PrivacyProfile.HARDENED,
        PerformanceProfile.LAPTOP,
        "Secure + battery-aware — hardened + laptop tuning",
    ),
    UnifiedProfile.PARANOID: ProfileResolution(
        PrivacyProfile.PARANOID,
        PerformanceProfile.LOW,
        "Maximum privacy — JS off, Tor, minimal memory",
    ),
    UnifiedProfile.KIOSK: ProfileResolution(
        PrivacyProfile.HARDENED,
        PerformanceProfile.LOW,
        "Shared terminal — locked-down, low footprint",
    ),
    UnifiedProfile.RESEARCH: ProfileResolution(
        PrivacyProfile.STANDARD,
        PerformanceProfile.HIGH,
        "Research session — many tabs, fast completion, low friction",
    ),
}


# ─────────────────────────────────────────────
# Strategy
# ─────────────────────────────────────────────
class ProfileStrategy(Strategy[ProfileResolution]):
    """
    Resolves a UnifiedProfile into its component profiles.

    Context key: "profile" (UnifiedProfile enum value or its .name string)
    """
    name = "unified_profile"

    def apply(self, context: ConfigDict) -> ProfileResolution:
        raw: Any = context.get("profile", UnifiedProfile.DAILY)

        if isinstance(raw, str):
            try:
                profile = UnifiedProfile[raw.upper()]
            except KeyError:
                logger.warning(
                    "[ProfileStrategy] unknown profile name %r, falling back to DAILY", raw
                )
                profile = UnifiedProfile.DAILY
        elif isinstance(raw, UnifiedProfile):
            profile = raw
        else:
            logger.warning("[ProfileStrategy] unexpected type %r, falling back to DAILY", type(raw)) # type: ignore
            profile = UnifiedProfile.DAILY

        resolution = _RESOLUTION_TABLE[profile]
        logger.debug(
            "[ProfileStrategy] %s → privacy=%s perf=%s",
            profile.name,
            resolution.privacy_profile.name,
            resolution.performance_profile.name,
        )
        return resolution


# ─────────────────────────────────────────────
# Registry Factory
# ─────────────────────────────────────────────
def build_profile_registry() -> StrategyRegistry[ProfileResolution]:
    """Return a profile strategy registry with the unified_profile strategy."""
    registry: StrategyRegistry[ProfileResolution] = StrategyRegistry(
        default=ProfileStrategy()
    )
    registry.register(ProfileStrategy())
    return registry


def resolve_profile(profile: UnifiedProfile) -> ProfileResolution:
    """Convenience: resolve directly without constructing a registry."""
    return _RESOLUTION_TABLE[profile]


