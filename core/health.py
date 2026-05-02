"""
core/health.py
==============
Configuration Health Check System  (v9.1)

Validates that the resolved config is internally consistent and
catches common mistakes before they reach qutebrowser.

Architecture:
  HealthCheck (ABC) → HealthChecker → HealthReport

Principle: fail fast, fail clearly.  Every check has a name and
a severity so operators know what is critical vs cosmetic.

Patterns: Visitor, Chain of Responsibility, Data Object

Built-in checks (v9.1 — 18 total):
  ── v8 checks (15) ─────────────────────────────────────────────
  BlockingEnabledCheck        — content.blocking.enabled should be True
  BlockingListCheck           — content.blocking.adblock.lists must be non-empty
  SearchEngineDefaultCheck    — url.searchengines must have DEFAULT key
  SearchEngineUrlCheck        — all engine URLs must contain '{}'
  WebRTCPolicyCheck           — webrtc_ip_handling_policy leak risk
                                (now also flags bare "default" value)
  CookieAcceptCheck           — all-cookie-accept is informational
  StartPageCheck              — url.start_pages should not be empty
  EditorCommandCheck          — editor.command must be a list with '{}' placeholder
  DownloadDirCheck            — downloads.location.directory should not be /tmp
  TabTitleFormatCheck         — tabs.title.format should reference {current_title}
                                (INFO severity, not WARNING)
  ProxySchemeCheck            — content.proxy must start with a valid scheme
  ZoomDefaultCheck            — zoom.default must end with '%'
  FontFamilyCheck             — fonts.default_family must not be empty / wrong type
  SpellcheckLangCheck         — one issue per invalid BCP-47 tag (not one combined)
  ContentHeaderCheck          — content.headers.user_agent should not be empty string

  ── v9 checks (3 new) ───────────────────────────────────────────
  SearchEngineCountCheck      — url.searchengines should not exceed 50 entries
  ProxySchemeDetailCheck      — socks5/http proxy entries validated for host:port
  DownloadPromptCheck         — INFO if prompt=False and dir is still ~/Downloads

v9.1 changes (bug-fix release):
  - HealthCheck ABC migrated to PUSH model:
      abstract method is now ``run(settings, report)`` — appends issues directly
      to the HealthReport (zero, one, or many per invocation).
      The old ``check(config) → Optional[HealthIssue]`` is kept as a
      backward-compatible bridge that delegates to ``run()``.
  - HealthReport.full_report() added as alias for summary().
  - HealthChecker.check() calls hc.run(); exceptions are caught and recorded
      as ERROR issues instead of being silently discarded.
  - WebRTCPolicyCheck: bare "default" policy now triggers a warning.
  - TabTitleFormatCheck: severity downgraded from WARNING to INFO.
  - SpellcheckLangCheck: emits one HealthIssue per invalid tag (was one combined).
  - FontFamilyCheck: also warns on non-str type (was only empty-string check).
  - DownloadDirCheck: also catches /tmp/<subdir> patterns.
"""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum, auto
import re
from typing import Any, Dict, List, Optional, cast

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

    def __str__(self) -> str:
        icon = {
            Severity.INFO:    "ℹ",
            Severity.WARNING: "⚠",
            Severity.ERROR:   "✗",
        }[self.severity]
        return f"{icon} [{self.check}] {self.message}"


@dataclass
class HealthReport:
    """Aggregated result of all health checks."""
    issues: List[HealthIssue] = field(default_factory=list[HealthIssue])

    # ── Accessors ─────────────────────────────────────────────────────

    @property
    def ok(self) -> bool:
        return not any(i.severity == Severity.ERROR for i in self.issues)

    @property
    def errors(self) -> List[HealthIssue]:
        return [i for i in self.issues if i.severity == Severity.ERROR]

    @property
    def warnings(self) -> List[HealthIssue]:
        return [i for i in self.issues if i.severity == Severity.WARNING]

    @property
    def infos(self) -> List[HealthIssue]:
        return [i for i in self.issues if i.severity == Severity.INFO]

    # ── Reporting ─────────────────────────────────────────────────────

    def summary(self) -> str:
        """
        Multi-line health summary.

        Categorised output: errors first, then warnings, then infos.
        Returns a single "all clear" line when no issues are found.
        """
        if not self.issues:
            return "✓ All health checks passed (0 issues)"

        n_e = len(self.errors)
        n_w = len(self.warnings)
        n_i = len(self.infos)
        header = (
            f"{'✓' if self.ok else '✗'} "
            f"{n_e} error(s) · {n_w} warning(s) · {n_i} info(s)"
        )
        lines = [header]
        for issue in self.errors + self.warnings + self.infos:
            lines.append(f"  {issue}")
        return "\n".join(lines)

    def full_report(self) -> str:
        """Alias for summary() — full categorised report string."""
        return self.summary()

    def add(self, issue: HealthIssue) -> None:
        self.issues.append(issue)


