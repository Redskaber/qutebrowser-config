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

Built-in checks (v5):
  BlockingEnabledCheck        — content.blocking.enabled should be True
  SearchEngineDefaultCheck    — url.searchengines must have DEFAULT key
  SearchEngineUrlCheck        — all engine URLs must contain '{}'
  WebRTCPolicyCheck           — webrtc_ip_handling_policy leak risk
  CookieAcceptCheck           — all-cookie-accept is suspicious
  StartPageCheck              — url.start_pages should not be empty
  EditorCommandCheck          — editor.command must contain "{}" placeholder
  DownloadDirCheck            — downloads.location.directory should not be /tmp
  TabTitleFormatCheck         — tabs.title.format should reference {current_title}
"""

from __future__ import annotations

import logging
import os
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
    def infos(self) -> List[HealthIssue]:
        return [i for i in self.issues if i.severity == Severity.INFO]

    @property
    def ok(self) -> bool:
        return len(self.errors) == 0

    def summary(self) -> str:
        n_e = len(self.errors)
        n_w = len(self.warnings)
        n_i = len(self.infos)
        status = "✓ HEALTHY" if self.ok else f"✗ {n_e} ERROR(S)"
        lines = [f"{status}  warnings={n_w}  info={n_i}"]
        for i in self.issues:
            if i.severity != Severity.INFO:
                lines.append(f"  {i}")
        return "\n".join(lines)

    def full_report(self) -> str:
        """Full report including INFO-level findings."""
        if not self.issues:
            return "✓ All health checks passed — no issues found."
        lines = [self.summary()]
        if self.infos:
            lines.append("  Info:")
            lines.extend(f"    {i}" for i in self.infos)
        return "\n".join(lines)


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
    description = "content.blocking.enabled should be True for privacy"

    def run(self, settings: ConfigDict, report: HealthReport) -> None:
        enabled = settings.get("content.blocking.enabled", True)
        if not enabled:
            report.add(HealthIssue(
                check=self.name,
                severity=Severity.WARNING,
                message="content.blocking.enabled=False — ad/tracker blocking is OFF",
                key="content.blocking.enabled",
            ))


class SearchEngineDefaultCheck(HealthCheck):
    """Error if no DEFAULT search engine is set."""
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


class SearchEngineUrlCheck(HealthCheck):
    """
    Warn if any search engine URL template does not contain '{}'.

    Without '{}', searches silently go to the engine's homepage.
    """
    name = "search-engine-urls"
    description = "All search engine URL templates must contain '{}'"

    def run(self, settings: ConfigDict, report: HealthReport) -> None:
        engines = settings.get("url.searchengines", {})
        if not isinstance(engines, dict):
            return
        bad = [k for k, v in engines.items() if isinstance(v, str) and "{}" not in v]
        for key in bad:
            report.add(HealthIssue(
                check=self.name,
                severity=Severity.WARNING,
                message=(
                    f"url.searchengines[{key!r}]={engines[key]!r} "
                    "has no '{}' placeholder — searches go to homepage"
                ),
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


class EditorCommandCheck(HealthCheck):
    """
    Error if editor.command is set but does not contain the '{}' placeholder.

    qutebrowser replaces '{}' with the temp file path; without it, the editor
    receives no file argument and the edit workflow silently fails.
    """
    name = "editor-command"
    description = "editor.command must contain '{}' placeholder"

    def run(self, settings: ConfigDict, report: HealthReport) -> None:
        cmd = settings.get("editor.command")
        if cmd is None:
            return   # not set — qutebrowser uses its own default
        if not isinstance(cmd, list):
            report.add(HealthIssue(
                check=self.name,
                severity=Severity.ERROR,
                message=f"editor.command must be a list, got {type(cmd).__name__}",
                key="editor.command",
            ))
            return
        if not cmd:
            report.add(HealthIssue(
                check=self.name,
                severity=Severity.ERROR,
                message="editor.command is an empty list",
                key="editor.command",
            ))
            return
        if not any("{}" in str(part) for part in cmd):
            report.add(HealthIssue(
                check=self.name,
                severity=Severity.ERROR,
                message=(
                    f"editor.command {cmd!r} has no '{{}}' placeholder — "
                    "qutebrowser will not pass the temp file to the editor"
                ),
                key="editor.command",
            ))


class DownloadDirCheck(HealthCheck):
    """
    Warn if downloads.location.directory is /tmp or an unsafe path.
    Files in /tmp are cleaned on reboot.
    """
    name = "download-dir"
    description = "downloads.location.directory should be a persistent path"

    _UNSAFE: frozenset[str] = frozenset({"/tmp", "/var/tmp", "/dev/shm"})

    def run(self, settings: ConfigDict, report: HealthReport) -> None:
        dl_dir = settings.get("downloads.location.directory")
        if dl_dir is None:
            return
        expanded = os.path.expanduser(str(dl_dir))
        try:
            resolved = os.path.realpath(expanded)
        except OSError:
            resolved = expanded
        if any(resolved == u or resolved.startswith(u + "/") for u in self._UNSAFE):
            report.add(HealthIssue(
                check=self.name,
                severity=Severity.WARNING,
                message=(
                    f"downloads.location.directory={dl_dir!r} resolves to {resolved!r} "
                    "— files in /tmp are lost on reboot"
                ),
                key="downloads.location.directory",
            ))


class TabTitleFormatCheck(HealthCheck):
    """
    Info if tabs.title.format does not include {current_title}.
    Without it, all tabs show the same label (confusing UX).
    """
    name = "tab-title-format"
    description = "tabs.title.format should include {current_title}"

    def run(self, settings: ConfigDict, report: HealthReport) -> None:
        fmt = settings.get("tabs.title.format")
        if fmt is not None and "{current_title}" not in str(fmt):
            report.add(HealthIssue(
                check=self.name,
                severity=Severity.INFO,
                message=(
                    f"tabs.title.format={fmt!r} does not include "
                    "'{current_title}' — tabs may show identical labels"
                ),
                key="tabs.title.format",
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
        if not report.ok:
            logger.warning(report.summary())

    Checks are run in registration order; exceptions inside individual
    checks are caught and recorded as ERROR-severity issues so one bad
    check cannot prevent others from running.
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
                logger.exception("[HealthChecker] check %r raised unexpectedly", c.name)
                report.add(HealthIssue(
                    check=c.name,
                    severity=Severity.ERROR,
                    message=f"Check raised exception: {exc}",
                ))
        return report

    @classmethod
    def default(cls) -> "HealthChecker":
        """Return a HealthChecker pre-loaded with all built-in checks."""
        return (
            cls()
            .add(BlockingEnabledCheck())
            .add(SearchEngineDefaultCheck())
            .add(SearchEngineUrlCheck())
            .add(WebRTCPolicyCheck())
            .add(CookieAcceptCheck())
            .add(StartPageCheck())
            .add(EditorCommandCheck())
            .add(DownloadDirCheck())
            .add(TabTitleFormatCheck())
        )
