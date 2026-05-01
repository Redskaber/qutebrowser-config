"""
policies/host.py
================
Per-Host Exception Policy Registry

A structured, data-driven registry for per-host configuration exceptions.
This sits *above* the PolicyChain system: host rules are applied via
config.set(key, value, pattern=...) rather than blocking/modifying global keys.

Design:
  HostRule (data) → HostPolicyRegistry → resolved per-pattern settings
  Applied by ConfigOrchestrator after global settings are merged.

Users add host rules by category, not by editing BehaviorLayer directly.
Categories provide semantic grouping and are queryable for docs/display.

This module is consumed by orchestrator.py and behavior.py.
Users should not import it directly — use the BEHAVIOR config section in config.py.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Dict, Iterator, List

logger = logging.getLogger("qute.policies.host")

ConfigDict = Dict[str, Any]


# ─────────────────────────────────────────────
# Data Model
# ─────────────────────────────────────────────
@dataclass(frozen=True)
class HostRule:
    """
    A single per-host configuration rule.

    Attributes:
        pattern:     URL pattern for config.set() — e.g. "*.example.com"
        settings:    Settings to apply for that pattern.
        description: Human-readable explanation (shown in docs/debug output).
        category:    Grouping key (e.g. "login", "dev", "media", "trusted").
        enabled:     Set to False to temporarily disable without deleting.
    """
    pattern:     str
    settings:    ConfigDict        = field(default_factory=dict)
    description: str               = ""
    category:    str               = "general"
    enabled:     bool              = True


# ─────────────────────────────────────────────
# Built-in Rule Sets
# ─────────────────────────────────────────────
#: Rules that are always loaded regardless of privacy profile.
ALWAYS_RULES: List[HostRule] = [
    HostRule(
        pattern="localhost",
        settings={
            "content.cookies.accept":           "all",
            "content.javascript.enabled":       True,
            "content.tls.certificate_errors":   "load-insecurely",
        },
        description="Local development: allow everything",
        category="dev",
    ),
    HostRule(
        pattern="127.0.0.1",
        settings={
            "content.cookies.accept":           "all",
            "content.javascript.enabled":       True,
            "content.tls.certificate_errors":   "load-insecurely",
        },
        description="Local development (IPv4): allow everything",
        category="dev",
    ),
    HostRule(
        pattern="file://*",
        settings={
            "content.javascript.enabled": True,
        },
        description="Local HTML files may need JS (e.g. readability output)",
        category="local",
    ),
]

#: Login/auth sites that need cookies and JS.  Loaded for STANDARD+.
LOGIN_RULES: List[HostRule] = [
    HostRule(
        pattern="*.google.com",
        settings={"content.cookies.accept": "all"},
        description="Google login requires cookies",
        category="login",
    ),
    HostRule(
        pattern="accounts.google.com",
        settings={
            "content.cookies.accept":     "all",
            "content.javascript.enabled": True,
        },
        description="Google account pages require JS + cookies",
        category="login",
    ),
    HostRule(
        pattern="*.github.com",
        settings={"content.cookies.accept": "all"},
        description="GitHub login requires cookies",
        category="login",
    ),
    HostRule(
        pattern="*.gitlab.com",
        settings={"content.cookies.accept": "all"},
        description="GitLab login requires cookies",
        category="login",
    ),
]

#: Communication/social sites.
SOCIAL_RULES: List[HostRule] = [
    HostRule(
        pattern="discord.com",
        settings={
            "content.cookies.accept":     "all",
            "content.javascript.enabled": True,
        },
        description="Discord requires JS + cookies",
        category="social",
    ),
    HostRule(
        pattern="*.notion.so",
        settings={
            "content.cookies.accept":     "all",
            "content.javascript.enabled": True,
        },
        description="Notion requires JS",
        category="social",
    ),
    HostRule(
        pattern="www.bilibili.com",
        settings={
            "content.cookies.accept":     "all",
            "content.javascript.enabled": True,
            "content.autoplay":           False,
        },
        description="Bilibili: allow JS/cookies, block autoplay",
        category="media",
    ),
]

#: Media sites (YouTube etc.) — need cookies for auth, block autoplay.
MEDIA_RULES: List[HostRule] = [
    HostRule(
        pattern="www.youtube.com",
        settings={
            "content.cookies.accept":     "all",
            "content.javascript.enabled": True,
            "content.autoplay":           False,
        },
        description="YouTube: cookies + JS, but no autoplay",
        category="media",
    ),
    HostRule(
        pattern="*.twitch.tv",
        settings={
            "content.cookies.accept":     "all",
            "content.javascript.enabled": True,
        },
        description="Twitch requires JS + cookies for streams",
        category="media",
    ),
]


# ─────────────────────────────────────────────
# Registry
# ─────────────────────────────────────────────
class HostPolicyRegistry:
    """
    Central registry of per-host rules.

    Supports:
      - registering rules individually or in bulk
      - querying by category
      - enabling/disabling rules without deletion
      - iterating active rules for the orchestrator
    """

    def __init__(self) -> None:
        self._rules: List[HostRule] = []

    def register(self, rule: HostRule) -> "HostPolicyRegistry":
        self._rules.append(rule)
        return self

    def register_many(self, rules: List[HostRule]) -> "HostPolicyRegistry":
        self._rules.extend(rules)
        return self

    def by_category(self, category: str) -> List[HostRule]:
        return [r for r in self._rules if r.category == category and r.enabled]

    def categories(self) -> List[str]:
        return list({r.category for r in self._rules})

    def active(self) -> Iterator[HostRule]:
        """Yield only enabled rules."""
        return (r for r in self._rules if r.enabled)

    def summary(self) -> str:
        cats = {}
        for r in self._rules:
            cats.setdefault(r.category, 0)
            cats[r.category] += 1
        return "  ".join(f"{k}:{v}" for k, v in sorted(cats.items()))

    def __len__(self) -> int:
        return sum(1 for r in self._rules if r.enabled)


# ─────────────────────────────────────────────
# Factory
# ─────────────────────────────────────────────
def build_default_host_registry(
    include_login: bool = True,
    include_social: bool = True,
    include_media: bool = True,
) -> HostPolicyRegistry:
    """
    Build the default host policy registry.

    Args:
        include_login:  Include common login/auth site rules.
        include_social: Include communication/social site rules.
        include_media:  Include media site rules.
    """
    registry = HostPolicyRegistry()
    registry.register_many(ALWAYS_RULES)

    if include_login:
        registry.register_many(LOGIN_RULES)
    if include_social:
        registry.register_many(SOCIAL_RULES)
    if include_media:
        registry.register_many(MEDIA_RULES)

    logger.debug("[HostRegistry] %d rules loaded: %s", len(registry), registry.summary())
    return registry