# ─────────────────────────────────────────────
# Health Check Abstraction  (v9.1 — push model)
# ─────────────────────────────────────────────

class HealthCheck(ABC):
    """
    Base class for all health checks.

    Push model (v9.1): subclasses implement ``run(settings, report)`` which
    appends HealthIssue objects directly to the report.  A single invocation
    may emit zero, one, or many issues.

    Backward-compat bridge: the legacy ``check(config)`` pull-model method is
    preserved — it delegates to ``run()`` and returns the first issue (or None).
    Callers that used the old one-issue-per-call API continue to work unchanged.
    """

    @property
    @abstractmethod
    def name(self) -> str: ...

    @abstractmethod
    def run(self, settings: ConfigDict, report: HealthReport) -> None:
        """
        Push model: inspect *settings* and append issues to *report*.

        Guidelines:
          - Call ``report.add(self._error(...))``, ``self._warning()``, or
            ``self._info()`` for every issue found.
          - Do NOT raise exceptions; surface problems as HealthIssue entries.
          - Return early (``return``) when nothing is wrong.
        """
        ...

    # ── Legacy bridge ─────────────────────────────────────────────────

    def check(self, config: ConfigDict) -> Optional[HealthIssue]:
        """
        Legacy pull-model bridge (v8 API).

        Runs ``run()`` against a temporary report and returns the first
        issue found, or None.  Retained for backward compatibility with
        any callers that used the old single-issue-per-check API.
        """
        tmp = HealthReport()
        self.run(config, tmp)
        return tmp.issues[0] if tmp.issues else None

    # ── Helpers ───────────────────────────────────────────────────────

    def _issue(self, severity: Severity, message: str) -> HealthIssue:
        return HealthIssue(check=self.name, severity=severity, message=message)

    def _error(self, message: str) -> HealthIssue:
        return self._issue(Severity.ERROR, message)

    def _warning(self, message: str) -> HealthIssue:
        return self._issue(Severity.WARNING, message)

    def _info(self, message: str) -> HealthIssue:
        return self._issue(Severity.INFO, message)


# ─────────────────────────────────────────────
# Built-in Checks (v9.1 — push model)
# ─────────────────────────────────────────────

class BlockingEnabledCheck(HealthCheck):

    @property
    def name(self) -> str:
        return "blocking_enabled"

    def run(self, settings: ConfigDict, report: HealthReport) -> None:
        if not settings.get("content.blocking.enabled", True):
            report.add(self._warning(
                "content.blocking.enabled is False — ad blocking is disabled"
            ))


class BlockingListCheck(HealthCheck):

    @property
    def name(self) -> str:
        return "blocking_lists"

    def run(self, settings: ConfigDict, report: HealthReport) -> None:
        lists = settings.get("content.blocking.adblock.lists", [])
        if not lists:
            report.add(self._warning(
                "content.blocking.adblock.lists is empty — no ad block lists configured"
            ))


class SearchEngineDefaultCheck(HealthCheck):

    @property
    def name(self) -> str:
        return "search_engine_default"

    def run(self, settings: ConfigDict, report: HealthReport) -> None:
        engines = settings.get("url.searchengines", {})
        if not isinstance(engines, dict) or "DEFAULT" not in engines:
            report.add(self._error(
                "url.searchengines is missing a 'DEFAULT' key — "
                "address bar searches will fail"
            ))


