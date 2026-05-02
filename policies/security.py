"""
policies/security.py
====================
Security Boundary Policies

Hard security constraints that cannot be overridden by higher-priority layers.
These are the "floor" of security — even UserLayer cannot weaken them under
HARDENED/PARANOID profiles.

Contrast with content.py (profile-tiered) and network.py (network-layer):
  security.py covers: TLS, cert validation, geolocation, camera/mic access.
"""

from __future__ import annotations

import logging
from typing import Any, Optional

from core.types import ConfigDict
from core.strategy import Policy, PolicyAction, PolicyChain, PolicyDecision
from layers.privacy import PrivacyProfile

logger = logging.getLogger("qute.policies.security")


class GeolocationPolicy(Policy):
    """HARDENED/PARANOID: never share geolocation."""
    name = "geolocation_policy"
    priority = 10

    def __init__(self, profile: PrivacyProfile) -> None:
        self._profile = profile

    def evaluate(self, key: str, value: Any, context: ConfigDict) -> Optional[PolicyDecision]:
        if key != "content.geolocation":
            return None
        if self._profile in (PrivacyProfile.HARDENED, PrivacyProfile.PARANOID) and value is True:
            return PolicyDecision(
                action=PolicyAction.MODIFY,
                reason=f"{self._profile.name}: geolocation disabled",
                modified_value=False,
            )
        return None


class MediaCapturePolicy(Policy):
    """HARDENED/PARANOID: block camera and microphone access."""
    name = "media_capture_policy"
    priority = 15

    def __init__(self, profile: PrivacyProfile) -> None:
        self._profile = profile

    def evaluate(self, key: str, value: Any, context: ConfigDict) -> Optional[PolicyDecision]:
        if key not in ("content.media.audio_capture", "content.media.video_capture",
                       "content.media.audio_video_capture"):
            return None
        if self._profile in (PrivacyProfile.HARDENED, PrivacyProfile.PARANOID) and value is True:
            return PolicyDecision(
                action=PolicyAction.MODIFY,
                reason=f"{self._profile.name}: media capture blocked",
                modified_value=False,
            )
        return None


class NotificationPolicy(Policy):
    """HARDENED/PARANOID: block push notifications."""
    name = "notification_policy"
    priority = 20

    def __init__(self, profile: PrivacyProfile) -> None:
        self._profile = profile

    def evaluate(self, key: str, value: Any, context: ConfigDict) -> Optional[PolicyDecision]:
        if key != "content.notifications.enabled":
            return None
        if self._profile in (PrivacyProfile.HARDENED, PrivacyProfile.PARANOID) and value is True:
            return PolicyDecision(
                action=PolicyAction.MODIFY,
                reason=f"{self._profile.name}: notifications blocked",
                modified_value=False,
            )
        return None


class ClipboardPolicy(Policy):
    """HARDENED/PARANOID: JS cannot read/write clipboard."""
    name = "clipboard_policy"
    priority = 25

    def __init__(self, profile: PrivacyProfile) -> None:
        self._profile = profile

    def evaluate(self, key: str, value: Any, context: ConfigDict) -> Optional[PolicyDecision]:
        if key != "content.javascript.clipboard":
            return None
        if (self._profile in (PrivacyProfile.HARDENED, PrivacyProfile.PARANOID)
                and value != "none"):
            return PolicyDecision(
                action=PolicyAction.MODIFY,
                reason=f"{self._profile.name}: JS clipboard access must be 'none'",
                modified_value="none",
            )
        return None


class MixedContentPolicy(Policy):
    """All profiles: prevent mixed content (HTTP inside HTTPS)."""
    name = "mixed_content_policy"
    priority = 5

    def evaluate(self, key: str, value: Any, context: ConfigDict) -> Optional[PolicyDecision]:
        if key != "downloads.prevent_mixed_content":
            return None
        if value is False:
            return PolicyDecision(
                action=PolicyAction.MODIFY,
                reason="mixed content prevention must be enabled",
                modified_value=True,
            )
        return None


# ─────────────────────────────────────────────
# Factory
# ─────────────────────────────────────────────
def build_security_policy_chain(profile: PrivacyProfile) -> PolicyChain:
    """Return a PolicyChain for security boundary enforcement."""
    chain = PolicyChain()
    chain.add(MixedContentPolicy())   # all profiles
    chain.add(GeolocationPolicy(profile))
    chain.add(MediaCapturePolicy(profile))
    chain.add(NotificationPolicy(profile))
    chain.add(ClipboardPolicy(profile))
    logger.debug("[SecurityPolicies] built for profile %s", profile.name)
    return chain


