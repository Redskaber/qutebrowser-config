"""
layers/privacy.py
=================
Privacy & Security Layer

Priority: 20

Responsibilities:
  - WebRTC / fingerprinting resistance
  - Cookie and storage policies
  - HTTPS enforcement
  - Content blocking (adblock + hosts)
  - DNS / network leak prevention

This layer is intentionally opinionated: secure > convenient.
Per-host exceptions belong in BehaviorLayer.host_policies().

Profiles (Strategy axis):
  STANDARD  — sane defaults, minimal site breakage
  HARDENED  — stronger protection; some authenticated sites may break
  PARANOID  — maximum protection; JavaScript and images disabled; Tor proxy

Fixes applied vs original:
  • Added ``leader`` constructor param so keybindings respect the configured
    leader key instead of hard-coding ``","``
  • ValidateStage now inspects ``data["settings"]`` (the nested structure that
    BaseConfigLayer.build() produces) rather than the flat top-level dict
  • Removed ``downloads.open_dispatcher: None`` (duplicate from base; None is
    not a valid qutebrowser config value)
"""

from __future__ import annotations

from enum import Enum, auto
from typing import List

from core.types import ConfigDict
from core.layer import BaseConfigLayer
from core.pipeline import LogStage, Pipeline, ValidateStage
from keybindings.catalog import Keybind  # ConfigPacket


class PrivacyProfile(Enum):
    """Selectable privacy levels."""
    STANDARD = auto()   # sane defaults, minimal breakage
    HARDENED = auto()   # stronger protection, some sites may break
    PARANOID = auto()   # maximum protection, expect breakage


class PrivacyLayer(BaseConfigLayer):
    """
    Privacy and security configuration.

    Args:
        profile: One of ``PrivacyProfile.{STANDARD,HARDENED,PARANOID}``.
        leader:  Leader key prefix used in keybindings (default ``","``).
    """

    name        = "privacy"
    priority    = 20
    description = "Privacy & security hardening"

    def __init__(
        self,
        profile: PrivacyProfile = PrivacyProfile.STANDARD,
        leader: str = ",",
    ) -> None:
        self._profile = profile
        self._leader  = leader

    # ── Settings ──────────────────────────────────────────────────────
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
            # ── WebEngine / Chromium ───────────────────────────
            "content.webrtc_ip_handling_policy": "default-public-interface-only",
            "content.geolocation":                False,
            "content.notifications.enabled":      False,
            "content.desktop_capture":            False,
            "content.autoplay":                   False,
            "content.register_protocol_handler":  False,

            # ── Cookies ───────────────────────────────────────
            "content.cookies.accept": "no-3rdparty",
            "content.cookies.store":  True,

            # ── JavaScript ────────────────────────────────────
            "content.javascript.clipboard":                  "none",
            "content.javascript.can_open_tabs_automatically": False,
            "content.javascript.alert":                      True,

            # ── Storage ───────────────────────────────────────
            "content.local_storage":      True,
            "content.persistent_storage": True,

            # ── Plugins / PDF ─────────────────────────────────
            "content.plugins":    False,
            "content.pdfjs":      True,

            # ── HTTPS ─────────────────────────────────────────
            "content.tls.certificate_errors": "ask-block-thirdparty",

            # ── Headers / Fingerprinting ──────────────────────
            "content.headers.accept_language": "",
            "content.headers.custom": {
                "accept-language": "en-US,en;q=0.9",
            },
            "content.headers.referer": "same-domain",
            "content.headers.user_agent": (
                "Mozilla/5.0 ({os_info}) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/134.0 Safari/537.36"
            ),

            # ── Network ───────────────────────────────────────
            "content.proxy": "system",

            # ── Content blocking (requires adblock package) ───
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

            # ── Cache ─────────────────────────────────────────
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
            "content.javascript.enabled":        False,
            "content.images":                    False,
            "content.media.audio_capture":       False,
            "content.media.video_capture":       False,
            "content.media.screen_capture":      False,
            "content.cookies.accept":            "never",
            "content.headers.accept_language":   "",
            "content.proxy":                     "socks://localhost:9050",  # Tor
        }

    # ── Keybindings ───────────────────────────────────────────────────
    def _keybindings(self) -> List[Keybind]:
        L = self._leader
        return [
            # Toggle JavaScript
            (f"{L}j", "config-cycle content.javascript.enabled true false",         "normal"),
            # Toggle images
            (f"{L}i", "config-cycle content.images true false",                     "normal"),
            # Cycle cookie policy
            (f"{L}c", "config-cycle content.cookies.accept all no-3rdparty never",  "normal"),
            # Force HTTPS reload
            (f"{L}s", "open https://{host}",                                        "normal"),
        ]

    # ── Pipeline (layer-level validation) ─────────────────────────────
    def pipeline(self) -> Pipeline:
        """
        Run a lightweight validation pass on the layer's output packet.

        The packet produced by BaseConfigLayer.build() has structure::

            {"settings": {"content.blocking.enabled": True, …}, …}

        ValidateStage (fixed) inspects both ``packet.data`` and
        ``packet.data["settings"]`` so the rules below work correctly.
        """
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
        settings = data.get("settings", data)  # tolerate flat or nested
        if settings.get("content.javascript.enabled") and self._profile == PrivacyProfile.PARANOID:
            errors.append("PARANOID profile should not enable JavaScript")
        return errors


