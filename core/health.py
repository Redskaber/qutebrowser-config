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

Built-in checks (v8 — 15 total):
  BlockingEnabledCheck        — content.blocking.enabled should be True
  BlockingListCheck           — content.blocking.adblock.lists must be non-empty
  SearchEngineDefaultCheck    — url.searchengines must have DEFAULT key
  SearchEngineUrlCheck        — all engine URLs must contain '{}'
  WebRTCPolicyCheck           — webrtc_ip_handling_policy leak risk
  CookieAcceptCheck           — all-cookie-accept is informational
  StartPageCheck              — url.start_pages should not be empty
  EditorCommandCheck          — editor.command must be a list with '{}' placeholder
  DownloadDirCheck            — downloads.location.directory should not be /tmp
  TabTitleFormatCheck         — tabs.title.format should reference {current_title}
  ProxySchemeCheck            — content.proxy must start with a valid scheme
  ZoomDefaultCheck            — zoom.default must end with '%'
  FontFamilyCheck      [NEW]  — fonts.default_family must not be empty string
  SpellcheckLangCheck  [NEW]  — spellcheck.languages entries should look like BCP-47 tags
  ContentHeaderCheck   [NEW]  — content.headers.user_agent should not be empty string
"""

from __future__ import annotations

import logging
import os
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Any, Dict, List, Optional

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
        if not self.issues:
            return "✓ Health: all checks passed"
        lines = [f"Health: {len(self.errors)} error(s), {len(self.warnings)} warning(s)"]
        for issue in sorted(self.issues, key=lambda i: i.severity.value, reverse=True):
            lines.append(f"  {issue}")
        return "\n".join(lines)

    def full_report(self) -> str:
        """Extended report including all severities (errors, warnings, infos)."""
        if not self.issues:
            return "✓ Health: all checks passed (0 issues)"
        lines = [
            f"Health Report: {len(self.errors)} error(s), "
            f"{len(self.warnings)} warning(s), {len(self.infos)} info(s)"
        ]
        for severity_label, bucket in (
            ("ERRORS",   self.errors),
            ("WARNINGS", self.warnings),
            ("INFO",     self.infos),
        ):
            if bucket:
                lines.append(f"\n  {severity_label}:")
                for issue in bucket:
                    lines.append(f"    {issue}")
        return "\n".join(lines)

    def __len__(self) -> int:
        return len(self.issues)


# ─────────────────────────────────────────────
# Health Check ABC
# ─────────────────────────────────────────────
class HealthCheck(ABC):
    """
    Abstract health check.

    Two equivalent interfaces — use whichever suits your style:

    **Functional** (return-based):
        Override ``check(config) -> List[HealthIssue]``.
        The base ``run()`` calls it automatically.

    **Imperative** (report-based, preferred for custom/extension checks):
        Override ``run(settings, report)`` and call ``report.add(...)``
        directly.  Leave ``check()`` returning ``[]``.

    All built-in checks use the functional style.
    Test helpers and external extensions may use the imperative style.
    """

    @property
    @abstractmethod
    def name(self) -> str:
        ...

    def check(self, config: ConfigDict) -> List[HealthIssue]:
        """
        Inspect ``config`` and return a list of HealthIssue objects.
        Empty list = check passed.

        Override this (functional style) *or* override ``run()``
        (imperative style).
        """
        return []

    def run(self, settings: ConfigDict, report: "HealthReport") -> None:
        """
        Run the check and add any findings to ``report``.

        Default implementation delegates to ``check()``.  Override
        directly for imperative-style checks.
        """
        for issue in self.check(settings):
            report.add(issue)

    # Helper for subclasses
    def _get(self, config: ConfigDict, key: str) -> Any:
        """
        Retrieve a setting from a merged config.
        Supports both flat (key=value) and nested {"settings": {key: value}}.
        """
        flat   = config.get(key)
        if flat is not None:
            return flat
        return config.get("settings", {}).get(key)


# ─────────────────────────────────────────────
# Built-in Checks
# ─────────────────────────────────────────────

class BlockingEnabledCheck(HealthCheck):
    """content.blocking.enabled should be True to block ads/trackers."""
    name = "BlockingEnabled"  # type: ignore[override]

    def check(self, config: ConfigDict) -> List[HealthIssue]:
        val = self._get(config, "content.blocking.enabled")
        if val is False:
            return [HealthIssue(
                check=self.name,
                severity=Severity.WARNING,
                message="content.blocking.enabled is False — ads and trackers not blocked",
                key="content.blocking.enabled",
            )]
        return []


class BlockingListCheck(HealthCheck):
    """content.blocking.adblock.lists should be non-empty when blocking is enabled."""
    name = "BlockingList"  # type: ignore[override]

    def check(self, config: ConfigDict) -> List[HealthIssue]:
        enabled = self._get(config, "content.blocking.enabled")
        if not enabled:
            return []   # blocking disabled; list is irrelevant
        lists = self._get(config, "content.blocking.adblock.lists")
        if lists is not None and len(lists) == 0:
            return [HealthIssue(
                check=self.name,
                severity=Severity.WARNING,
                message=(
                    "content.blocking.adblock.lists is empty — "
                    "blocking is enabled but no filter lists are configured"
                ),
                key="content.blocking.adblock.lists",
            )]
        return []


class SearchEngineDefaultCheck(HealthCheck):
    """url.searchengines must contain a 'DEFAULT' key."""
    name = "SearchEngineDefault"  # type: ignore[override]

    def check(self, config: ConfigDict) -> List[HealthIssue]:
        engines = self._get(config, "url.searchengines")
        if engines is None or (isinstance(engines, dict) and "DEFAULT" not in engines):
            return [HealthIssue(
                check=self.name,
                severity=Severity.ERROR,
                message="url.searchengines is missing the 'DEFAULT' key — address bar search will fail",
                key="url.searchengines",
            )]
        return []


class SearchEngineUrlCheck(HealthCheck):
    """All search engine URL templates must contain '{}'."""
    name = "SearchEngineUrl"  # type: ignore[override]

    def check(self, config: ConfigDict) -> List[HealthIssue]:
        engines = self._get(config, "url.searchengines")
        if not isinstance(engines, dict):
            return []
        issues: List[HealthIssue] = []
        for name, url in engines.items():
            if isinstance(url, str) and "{}" not in url:
                issues.append(HealthIssue(
                    check=self.name,
                    severity=Severity.ERROR,
                    message=f"Search engine '{name}' URL missing '{{}}' placeholder: {url!r}",
                    key="url.searchengines",
                ))
        return issues


class WebRTCPolicyCheck(HealthCheck):
    """WebRTC policy should not expose local IPs."""
    name = "WebRTCPolicy"  # type: ignore[override]

    _RISKY = {"default", "default-public-and-private-interfaces"}

    def check(self, config: ConfigDict) -> List[HealthIssue]:
        val = self._get(config, "content.webrtc_ip_handling_policy")
        if val in self._RISKY:
            return [HealthIssue(
                check=self.name,
                severity=Severity.WARNING,
                message=(
                    f"webrtc_ip_handling_policy={val!r} may leak local IP addresses; "
                    "consider 'default-public-interface-only' or 'disable-non-proxied-udp'"
                ),
                key="content.webrtc_ip_handling_policy",
            )]
        return []


class CookieAcceptCheck(HealthCheck):
    """Accepting all cookies from all sites is suspicious."""
    name = "CookieAccept"  # type: ignore[override]

    def check(self, config: ConfigDict) -> List[HealthIssue]:
        val = self._get(config, "content.cookies.accept")
        if val == "all":
            return [HealthIssue(
                check=self.name,
                severity=Severity.INFO,
                message=(
                    "content.cookies.accept='all' is set globally — "
                    "third-party trackers will be allowed on all sites"
                ),
                key="content.cookies.accept",
            )]
        return []


class StartPageCheck(HealthCheck):
    """url.start_pages should not be empty."""
    name = "StartPage"  # type: ignore[override]

    def check(self, config: ConfigDict) -> List[HealthIssue]:
        val = self._get(config, "url.start_pages")
        if isinstance(val, list) and len(val) == 0:
            return [HealthIssue(
                check=self.name,
                severity=Severity.WARNING,
                message="url.start_pages is empty — qutebrowser may start with a blank tab",
                key="url.start_pages",
            )]
        return []


class EditorCommandCheck(HealthCheck):
    """editor.command must be a list containing '{}'."""
    name = "EditorCommand"  # type: ignore[override]

    def check(self, config: ConfigDict) -> List[HealthIssue]:
        val = self._get(config, "editor.command")
        issues: List[HealthIssue] = []

        if val is None:
            return []

        if not isinstance(val, list):
            issues.append(HealthIssue(
                check=self.name,
                severity=Severity.ERROR,
                message=f"editor.command must be a list, got {type(val).__name__}",
                key="editor.command",
            ))
            return issues

        # Check that '{}' placeholder is present somewhere in the command
        has_placeholder = any("{}" in str(arg) for arg in val)
        if not has_placeholder:
            issues.append(HealthIssue(
                check=self.name,
                severity=Severity.ERROR,
                message=(
                    f"editor.command {val!r} is missing '{{}}' placeholder — "
                    "qutebrowser won't be able to pass the temp file path"
                ),
                key="editor.command",
            ))

        return issues


class DownloadDirCheck(HealthCheck):
    """downloads.location.directory should not be /tmp (files deleted on reboot)."""
    name = "DownloadDir"  # type: ignore[override]

    def check(self, config: ConfigDict) -> List[HealthIssue]:
        val = self._get(config, "downloads.location.directory")
        if isinstance(val, str):
            normalized = os.path.normpath(os.path.expanduser(val))
            if normalized in {"/tmp", "/var/tmp"} or any(
                normalized.startswith(p + os.sep) for p in ("/tmp", "/var/tmp")
            ):
                return [HealthIssue(
                    check=self.name,
                    severity=Severity.WARNING,
                    message=f"downloads.location.directory={val!r} is a temp dir — files may be lost",
                    key="downloads.location.directory",
                )]
        return []


class TabTitleFormatCheck(HealthCheck):
    """tabs.title.format should reference {current_title}."""
    name = "TabTitleFormat"  # type: ignore[override]

    def check(self, config: ConfigDict) -> List[HealthIssue]:
        val = self._get(config, "tabs.title.format")
        if isinstance(val, str) and "{current_title}" not in val:
            return [HealthIssue(
                check=self.name,
                severity=Severity.INFO,
                message=(
                    f"tabs.title.format={val!r} does not include {{current_title}} — "
                    "tab bar will not show page titles"
                ),
                key="tabs.title.format",
            )]
        return []


class ProxySchemeCheck(HealthCheck):
    """content.proxy must be 'system', 'none', or start with a valid scheme."""
    name = "ProxyScheme"  # type: ignore[override]

    _VALID_KEYWORDS = {"system", "none"}
    _VALID_SCHEMES  = ("socks5://", "socks://", "http://", "https://")

    def check(self, config: ConfigDict) -> List[HealthIssue]:
        val = self._get(config, "content.proxy")
        if val is None:
            return []

        # Lists are not valid for content.proxy
        if isinstance(val, list):
            return [HealthIssue(
                check=self.name,
                severity=Severity.ERROR,
                message=(
                    "content.proxy is a list — qutebrowser requires a single string. "
                    f"Got: {val!r}"
                ),
                key="content.proxy",
            )]

        if not isinstance(val, str):
            return [HealthIssue(
                check=self.name,
                severity=Severity.ERROR,
                message=f"content.proxy must be a string, got {type(val).__name__}: {val!r}",
                key="content.proxy",
            )]

        if val in self._VALID_KEYWORDS:
            return []

        if any(val.startswith(s) for s in self._VALID_SCHEMES):
            return []

        return [HealthIssue(
            check=self.name,
            severity=Severity.ERROR,
            message=(
                f"content.proxy={val!r} is not a valid proxy value. "
                f"Expected one of {self._VALID_KEYWORDS} or a URL starting with "
                f"{self._VALID_SCHEMES}"
            ),
            key="content.proxy",
        )]


class ZoomDefaultCheck(HealthCheck):
    """zoom.default must be a percentage string like '100%'."""
    name = "ZoomDefault"  # type: ignore[override]

    def check(self, config: ConfigDict) -> List[HealthIssue]:
        val = self._get(config, "zoom.default")
        if val is None:
            return []
        if not isinstance(val, str) or not val.endswith("%"):
            return [HealthIssue(
                check=self.name,
                severity=Severity.ERROR,
                message=(
                    f"zoom.default={val!r} is not a valid zoom string. "
                    "Expected a percentage like '100%', '110%', etc."
                ),
                key="zoom.default",
            )]
        # Also check it's a reasonable number
        try:
            pct = int(val.rstrip("%"))
            if pct < 10 or pct > 500:
                return [HealthIssue(
                    check=self.name,
                    severity=Severity.WARNING,
                    message=f"zoom.default={val!r} is outside the reasonable range 10%–500%",
                    key="zoom.default",
                )]
        except ValueError:
            return [HealthIssue(
                check=self.name,
                severity=Severity.ERROR,
                message=f"zoom.default={val!r} is not parseable as an integer percentage",
                key="zoom.default",
            )]
        return []


class FontFamilyCheck(HealthCheck):
    """fonts.default_family must not be set to an empty string."""
    name = "FontFamily"  # type: ignore[override]

    def check(self, config: ConfigDict) -> List[HealthIssue]:
        val = self._get(config, "fonts.default_family")
        if val is None:
            return []
        if not isinstance(val, str):
            return [HealthIssue(
                check=self.name,
                severity=Severity.WARNING,
                message=(
                    f"fonts.default_family must be a string, "
                    f"got {type(val).__name__}: {val!r}"
                ),
                key="fonts.default_family",
            )]
        if val.strip() == "":
            return [HealthIssue(
                check=self.name,
                severity=Severity.WARNING,
                message=(
                    "fonts.default_family is an empty string — "
                    "qutebrowser will fall back to a system default font"
                ),
                key="fonts.default_family",
            )]
        return []


class SpellcheckLangCheck(HealthCheck):
    """spellcheck.languages entries should look like valid BCP-47 language tags."""
    name = "SpellcheckLang"  # type: ignore[override]

    # A valid BCP-47 tag looks like: en-US, zh-CN, de-DE, fr-FR …
    # We check: 2-3 alpha + optional hyphen + 2-3 alpha/digit suffix
    import re as _re
    _LANG_RE = _re.compile(r"^[a-zA-Z]{2,3}(-[a-zA-Z0-9]{2,4})?$")

    def check(self, config: ConfigDict) -> List[HealthIssue]:
        langs = self._get(config, "spellcheck.languages")
        if langs is None:
            return []
        if not isinstance(langs, list):
            return [HealthIssue(
                check=self.name,
                severity=Severity.ERROR,
                message=(
                    f"spellcheck.languages must be a list, "
                    f"got {type(langs).__name__}: {langs!r}"
                ),
                key="spellcheck.languages",
            )]
        issues: List[HealthIssue] = []
        for tag in langs:
            if not isinstance(tag, str) or not self._LANG_RE.match(tag):
                issues.append(HealthIssue(
                    check=self.name,
                    severity=Severity.WARNING,
                    message=(
                        f"spellcheck.languages entry {tag!r} does not look like "
                        "a valid BCP-47 tag (e.g. 'en-US', 'zh-CN', 'de'). "
                        "Spellcheck for this language may silently fail."
                    ),
                    key="spellcheck.languages",
                ))
        return issues


class ContentHeaderCheck(HealthCheck):
    """content.headers.user_agent must not be set to an empty string."""
    name = "ContentHeader"  # type: ignore[override]

    def check(self, config: ConfigDict) -> List[HealthIssue]:
        val = self._get(config, "content.headers.user_agent")
        if val is None:
            return []
        if isinstance(val, str) and val.strip() == "":
            return [HealthIssue(
                check=self.name,
                severity=Severity.WARNING,
                message=(
                    "content.headers.user_agent is an empty string — "
                    "some sites may reject the request or break. "
                    "Use 'default' or a recognised UA string."
                ),
                key="content.headers.user_agent",
            )]
        return []


# ─────────────────────────────────────────────
# Health Checker
# ─────────────────────────────────────────────
class HealthChecker:
    """
    Runs a collection of HealthChecks against a merged ConfigDict
    and returns a HealthReport.

    Usage:
        checker = HealthChecker.default()
        report  = checker.check(merged_config["settings"])
        if not report.ok:
            logger.warning(report.summary())
    """

    def __init__(self, checks: Optional[List[HealthCheck]] = None) -> None:
        self._checks: List[HealthCheck] = list(checks) if checks is not None else []

    @classmethod
    def default(cls) -> "HealthChecker":
        """Return a HealthChecker pre-loaded with all v8 built-in checks (15 total)."""
        return cls([
            BlockingEnabledCheck(),
            BlockingListCheck(),
            SearchEngineDefaultCheck(),
            SearchEngineUrlCheck(),
            WebRTCPolicyCheck(),
            CookieAcceptCheck(),
            StartPageCheck(),
            EditorCommandCheck(),
            DownloadDirCheck(),
            TabTitleFormatCheck(),
            ProxySchemeCheck(),
            ZoomDefaultCheck(),
            FontFamilyCheck(),
            SpellcheckLangCheck(),
            ContentHeaderCheck(),
        ])

    def add(self, check: HealthCheck) -> "HealthChecker":
        """Fluent: add a custom check."""
        self._checks.append(check)
        return self

    def check(self, config: ConfigDict) -> HealthReport:
        """Run all checks and return an aggregated report."""
        report = HealthReport()
        for chk in self._checks:
            try:
                chk.run(config, report)
            except Exception as exc:
                logger.exception("[Health] check %r raised: %s", chk.name, exc)
                report.add(HealthIssue(
                    check=chk.name,
                    severity=Severity.ERROR,
                    message=f"check raised an exception: {exc}",
                ))

        for issue in report.issues:
            if issue.severity == Severity.ERROR:
                logger.error("[Health] %s", issue)
            elif issue.severity == Severity.WARNING:
                logger.warning("[Health] %s", issue)
            else:
                logger.info("[Health] %s", issue)

        logger.info("[Health] %d checks run, %d issue(s)", len(self._checks), len(report))
        return report
