"""
policies/network.py
===================
Network-Level Policies

Controls proxy, DNS, and network-level privacy behaviors.

STANDARD  → no proxy, DNS prefetch on, normal network
HARDENED  → DNS prefetch off, no referrer on cross-origin
PARANOID  → route through Tor SOCKS5 proxy
"""

from __future__ import annotations

import logging
from typing import Any, Optional, cast

from core.types import ConfigDict
from core.strategy import Policy, PolicyAction, PolicyChain, PolicyDecision
from layers.privacy import PrivacyProfile

logger = logging.getLogger("qute.policies.network")


class DnsPrefetchPolicy(Policy):
    """HARDENED/PARANOID: disable DNS prefetching (leaks visited sites)."""
    name = "dns_prefetch_policy"
    priority = 10

    def __init__(self, profile: PrivacyProfile) -> None:
        self._profile = profile

    def evaluate(self, key: str, value: Any, context: ConfigDict) -> Optional[PolicyDecision]:
        if key != "content.dns_prefetch":
            return None
        if self._profile in (PrivacyProfile.HARDENED, PrivacyProfile.PARANOID) and value is True:
            return PolicyDecision(
                action=PolicyAction.MODIFY,
                reason=f"{self._profile.name}: DNS prefetch disabled (fingerprint/leak risk)",
                modified_value=False,
            )
        return None


class ReferrerPolicy(Policy):
    """
    HARDENED: set referrer policy to same-origin.
    PARANOID: set to never.
    """
    name = "referrer_policy"
    priority = 15

    def __init__(self, profile: PrivacyProfile) -> None:
        self._profile = profile

    def evaluate(self, key: str, value: Any, context: ConfigDict) -> Optional[PolicyDecision]:
        if key != "content.headers.referer":
            return None
        if self._profile == PrivacyProfile.PARANOID and value != "never":
            return PolicyDecision(
                action=PolicyAction.MODIFY,
                reason="PARANOID: Referer header must be 'never'",
                modified_value="never",
            )
        if self._profile == PrivacyProfile.HARDENED and value == "always":
            return PolicyDecision(
                action=PolicyAction.MODIFY,
                reason="HARDENED: Referer downgraded to 'same-origin'",
                modified_value="same-origin",
            )
        return None


class ProxyFormatPolicy(Policy):
    """
    Guard: content.proxy must be a single str, never a list.

    qutebrowser's content.proxy setting accepts exactly one URL string
    (or the keywords "system"/"none").  Passing a list causes the error:
      "expected a value of type str but got list"

    This policy intercepts the mistake early and either:
      - MODIFY: coerce list → first element (best-effort recovery), or
      - BLOCK:  reject entirely if the list is empty or malformed.
    """
    name     = "proxy_format_policy"
    priority = 1   # run before ProxyPolicy (priority=5)

    def evaluate(self, key: str, value: Any, context: ConfigDict) -> Optional[PolicyDecision]:
        if key != "content.proxy":
            return None
        if not value:
            return PolicyDecision(
                action=PolicyAction.BLOCK,
                reason=(
                    "[ProxyFormat] content.proxy received an empty list — "
                    "must be a str like 'socks5://host:port' or 'system'."
                ),
            )
        if not isinstance(value, list):
            return None   # str/None: handled by ProxyPolicy
        value = cast(list[Any], value)
        first = value[0]
        if not isinstance(first, str):
            return PolicyDecision(
                action=PolicyAction.BLOCK,
                reason=(
                    f"[ProxyFormat] content.proxy list contains non-str element: "
                    f"{first!r}."
                ),
            )
        logger.warning(
            "[ProxyFormat] content.proxy was a list %r; "
            "coercing to first element %r.  "
            "Fix config.py: set USER_PROXY = %r (a single str).",
            value, first, first,
        )
        return PolicyDecision(
            action=PolicyAction.MODIFY,
            reason=(
                f"[ProxyFormat] list coerced → {first!r}. "
                "Set USER_PROXY to a single str to suppress this warning."
            ),
            modified_value=first,
        )


class ProxyPolicy(Policy):
    """
    PARANOID: enforce Tor SOCKS5 proxy.
    Warns if proxy is unset under PARANOID.
    """
    name = "proxy_policy"
    priority = 5

    def __init__(self, profile: PrivacyProfile) -> None:
        self._profile = profile

    def evaluate(self, key: str, value: Any, context: ConfigDict) -> Optional[PolicyDecision]:
        if key != "content.proxy":
            return None
        if self._profile == PrivacyProfile.PARANOID and value in ("system", "none", None):
            return PolicyDecision(
                action=PolicyAction.WARN,
                reason=(
                    "PARANOID profile expects a proxy (e.g. socks://localhost:9050 for Tor). "
                    "Set content.proxy in your UserLayer or host policy."
                ),
            )
        return None


class HttpsOnlyPolicy(Policy):
    """
    PARANOID: HTTPS everywhere — deny non-HTTPS upgrades being turned off.
    """
    name = "https_only_policy"
    priority = 20

    def __init__(self, profile: PrivacyProfile) -> None:
        self._profile = profile

    def evaluate(self, key: str, value: Any, context: ConfigDict) -> Optional[PolicyDecision]:
        if key != "content.tls.certificate_errors":
            return None
        if self._profile == PrivacyProfile.PARANOID and value != "block":
            return PolicyDecision(
                action=PolicyAction.MODIFY,
                reason="PARANOID: TLS errors must be 'block'",
                modified_value="block",
            )
        return None


# ─────────────────────────────────────────────
# Factory
# ─────────────────────────────────────────────
def build_network_policy_chain(profile: PrivacyProfile) -> PolicyChain:
    """Return a PolicyChain for network-level controls."""
    chain = PolicyChain()
    chain.add(ProxyFormatPolicy())          # priority=1: catch list before ProxyPolicy
    chain.add(DnsPrefetchPolicy(profile))
    chain.add(ReferrerPolicy(profile))
    chain.add(ProxyPolicy(profile))
    chain.add(HttpsOnlyPolicy(profile))
    logger.debug("[NetworkPolicies] built for profile %s", profile.name)
    return chain


