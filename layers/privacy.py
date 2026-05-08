"""
layers/privacy.py
=================
Privacy & Security Layer  (v18)

Priority: 20

Responsibilities:
  - WebRTC / fingerprinting resistance
  - Cookie and storage policies
  - HTTPS enforcement
  - Content blocking (adblock + hosts)
  - DNS / network leak prevention

This layer is intentionally opinionated: secure > convenient.
Per-host exceptions belong in BehaviorLayer.host_policies().

Profiles (Strategy pattern):
  STANDARD  — sane defaults, minimal site breakage
  HARDENED  — stronger protection; some authenticated sites may break
  PARANOID  — maximum protection; JS and images disabled; Tor proxy

Keybinding namespace (EXCLUSIVE to this layer):
  ,j  = toggle JavaScript     ,i  = toggle images
  ,c  = cycle cookie policy   ,s  = force HTTPS reload

  These FOUR keys are the privacy layer's hard ownership.
  BehaviorLayer (priority=40) does NOT define ,j / ,i / ,c / ,s.

  Cross-layer prefix rule: ,s is a TERMINAL — BehaviorLayer must NOT
  register any ,s* sub-sequences (would block this terminal from firing).
  This rule was violated in v17 (,sn/,sl) and fixed in v18 (removed).

v18 changes:
  [ADD] message-info feedback on ,j / ,i / ,c so status bar confirms
        what was toggled (useful with DEBUG_BINDINGS or just as UX).
  [FIX] Docstring updated to reflect v18 cross-layer prefix rule.

v13 changes (retained):
  ,p removed from this layer (was OTP userscript — moved to BehaviorLayer).

v12 fixes (retained):
  leader= constructor param; ValidateStage inspects data["settings"];
  removed downloads.open_dispatcher: None (not a valid config value).
"""

from __future__ import annotations

from enum import Enum, auto
from typing import List

from core.types import ConfigDict, Keybind
from core.layer import BaseConfigLayer
from core.pipeline import LogStage, Pipeline, ValidateStage


class PrivacyProfile(Enum):
    """Selectable privacy hardening levels."""
    STANDARD = auto()   # sane defaults, minimal breakage
    HARDENED = auto()   # stronger protection; some sites may break
    PARANOID = auto()   # maximum protection; expect significant breakage


class PrivacyLayer(BaseConfigLayer):
    """
    Privacy and security configuration layer (priority=20).

    Args:
        profile: One of PrivacyProfile.{STANDARD,HARDENED,PARANOID}.
        leader:  Leader key prefix (default ",").
    """

    name        = "privacy"
    priority    = 20
    description = "Privacy & security hardening"

    def __init__(
        self,
        profile: PrivacyProfile = PrivacyProfile.STANDARD,
        leader:  str            = ",",
    ) -> None:
        self._profile = profile
        self._leader  = leader

    # ── Settings ─────────────────────────────────────────────────────────────

    def _settings(self) -> ConfigDict:
        base = self._standard_settings()
        if self._profile == PrivacyProfile.HARDENED:
            base.update(self._hardened_overlay())
        elif self._profile == PrivacyProfile.PARANOID:
            base.update(self._hardened_overlay())
            base.update(self._paranoid_overlay())
        return base

    def _standard_settings(self) -> ConfigDict:
        return {
            # ── WebRTC ────────────────────────────────────────────────────────
            "content.webrtc_ip_handling_policy": "default-public-interface-only",

            # ── TLS / HTTPS ───────────────────────────────────────────────────
            "content.tls.certificate_errors": "ask",

            # ── Referer ───────────────────────────────────────────────────────
            "content.headers.referer": "same-domain",

            # ── Do-Not-Track ──────────────────────────────────────────────────
            "content.headers.do_not_track": True,

            # ── Third-party cookies ───────────────────────────────────────────
            "content.cookies.accept": "no-3rdparty",
            "content.cookies.store":  True,

            # ── Content blocking (adblock + host-level) ───────────────────────
            "content.blocking.enabled": True,
            "content.blocking.method":  "both",
            "content.blocking.adblock.lists": [
                "https://easylist.to/easylist/easylist.txt",
                "https://easylist.to/easylist/easyprivacy.txt",
                "https://raw.githubusercontent.com/uBlockOrigin/uAssets/master/filters/filters.txt",
                "https://raw.githubusercontent.com/uBlockOrigin/uAssets/master/filters/privacy.txt",
                "https://raw.githubusercontent.com/uBlockOrigin/uAssets/master/filters/annoyances.txt",
                "https://secure.fanboy.co.nz/fanboy-cookiemonster.txt",
            ],
            "content.blocking.hosts.lists": [
                "https://raw.githubusercontent.com/StevenBlack/hosts/master/hosts",
            ],

            # ── Cache ─────────────────────────────────────────────────────────
            "content.cache.size": 0,   # let Chromium manage (~80 MB default)
        }

    def _hardened_overlay(self) -> ConfigDict:
        return {
            "content.cookies.accept":            "never",
            "content.local_storage":             False,
            "content.persistent_storage":        False,
            "content.headers.referer":           "never",
            "content.webrtc_ip_handling_policy": "disable-non-proxied-udp",
            "content.tls.certificate_errors":    "block",
        }

    def _paranoid_overlay(self) -> ConfigDict:
        return {
            "content.javascript.enabled":      False,
            "content.images":                  False,
            "content.media.audio_capture":     False,
            "content.media.video_capture":     False,
            "content.media.screen_capture":    False,
            "content.cookies.accept":          "never",
            "content.headers.accept_language": "",
            "content.proxy":                   "socks://localhost:9050",
        }

    # ── Keybindings ──────────────────────────────────────────────────────────

    def _keybindings(self) -> List[Keybind]:
        """
        Privacy-specific toggle bindings.

        Exclusive namespace: ,j / ,i / ,c / ,s
        BehaviorLayer[40] must not touch these keys (cross-layer prefix rule).

        message-info appended to ,j/,i/,c so the status bar confirms
        what changed (useful during testing / DEBUG_BINDINGS=True sessions).
        ,s navigates to the HTTPS version — the URL bar change is itself
        sufficient feedback; no message-info needed.
        """
        L = self._leader
        return [
            (f"{L}j",
             "config-cycle content.javascript.enabled true false"
             " ;; message-info 'JS toggled'",
             "normal"),

            (f"{L}i",
             "config-cycle content.images true false"
             " ;; message-info 'Images toggled'",
             "normal"),

            (f"{L}c",
             "config-cycle content.cookies.accept all no-3rdparty never"
             " ;; message-info 'Cookies cycled'",
             "normal"),

            (f"{L}s",
             "open https://{url:host}",
             "normal"),
        ]

    # ── Layer-level validation pipeline ──────────────────────────────────────

    def pipeline(self) -> Pipeline:
        return (
            Pipeline("privacy")
            .pipe(LogStage("privacy-pre"))
            .pipe(ValidateStage({
                "content.blocking.enabled": lambda v: isinstance(v, bool),
                "content.cookies.accept": lambda v: v in (
                    "all", "no-3rdparty", "no-unknown-3rdparty", "never"
                ),
            }))
            .pipe(LogStage("privacy-post"))
        )

    def validate(self, data: ConfigDict) -> List[str]:
        errors: List[str] = []
        settings = data.get("settings", data)
        if (settings.get("content.javascript.enabled")
                and self._profile == PrivacyProfile.PARANOID):
            errors.append("PARANOID profile should not enable JavaScript")
        return errors