class SearchEngineUrlCheck(HealthCheck):

    @property
    def name(self) -> str:
        return "search_engine_urls"

    def run(self, settings: ConfigDict, report: HealthReport) -> None:
        engines = settings.get("url.searchengines", {})
        bad = [k for k, v in engines.items() if isinstance(v, str) and "{}" not in v]
        if bad:
            report.add(self._error(
                f"Search engine URL(s) missing '{{}}' placeholder: {bad}"
            ))


class WebRTCPolicyCheck(HealthCheck):
    """
    Warn when the WebRTC IP-handling policy may leak the real local IP address.

    v9.1: bare "default" is also considered risky (it exposes all interfaces
    in most Chromium builds).  Safe values are "default-public-interface-only"
    and "disable-non-proxied-udp".
    """

    @property
    def name(self) -> str:
        return "webrtc_policy"

    _RISKY = {
        "all-interfaces",
        "default-public-and-private-interfaces",
        "default",  # bare "default" also leaks local IPs in most builds
    }

    def run(self, settings: ConfigDict, report: HealthReport) -> None:
        val = settings.get("content.webrtc_ip_handling_policy", "")
        if val in self._RISKY:
            report.add(self._warning(
                f"content.webrtc_ip_handling_policy={val!r} may leak "
                "your real IP via WebRTC"
            ))


class CookieAcceptCheck(HealthCheck):

    @property
    def name(self) -> str:
        return "cookie_accept"

    def run(self, settings: ConfigDict, report: HealthReport) -> None:
        val = settings.get("content.cookies.accept", "")
        if val == "all":
            report.add(self._info(
                "content.cookies.accept='all' — "
                "tracking cookies are accepted on all sites"
            ))


class StartPageCheck(HealthCheck):

    @property
    def name(self) -> str:
        return "start_pages"

    def run(self, settings: ConfigDict, report: HealthReport) -> None:
        pages = settings.get("url.start_pages", [])
        if not pages:
            report.add(self._warning(
                "url.start_pages is empty — no start page configured"
            ))


class EditorCommandCheck(HealthCheck):

    @property
    def name(self) -> str:
        return "editor_command"

    def run(self, settings: ConfigDict, report: HealthReport) -> None:
        cmd = settings.get("editor.command")
        if cmd is None:
            return
        if not isinstance(cmd, list) or not cmd:
            report.add(self._error(
                f"editor.command must be a non-empty list, got: {cmd!r}"
            ))
            return
        if "{}" not in cmd:
            report.add(self._error(
                "editor.command must contain '{}' as the file placeholder"
            ))


class DownloadDirCheck(HealthCheck):

    @property
    def name(self) -> str:
        return "download_dir"

    def run(self, settings: ConfigDict, report: HealthReport) -> None:
        d = settings.get("downloads.location.directory", "")
        if isinstance(d, str) and (d == "/tmp" or d.startswith("/tmp/")):
            report.add(self._warning(
                f"downloads.location.directory={d!r} — "
                "downloads may be lost on reboot"
            ))


class TabTitleFormatCheck(HealthCheck):
    """
    Informational: tabs.title.format should include {current_title}.

    v9.1: severity is INFO (not WARNING) — the tab still works without it,
    but users typically want the page title shown.
    """

    @property
    def name(self) -> str:
        return "tab_title_format"

    def run(self, settings: ConfigDict, report: HealthReport) -> None:
        fmt = settings.get("tabs.title.format", "")
        if isinstance(fmt, str) and fmt and "{current_title}" not in fmt:
            report.add(self._info(
                f"tabs.title.format={fmt!r} does not include {{current_title}}"
                " — tabs may show only the URL or index"
            ))


class ProxySchemeCheck(HealthCheck):

    @property
    def name(self) -> str:
        return "proxy_scheme"

    _VALID_SCHEMES = {"socks5://", "socks://", "http://", "https://", "system", "none"}

    def run(self, settings: ConfigDict, report: HealthReport) -> None:
        proxy = settings.get("content.proxy", "system")
        if proxy is None:
            return
        if not isinstance(proxy, str):
            report.add(self._error(
                f"content.proxy must be a string, "
                f"got {type(proxy).__name__}: {proxy!r}"
            ))
            return
        if proxy in ("system", "none", ""):
            return
        if not any(proxy.startswith(s) for s in self._VALID_SCHEMES):
            report.add(self._error(
                f"content.proxy={proxy!r} does not start with a valid scheme "
                f"({', '.join(sorted(self._VALID_SCHEMES))})"
            ))


