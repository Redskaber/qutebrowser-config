"""
layers/network.py
=================
Network Layer — Proxy, DNS, and Network-Level Configuration  (v15)

Priority: 27  (between privacy[20] and appearance[30])

Responsibilities:
  - Proxy configuration (system / none / socks5 / http / tor / offline)
  - DNS prefetch control
  - Referrer policy
  - TLS certificate error behaviour
  - Keybindings for runtime proxy cycling (,N prefix)
  - :net alias shows active mode description

Rationale for a dedicated layer:
  Prior to v14, network settings were scattered across:
    - BaseLayer          (dns_prefetch default)
    - PrivacyLayer       (referer, WebRTC — stays there — privacy-semantics)
    - UserLayer          (proxy override via proxy= param)
    - policies/network.py (policy-chain enforcement)

  NetworkLayer centralises *declarative* network settings: how the browser
  connects to the internet.  Separation of concerns:
    NetworkLayer     → what the network settings ARE (declarative, data-driven)
    policies/network.py → what the settings MUST NOT violate (enforcement)
    UserLayer(p=90)  → personal runtime override (proxy= param, still works)

Network Modes (data-driven via NetworkSpec):
  DIRECT  — no proxy; DNS prefetch on; normal referrer
  SYSTEM  — OS-level proxy; DNS prefetch on; normal referrer  ← default
  SOCKS5  — SOCKS5 proxy (127.0.0.1:7897); DNS off; same-origin referrer
  HTTP    — HTTP proxy  (127.0.0.1:7890); DNS off; same-origin referrer
  TOR     — Tor SOCKS5 (127.0.0.1:9050); DNS off; never referrer; block TLS errors
  OFFLINE — no proxy; DNS off; never referrer; local-only hint

Mode Resolution (highest priority wins):
  1. mode= constructor parameter (NETWORK_MODE in config.py)
  2. QUTE_NETWORK environment variable
  3. ~/.config/qutebrowser/.network file (written by ,N* keybindings)
  4. SYSTEM fallback

Priority ordering for network-relevant keys:
  BaseLayer[10]    → dns_prefetch=True (structural default)
  PrivacyLayer[20] → dns_prefetch, referer (hardening for HARDENED/PARANOID)
  NetworkLayer[27] → proxy, dns_prefetch, referer, tls_errors (declarative mode)
  UserLayer[90]    → proxy= param (final personal override)

Note: NetworkLayer[27] > PrivacyLayer[20] for network routing settings.
This is intentional — mode choice is more authoritative than profile hardening
for *how you connect*.  Use PARANOID + TOR mode together for maximum privacy.

Keybindings (,N prefix):
  ,Nn  → network mode: none/direct
  ,Ns  → network mode: system (default)
  ,N5  → network mode: socks5://127.0.0.1:7897 (common Clash/V2ray port)
  ,Nh  → network mode: http://127.0.0.1:7890
  ,Nt  → network mode: Tor (socks5://127.0.0.1:9050)
  ,Ni  → show current proxy setting

Aliases:
  :net → message showing active mode and description

Design patterns:
  - Data-Driven: NetworkSpec table, no if/else chains in _settings
  - Strategy: NetworkMode selects the spec
  - Separation of Concerns: declarative layer vs policy enforcement
  - Immutability: _NETWORK_TABLE is never mutated; URL overrides build a
    fresh per-instance spec dict

Strict-mode: all attrs typed; NetworkSpec is frozen dataclass.

v15 changes:
  - Bug fix: URL overrides (socks5_url, http_url) no longer mutate the
    module-level _NETWORK_TABLE.  Each instance builds its own _spec_table
    copy only when overrides are provided.
  - NetworkLayer._spec_table property: instance-local table (= _NETWORK_TABLE
    unless overrides are present).
  - describe() output improved: includes mode value and proxy string.
  - available_modes() classmethod added (mirrors SessionLayer.available_sessions).
  - __repr__ includes active mode.

v14 (original design, retained):
  - NetworkMode enum: DIRECT / SYSTEM / SOCKS5 / HTTP / TOR / OFFLINE
  - NetworkSpec frozen dataclass: proxy, dns_prefetch, referer, tls_errors, description
  - _NETWORK_TABLE data-driven spec map
  - _resolve_active_mode(): param → env → file → SYSTEM fallback
  - NetworkLayer: _settings(), _keybindings(), _aliases(), active_mode, describe()
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from enum import StrEnum
from typing import ClassVar, Dict, List, Optional

from core.types import ConfigDict, Keybind
from core.layer import BaseConfigLayer

logger = logging.getLogger("qute.layers.network")

_NETWORK_ENV   = "QUTE_NETWORK"
_NETWORK_FILE  = os.path.expanduser("~/.config/qutebrowser/.network")


# ─────────────────────────────────────────────
# Network Modes
# ─────────────────────────────────────────────

class NetworkMode(StrEnum):
    """Named network/proxy configuration slots."""
    DIRECT  = "direct"   # no proxy; direct connection
    SYSTEM  = "system"   # OS-level proxy / no proxy (qutebrowser default)
    SOCKS5  = "socks5"   # SOCKS5 via 127.0.0.1:7897 (Clash/Verge default)
    HTTP    = "http"     # HTTP proxy via 127.0.0.1:7890
    TOR     = "tor"      # Tor SOCKS5 via 127.0.0.1:9050
    OFFLINE = "offline"  # block-external hint; local-only mode


# ─────────────────────────────────────────────
# NetworkSpec — data-driven configuration
# ─────────────────────────────────────────────

@dataclass(frozen=True)
class NetworkSpec:
    """
    Immutable specification for one network mode.

    Fields
    ------
    proxy       : value for content.proxy ("system", "none", socks5://…, …)
    dns_prefetch: whether to enable content.dns_prefetch
    referer     : value for content.headers.referer
                  "always" | "never" | "same-origin" | "no-referrer-when-downgrade"
    description : human-readable summary shown by :net alias
    tls_errors  : value for content.tls.certificate_errors
                  "ask" | "block" | "ignore" | "load-insecure"
    """
    proxy:        str
    dns_prefetch: bool
    referer:      str
    description:  str
    tls_errors:   str = "ask"


# ─────────────────────────────────────────────
# Default proxy URLs (used by keybindings too)
# ─────────────────────────────────────────────

_DEFAULT_SOCKS5_URL = "socks5://127.0.0.1:7897"
_DEFAULT_HTTP_URL   = "http://127.0.0.1:7890"
_DEFAULT_TOR_URL    = "socks5://127.0.0.1:9050"


# ─────────────────────────────────────────────
# Spec Table (Single Source of Truth)
# ─────────────────────────────────────────────

def _build_spec_table(
    socks5_url: str = _DEFAULT_SOCKS5_URL,
    http_url:   str = _DEFAULT_HTTP_URL,
    tor_url:    str = _DEFAULT_TOR_URL,
) -> Dict[NetworkMode, NetworkSpec]:
    """
    Build a NetworkMode → NetworkSpec mapping.

    Parameters allow per-instance URL overrides without mutating the
    module-level default table.  Called once at module load (defaults)
    and once per NetworkLayer instance only when overrides are provided.
    """
    return {
        NetworkMode.DIRECT: NetworkSpec(
            proxy        = "none",
            dns_prefetch = True,
            referer      = "always",
            description  = "Direct connection — no proxy, DNS prefetch on",
            tls_errors   = "ask",
        ),
        NetworkMode.SYSTEM: NetworkSpec(
            proxy        = "system",
            dns_prefetch = True,
            referer      = "always",
            description  = "System proxy (OS-level) — qutebrowser default",
            tls_errors   = "ask",
        ),
        NetworkMode.SOCKS5: NetworkSpec(
            proxy        = socks5_url,
            dns_prefetch = False,
            referer      = "same-origin",
            description  = f"SOCKS5 proxy ({socks5_url}) — Clash/Verge default port",
            tls_errors   = "ask",
        ),
        NetworkMode.HTTP: NetworkSpec(
            proxy        = http_url,
            dns_prefetch = False,
            referer      = "same-origin",
            description  = f"HTTP proxy ({http_url})",
            tls_errors   = "ask",
        ),
        NetworkMode.TOR: NetworkSpec(
            proxy        = tor_url,
            dns_prefetch = False,
            referer      = "never",
            description  = f"Tor SOCKS5 ({tor_url}) — maximum anonymity",
            tls_errors   = "block",
        ),
        NetworkMode.OFFLINE: NetworkSpec(
            proxy        = "none",
            dns_prefetch = False,
            referer      = "never",
            description  = "Offline / local-only (no external requests recommended)",
            tls_errors   = "ask",
        ),
    }


# Module-level default table (never mutated)
_NETWORK_TABLE: Dict[NetworkMode, NetworkSpec] = _build_spec_table()


# ─────────────────────────────────────────────
# Mode Resolution
# ─────────────────────────────────────────────

def _resolve_active_mode(param: Optional[str]) -> NetworkMode:
    """
    Resolve active NetworkMode from multiple sources (highest priority first):

    1. ``mode`` constructor parameter (from config.py NETWORK_MODE)
    2. QUTE_NETWORK environment variable
    3. ~/.config/qutebrowser/.network file (written by ,N* keybindings)
    4. NetworkMode.SYSTEM fallback

    All lookups are case-insensitive.  Unknown values log a warning and
    fall through to the next source rather than raising.
    """
    # 1. Constructor param
    if param is not None:
        try:
            return NetworkMode(param.lower().strip())
        except ValueError:
            logger.warning(
                "[NetworkLayer] unknown network mode %r; falling back to env/file/SYSTEM",
                param,
            )

    # 2. Environment variable
    env_val = os.environ.get(_NETWORK_ENV, "").strip().lower()
    if env_val:
        try:
            return NetworkMode(env_val)
        except ValueError:
            logger.warning(
                "[NetworkLayer] QUTE_NETWORK=%r is not a valid mode; ignoring", env_val
            )

    # 3. Persistent file
    try:
        if os.path.isfile(_NETWORK_FILE):
            with open(_NETWORK_FILE) as fh:
                file_val = fh.read().strip().lower()
            if file_val:
                try:
                    return NetworkMode(file_val)
                except ValueError:
                    logger.debug(
                        "[NetworkLayer] .network file contains %r — not a valid mode; ignoring",
                        file_val,
                    )
    except OSError:
        pass

    # 4. Default
    return NetworkMode.SYSTEM


# ─────────────────────────────────────────────
# NetworkLayer
# ─────────────────────────────────────────────

class NetworkLayer(BaseConfigLayer):
    """
    Network and proxy configuration layer.

    Declares how qutebrowser connects to the internet.  Sits between
    PrivacyLayer (p=20) and AppearanceLayer (p=30) at priority 27.

    Args:
        mode      : NetworkMode name string or None (auto-resolve).
                    Valid: "direct" | "system" | "socks5" | "http" | "tor" | "offline"
        leader    : Leader key prefix for keybindings (default ",").
        socks5_url: Override SOCKS5 proxy URL.
                    Default: socks5://127.0.0.1:7897 (Clash/Verge mixed port).
        http_url  : Override HTTP proxy URL.
                    Default: http://127.0.0.1:7890.
        tor_url   : Override Tor proxy URL.
                    Default: socks5://127.0.0.1:9050.
    """

    name        = "network"
    priority    = 27
    description = "Network/proxy/DNS/TLS configuration"

    #: Names of all valid network modes — for diagnostics / completion.
    MODE_NAMES: ClassVar[List[str]] = [m.value for m in NetworkMode]

    def __init__(
        self,
        mode:       Optional[str] = None,
        leader:     str           = ",",
        socks5_url: Optional[str] = None,
        http_url:   Optional[str] = None,
        tor_url:    Optional[str] = None,
    ) -> None:
        self._mode   = _resolve_active_mode(mode)
        self._leader = leader

        # Build per-instance spec table only when URL overrides are provided.
        # No mutation of module-level _NETWORK_TABLE.
        if socks5_url is not None or http_url is not None or tor_url is not None:
            self._spec_table: Dict[NetworkMode, NetworkSpec] = _build_spec_table(
                socks5_url = socks5_url or _DEFAULT_SOCKS5_URL,
                http_url   = http_url   or _DEFAULT_HTTP_URL,
                tor_url    = tor_url    or _DEFAULT_TOR_URL,
            )
        else:
            self._spec_table = _NETWORK_TABLE

        self._spec  = self._spec_table[self._mode]
        self._socks5_url = socks5_url or _DEFAULT_SOCKS5_URL
        self._http_url   = http_url   or _DEFAULT_HTTP_URL
        self._tor_url    = tor_url    or _DEFAULT_TOR_URL

        logger.debug(
            "[NetworkLayer] active mode: %s — %s",
            self._mode.value, self._spec.description,
        )

    # ── Properties ────────────────────────────────────────────────────

    @property
    def active_mode(self) -> NetworkMode:
        """Return the resolved active NetworkMode."""
        return self._mode

    @property
    def active_spec(self) -> NetworkSpec:
        """Return the NetworkSpec for the active mode."""
        return self._spec

    @classmethod
    def available_modes(cls) -> List[str]:
        """Return sorted list of all valid mode name strings."""
        return sorted(m.value for m in NetworkMode)

    def describe(self) -> str:
        """Human-readable description of active network configuration."""
        return (
            f"[NetworkLayer] mode={self._mode.value}  "
            f"proxy={self._spec.proxy}  "
            f"{self._spec.description}"
        )

    def __repr__(self) -> str:
        return f"NetworkLayer(mode={self._mode.value!r}, priority={self.priority})"

    # ── Settings ──────────────────────────────────────────────────────

    def _settings(self) -> ConfigDict:
        s = self._spec
        return {
            "content.proxy":                  s.proxy,
            "content.dns_prefetch":           s.dns_prefetch,
            "content.headers.referer":        s.referer,
            "content.tls.certificate_errors": s.tls_errors,
        }

    # ── Keybindings (,N prefix) ────────────────────────────────────────

    def _keybindings(self) -> List[Keybind]:
        L = self._leader
        return [
            # ── Proxy mode selection ───────────────────────────────────
            (f"{L}Nn",  "set content.proxy none",                           "normal"),
            (f"{L}Ns",  "set content.proxy system",                         "normal"),
            (f"{L}N5",  f"set content.proxy {self._socks5_url}",            "normal"),
            (f"{L}Nh",  f"set content.proxy {self._http_url}",              "normal"),
            (f"{L}Nt",  f"set content.proxy {self._tor_url}",               "normal"),

            # ── Status ─────────────────────────────────────────────────
            (f"{L}Ni",  "config-info content.proxy",                        "normal"),
        ]

    # ── Aliases ───────────────────────────────────────────────────────

    def _aliases(self) -> ConfigDict:
        return {
            "net": (
                f"message-info 'Network: {self._mode.value} — "
                f"proxy={self._spec.proxy} — "
                f"{self._spec.description}'"
            ),
        }


# ─────────────────────────────────────────────
# Public exports
# ─────────────────────────────────────────────

__all__ = [
    "NetworkLayer",
    "NetworkMode",
    "NetworkSpec",
    "_NETWORK_TABLE",
    "_build_spec_table",
    "_resolve_active_mode",
]
