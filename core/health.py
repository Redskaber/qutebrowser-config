"""
core/health.py
==============
Configuration Health Check System

Validates that the resolved config is internally consistent and
catches common mistakes before they reach qutebrowser.

Architecture:
  HealthCheck (ABC) → HealthChecker → HealthReport

Principle: fail fast, fail clearly.  Every check has a name and
a severity so operators know what is critical vs cosmetic.

Patterns: Visitor, Chain of Responsibility, Data Object
"""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Any, Dict, List

logger = logging.getLogger("qute.health")

ConfigDict = Dict[str, Any]


class Severity(Enum):
    INFO    = auto()   # cosmetic / informational
    WARNING = auto()   # works but suboptimal
    ERROR   = auto()   # will likely cause qutebrowser errors


@dataclass(frozen=True)
class HealthIssue:
    """A single diagnostic finding."""
    check:    str
    severity: Severity
    message:  str
    key:      str = ""

    def __str__(self) -> str:
        icon = {Severity.INFO: "ℹ", Severity.WARNING: "⚠", Severity.ERROR: "✗"}[self.severity]
        loc  = f" [{self.key}]" if self.key else ""
        return f"{icon} {self.check}{loc}: {self.message}"


@dataclass
class HealthReport:
    """Aggregate result of all health checks."""
    issues: List[HealthIssue] = field(default_factory=list)

    def add(self, issue: HealthIssue) -> None:
        self.issues.append(issue)

    @property
    def errors(self) -> List[HealthIssue]:
        return [i for i in self.issues if i.severity == Severity.ERROR]

    @property
    def warnings(self) -> List[HealthIssue]:
        return [i for i in self.issues if i.severity == Severity.WARNING]

    @property
    def ok(self) -> bool:
        return len(self.errors) == 0

    def summary(self) -> str:
        n_e = len(self.errors)
        n_w = len(self.warnings)
        n_i = len([i for i in self.issues if i.severity == Severity.INFO])
        status = "✓ HEALTHY" if self.ok else f"✗ {n_e} ERROR(S)"
        return (
            f"{status}  warnings={n_w}  info={n_i}\n"
            + "\n".join(f"  {i}" for i in self.issues if i.severity != Severity.INFO)
        )


class HealthCheck(ABC):
    """Base class for a single health check."""
    name: str = "unnamed"
    description: str = ""

    @abstractmethod
    def run(self, settings: ConfigDict, report: HealthReport) -> None:
        """Run this check; append any issues to report."""
        ...


# ─────────────────────────────────────────────
# Built-in Checks
# ─────────────────────────────────────────────

class BlockingEnabledCheck(HealthCheck):
    """Warn if content blocking is disabled."""
    name = "blocking-enabled"
    description = "Content blocking should be enabled for privacy"

    def run(self, settings: ConfigDict, report: HealthReport) -> None:
        if not settings.get("content.blocking.enabled", True):
            report.add(HealthIssue(
                check=self.name,
                severity=Severity.WARNING,
                message="content.blocking.enabled is False — adblock disabled",
                key="content.blocking.enabled",
            ))


class JavaScriptClipboardCheck(HealthCheck):
    """Warn if JS clipboard access is enabled globally."""
    name = "js-clipboard"
    description = "JavaScript clipboard access should be restricted"

    def run(self, settings: ConfigDict, report: HealthReport) -> None:
        val = settings.get("content.javascript.clipboard", "none")
        if val not in ("none", "access"):
            report.add(HealthIssue(
                check=self.name,
                severity=Severity.WARNING,
                message=f"content.javascript.clipboard={val!r} allows write access",
                key="content.javascript.clipboard",
            ))


class SearchEngineDefaultCheck(HealthCheck):
    """Error if no DEFAULT search engine is defined."""
    name = "search-default"
    description = "A DEFAULT search engine must exist"

    def run(self, settings: ConfigDict, report: HealthReport) -> None:
        engines = settings.get("url.searchengines", {})
        if not isinstance(engines, dict) or "DEFAULT" not in engines:
            report.add(HealthIssue(
                check=self.name,
                severity=Severity.ERROR,
                message="url.searchengines missing 'DEFAULT' key",
                key="url.searchengines",
            ))


class WebRTCPolicyCheck(HealthCheck):
    """Warn if WebRTC can leak local IP."""
    name = "webrtc-policy"
    description = "WebRTC should not leak local IP addresses"

    _SAFE = {
        "default-public-interface-only",
        "disable-non-proxied-udp",
        "disable-udp",
    }

    def run(self, settings: ConfigDict, report: HealthReport) -> None:
        policy = settings.get("content.webrtc_ip_handling_policy", "default")
        if policy not in self._SAFE:
            report.add(HealthIssue(
                check=self.name,
                severity=Severity.WARNING,
                message=(
                    f"webrtc_ip_handling_policy={policy!r} may leak local IP; "
                    f"consider one of {sorted(self._SAFE)}"
                ),
                key="content.webrtc_ip_handling_policy",
            ))


class CookieAcceptCheck(HealthCheck):
    """Info if third-party cookies are fully allowed."""
    name = "cookie-accept"
    description = "Warn when all cookies are accepted globally"

    def run(self, settings: ConfigDict, report: HealthReport) -> None:
        policy = settings.get("content.cookies.accept", "no-3rdparty")
        if policy == "all":
            report.add(HealthIssue(
                check=self.name,
                severity=Severity.INFO,
                message="content.cookies.accept=all — tracking cookies accepted globally",
                key="content.cookies.accept",
            ))


class StartPageCheck(HealthCheck):
    """Warn if start pages list is empty."""
    name = "start-pages"
    description = "At least one start page should be configured"

    def run(self, settings: ConfigDict, report: HealthReport) -> None:
        pages = settings.get("url.start_pages", [])
        if not pages:
            report.add(HealthIssue(
                check=self.name,
                severity=Severity.WARNING,
                message="url.start_pages is empty",
                key="url.start_pages",
            ))


# ─────────────────────────────────────────────
# Health Checker (runner)
# ─────────────────────────────────────────────

class HealthChecker:
    """
    Runs all registered health checks and produces a HealthReport.

    Usage::

        checker = HealthChecker.default()
        report  = checker.check(merged_settings)
        print(report.summary())
    """

    def __init__(self) -> None:
        self._checks: List[HealthCheck] = []

    def add(self, check: HealthCheck) -> "HealthChecker":
        self._checks.append(check)
        return self

    def check(self, settings: ConfigDict) -> HealthReport:
        report = HealthReport()
        for c in self._checks:
            try:
                c.run(settings, report)
            except Exception as exc:
                logger.error("[HealthChecker] check %r raised: %s", c.name, exc)
                report.add(HealthIssue(
                    check=c.name,
                    severity=Severity.ERROR,
                    message=f"check itself raised an exception: {exc}",
                ))
        return report

    @classmethod
    def default(cls) -> "HealthChecker":
        """Build a checker with all built-in checks."""
        return (
            cls()
            .add(BlockingEnabledCheck())
            .add(JavaScriptClipboardCheck())
            .add(SearchEngineDefaultCheck())
            .add(WebRTCPolicyCheck())
            .add(CookieAcceptCheck())
            .add(StartPageCheck())
        )