class ZoomDefaultCheck(HealthCheck):

    @property
    def name(self) -> str:
        return "zoom_default"

    def run(self, settings: ConfigDict, report: HealthReport) -> None:
        z = settings.get("zoom.default", "100%")
        if isinstance(z, str) and not z.endswith("%"):
            report.add(self._error(
                f"zoom.default={z!r} must end with '%', e.g. '100%' or '110%'"
            ))


class FontFamilyCheck(HealthCheck):
    """
    v9.1: also warns when fonts.default_family is not a string (was silently ignored).
    """

    @property
    def name(self) -> str:
        return "font_family"

    def run(self, settings: ConfigDict, report: HealthReport) -> None:
        fam = settings.get("fonts.default_family", None)
        if fam is None:
            return
        if not isinstance(fam, str):
            report.add(self._warning(
                f"fonts.default_family must be a string, "
                f"got {type(fam).__name__}"
            ))
            return
        if fam.strip() == "":
            report.add(self._warning(
                "fonts.default_family is empty string — "
                "qutebrowser will use a system fallback"
            ))


class SpellcheckLangCheck(HealthCheck):
    """
    v9.1: emits one HealthIssue per invalid BCP-47 tag (was a single combined warning).
    This makes it easier to identify exactly which entry is wrong when multiple
    invalid values are present.
    """

    @property
    def name(self) -> str:
        return "spellcheck_langs"

    # BCP-47 tag: en-US, zh-CN, de, fr, pt-BR, etc.
    _BCP47 = re.compile(r"^[a-z]{2,3}(-[A-Z]{2,3})?$")

    def run(self, settings: ConfigDict, report: HealthReport) -> None:
        langs = settings.get("spellcheck.languages", [])
        if not isinstance(langs, list):
            report.add(self._error(
                f"spellcheck.languages must be a list, "
                f"got {type(langs).__name__}"
            ))
            return
        langs = cast(list[Any], langs)
        for lang in langs:
            if not self._BCP47.match(str(lang)):
                report.add(self._warning(
                    f"spellcheck.languages: {lang!r} is not a valid BCP-47 tag"
                    " (expected e.g. 'en-US', 'zh-CN')"
                ))


class ContentHeaderCheck(HealthCheck):

    @property
    def name(self) -> str:
        return "content_user_agent"

    def run(self, settings: ConfigDict, report: HealthReport) -> None:
        ua = settings.get("content.headers.user_agent", None)
        if ua is not None and isinstance(ua, str) and ua.strip() == "":
            report.add(self._warning(
                "content.headers.user_agent is empty — "
                "some sites may reject requests"
            ))


class SearchEngineCountCheck(HealthCheck):
    """
    Warn if the search engine dict is suspiciously large (> MAX_ENGINES).

    More than 50 engines usually indicates a configuration error
    (e.g. engines dict merged multiple times, or a loop that adds duplicates).
    """
    MAX_ENGINES = 50

    @property
    def name(self) -> str:
        return "search_engine_count"

    def run(self, settings: ConfigDict, report: HealthReport) -> None:
        engines = settings.get("url.searchengines", {})
        if not isinstance(engines, dict):
            return
        engines = cast(dict[str, Any], engines)
        count = len(engines)
        if count > self.MAX_ENGINES:
            report.add(self._warning(
                f"url.searchengines has {count} entries (>{self.MAX_ENGINES}) — "
                "possible merge loop or misconfiguration"
            ))


