"""
policies/content.py
===================
Web Content Policies

Data-driven rules that constrain qutebrowser content settings.
Applied via PolicyChain before settings are written to qutebrowser.

Policies are tiered by PrivacyProfile:
  STANDARD → minimal restriction; sensible defaults
  HARDENED → strict; cookies/storage blocked by default
  PARANOID  → maximum; JS/images/canvas all off

The PolicyChain is evaluated per-key during apply_settings().
A DENY decision means the setting is silently dropped (not applied).
A MODIFY decision means the value is clamped/replaced before apply.
A WARN decision logs a warning but still applies.
"""

from __future__ import annotations

import logging
from typing import Any, Optional

from core.types import ConfigDict
from core.strategy import Policy, PolicyAction, PolicyChain, PolicyDecision
from layers.privacy import PrivacyProfile

logger = logging.getLogger("qute.policies.content")


# ─────────────────────────────────────────────
# Content Policies
# ─────────────────────────────────────────────
class JavaScriptPolicy(Policy):
    """
    Enforce JavaScript settings based on profile.
    PARANOID: always disable JS, regardless of user overrides in non-host settings.
    """
    name = "js_policy"
    priority = 10

    def __init__(self, profile: PrivacyProfile) -> None:
        self._profile = profile

    def evaluate(self, key: str, value: Any, context: ConfigDict) -> Optional[PolicyDecision]:
        if key != "content.javascript.enabled":
            return None
        if self._profile == PrivacyProfile.PARANOID and value is True:
            return PolicyDecision(
                action=PolicyAction.DENY,
                reason="PARANOID profile: JavaScript globally disabled",
            )
        return None


class CookiePolicy(Policy):
    """
    Enforce cookie acceptance policy.
    HARDENED: only same-site cookies (no third-party).
    PARANOID: no cookies at all.
    """
    name = "cookie_policy"
    priority = 15

    def __init__(self, profile: PrivacyProfile) -> None:
        self._profile = profile

    def evaluate(self, key: str, value: Any, context: ConfigDict) -> Optional[PolicyDecision]:
        if key != "content.cookies.accept":
            return None
        if self._profile == PrivacyProfile.PARANOID and value != "never":
            return PolicyDecision(
                action=PolicyAction.MODIFY,
                reason="PARANOID profile: cookies must be 'never'",
                modified_value="never",
            )
        if self._profile == PrivacyProfile.HARDENED and value == "all":
            return PolicyDecision(
                action=PolicyAction.MODIFY,
                reason="HARDENED profile: downgrading 'all' cookies to 'no-3rdparty'",
                modified_value="no-3rdparty",
            )
        return None


class AutoplayPolicy(Policy):
    """HARDENED/PARANOID: always block autoplay."""
    name = "autoplay_policy"
    priority = 20

    def __init__(self, profile: PrivacyProfile) -> None:
        self._profile = profile

    def evaluate(self, key: str, value: Any, context: ConfigDict) -> Optional[PolicyDecision]:
        if key != "content.autoplay":
            return None
        if self._profile in (PrivacyProfile.HARDENED, PrivacyProfile.PARANOID) and value is True:
            return PolicyDecision(
                action=PolicyAction.MODIFY,
                reason=f"{self._profile.name}: autoplay must be off",
                modified_value=False,
            )
        return None


class CanvasReadingPolicy(Policy):
    """
    PARANOID: disable canvas reading (fingerprinting vector).
    HARDENED: warn if enabled (not block, for usability).
    """
    name = "canvas_policy"
    priority = 25

    def __init__(self, profile: PrivacyProfile) -> None:
        self._profile = profile

    def evaluate(self, key: str, value: Any, context: ConfigDict) -> Optional[PolicyDecision]:
        if key != "content.canvas_reading":
            return None
        if self._profile == PrivacyProfile.PARANOID and value is True:
            return PolicyDecision(
                action=PolicyAction.MODIFY,
                reason="PARANOID: canvas reading blocked (fingerprint vector)",
                modified_value=False,
            )
        if self._profile == PrivacyProfile.HARDENED and value is True:
            return PolicyDecision(
                action=PolicyAction.WARN,
                reason="HARDENED: canvas reading enabled; consider disabling",
            )
        return None


class LocalStoragePolicy(Policy):
    """PARANOID: block local storage."""
    name = "localstorage_policy"
    priority = 30

    def __init__(self, profile: PrivacyProfile) -> None:
        self._profile = profile

    def evaluate(self, key: str, value: Any, context: ConfigDict) -> Optional[PolicyDecision]:
        if key != "content.local_storage":
            return None
        if self._profile == PrivacyProfile.PARANOID and value is True:
            return PolicyDecision(
                action=PolicyAction.MODIFY,
                reason="PARANOID: local storage disabled",
                modified_value=False,
            )
        return None


class WebRTCPolicy(Policy):
    """
    HARDENED/PARANOID: enforce 'disable-non-proxied-udp' WebRTC policy
    to prevent IP leaks through WebRTC.
    """
    name = "webrtc_policy"
    priority = 35

    def __init__(self, profile: PrivacyProfile) -> None:
        self._profile = profile

    def evaluate(self, key: str, value: Any, context: ConfigDict) -> Optional[PolicyDecision]:
        if key != "content.webrtc_ip_handling_policy":
            return None
        safe_values = {"disable-non-proxied-udp", "disable-udp"}
        if self._profile in (PrivacyProfile.HARDENED, PrivacyProfile.PARANOID):
            if value not in safe_values:
                return PolicyDecision(
                    action=PolicyAction.MODIFY,
                    reason=f"{self._profile.name}: WebRTC must not expose real IP",
                    modified_value="disable-non-proxied-udp",
                )
        return None


# ─────────────────────────────────────────────
# Factory
# ─────────────────────────────────────────────
def build_content_policy_chain(profile: PrivacyProfile) -> PolicyChain:
    """Return a PolicyChain configured for the given privacy profile."""
    chain = PolicyChain()
    chain.add(JavaScriptPolicy(profile))
    chain.add(CookiePolicy(profile))
    chain.add(AutoplayPolicy(profile))
    chain.add(CanvasReadingPolicy(profile))
    chain.add(LocalStoragePolicy(profile))
    chain.add(WebRTCPolicy(profile))
    logger.debug("[ContentPolicies] built for profile %s", profile.name)
    return chain