class ProxySchemeDetailCheck(HealthCheck):
    """
    Validate that socks5:// and http:// proxy values have a host:port component.

    Catches common mistakes like ``socks5://`` (missing host) or
    ``socks5://127.0.0.1`` (missing port).
    """

    @property
    def name(self) -> str:
        return "proxy_scheme_detail"

    # host:port — host can be an IPv4, IPv6 bracket address, or hostname
    _HOST_PORT = re.compile(
        r"^(socks5?|https?)://"
        r"(\[.+\]|[^:/]+)"    # host: IPv6 bracket or plain
        r":(\d{1,5})"          # :port
        r"(/.*)?$"             # optional path
    )

    def run(self, settings: ConfigDict, report: HealthReport) -> None:
        proxy = settings.get("content.proxy", "system")
        if not isinstance(proxy, str):
            return
        if proxy in ("system", "none", ""):
            return
        if "://" not in proxy:
            return
        if not self._HOST_PORT.match(proxy):
            report.add(self._warning(
                f"content.proxy={proxy!r} does not match expected format "
                "'scheme://host:port' — connection may fail"
            ))


class DownloadPromptCheck(HealthCheck):
    """
    Informational: when prompt=False and directory is still ~/Downloads.

    Not an error — but a common oversight: users set prompt=False and
    forget to update the download directory to something more specific.
    """

    @property
    def name(self) -> str:
        return "download_prompt"

    _DEFAULT_DIRS = {"~/Downloads", "~/downloads"}

    def run(self, settings: ConfigDict, report: HealthReport) -> None:
        prompt = settings.get("downloads.location.prompt", True)
        if prompt:
            return
        d = settings.get("downloads.location.directory", "")
        if isinstance(d, str) and d in self._DEFAULT_DIRS:
            report.add(self._info(
                f"downloads.location.prompt=False and directory is still {d!r} — "
                "consider setting downloads.location.directory to a specific path"
            ))


# ─────────────────────────────────────────────
# Health Checker
# ─────────────────────────────────────────────

class HealthChecker:
    """
    Runs a set of HealthChecks against a resolved config dict.

    v9:   check() accepts optional extra_checks for composable injection.
          with_checks() factory builds a checker with an explicit check set.
    v9.1: calls hc.run() (push model); exceptions recorded as ERROR issues.
    """

    def __init__(self, checks: Optional[List[HealthCheck]] = None) -> None:
        self._checks: List[HealthCheck] = list(checks) if checks else []

    # ── Factories ─────────────────────────────────────────────────────

    @classmethod
    def default(cls) -> "HealthChecker":
        """Build the default checker with all 18 built-in checks (v9.1)."""
        return cls(checks=[
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
            SearchEngineCountCheck(),
            ProxySchemeDetailCheck(),
            DownloadPromptCheck(),
        ])

    @classmethod
    def with_checks(cls, *checks: HealthCheck) -> "HealthChecker":
        """
        Build a checker with an explicit check set (no defaults).

        Useful for testing specific checks in isolation::

            report = HealthChecker.with_checks(WebRTCPolicyCheck()).check(cfg)
        """
        return cls(checks=list(checks))

    # ── Mutation ──────────────────────────────────────────────────────

    def add(self, check: HealthCheck) -> "HealthChecker":
        """Append a check in-place; returns self for chaining."""
        self._checks.append(check)
        return self

    # ── Execution ─────────────────────────────────────────────────────

    def check(
        self,
        config:       ConfigDict,
        extra_checks: Optional[List[HealthCheck]] = None,
    ) -> HealthReport:
        """
        Run all checks against *config* and return a HealthReport.

        Args:
            config:       Resolved settings dict (flat key → value mapping).
            extra_checks: Additional checks to run for this invocation only
                          (not added to the checker permanently).

        Returns:
            HealthReport with all issues found.
        """
        report     = HealthReport()
        all_checks = list(self._checks)
        if extra_checks:
            all_checks.extend(extra_checks)

        for hc in all_checks:
            try:
                hc.run(config, report)
            except Exception as exc:
                logger.error("[HealthChecker] check %r raised: %s", hc.name, exc)
                report.add(HealthIssue(
                    check=hc.name,
                    severity=Severity.ERROR,
                    message=f"check raised unexpected exception: {exc}",
                ))

        logger.info(
            "[HealthChecker] %d checks run: %d error(s) %d warning(s) %d info(s)",
            len(all_checks),
            len(report.errors),
            len(report.warnings),
            len(report.infos),
        )
        return report

    def __len__(self) -> int:
        return len(self._checks)

    def __repr__(self) -> str:
        return f"HealthChecker(checks={len(self._checks)})"
