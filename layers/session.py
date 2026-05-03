"""
layers/session.py
=================
Session Layer — Time-Aware and System-Aware Configuration  (v11)

Priority: 55  (between performance[50] and user[90])

A "session" is a named time/situation slot that adjusts configuration
based on the current environment:

  SessionMode.AUTO       — auto-detect from local time + environment
  SessionMode.DAY        — daylight working hours (08:00–18:00)
  SessionMode.EVENING    — wind-down hours (18:00–22:00)
  SessionMode.NIGHT      — late night / low-light (22:00–06:00)
  SessionMode.FOCUS      — deep-work: minimal UI, distraction-free
  SessionMode.COMMUTE    — mobile / bandwidth-constrained
  SessionMode.PRESENT    — screen-share / presentation mode

Design:
  SessionSpec (data) → SessionLayer (renderer) → qutebrowser settings delta

Architecture integration:
  - SessionLayer resolves active session from (in priority order):
      1. ``session`` constructor parameter  (from config.py SESSION_MODE)
      2. QUTE_SESSION environment variable
      3. ~/.config/qutebrowser/.session persistent file
      4. SessionMode.AUTO → derived from local time

  - The layer emits *only* the delta (keys that differ from defaults).
    It does NOT override colors; those belong to AppearanceLayer (p=30).
    Session affects: zoom, font size, animation, scroll, tab visibility,
    notification policy, image loading.

  - Compatible with ContextLayer: context controls *what* you browse;
    session controls *how* the browser behaves right now.

Patterns:
  - Strategy (session as spec)
  - Data-Driven (spec table, no if/else chains in _settings)
  - State (active session resolved once at init)

Strict-mode:
  All attrs typed; SessionSpec is frozen dataclass; no bare dict usage.

v11 (new module):
  - SessionMode enum: AUTO / DAY / EVENING / NIGHT / FOCUS / COMMUTE / PRESENT
  - SessionSpec frozen dataclass: settings_delta, description, zoom_hint
  - _SESSION_TABLE data-driven spec map
  - _resolve_active_session(): env var → file → auto-detect
  - SessionLayer: _settings(), _keybindings(), active_session, describe()
  - Keybindings: ,S prefix (,Sd = day, ,Se = evening, ,Sn = night,
                             ,Sf = focus, ,Sc = commute, ,Sp = present,
                             ,S0 = auto, ,Si = show current)
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional

from core.types import ConfigDict, Keybind
from core.layer import BaseConfigLayer

logger = logging.getLogger("qute.layers.session")

_SESSION_FILE_ENV = "QUTE_SESSION_FILE"


# ─────────────────────────────────────────────
# Session Modes
# ─────────────────────────────────────────────

class SessionMode(str, Enum):
    """Named time/situation slots."""
    AUTO    = "auto"      # derived from local time
    DAY     = "day"       # 08:00–18:00 standard working
    EVENING = "evening"   # 18:00–22:00 wind-down
    NIGHT   = "night"     # 22:00–06:00 low-light
    FOCUS   = "focus"     # deep work, no distractions
    COMMUTE = "commute"   # bandwidth-constrained mobile
    PRESENT = "present"   # screen-sharing / demo mode


# ─────────────────────────────────────────────
# Session Specification (immutable data)
# ─────────────────────────────────────────────

@dataclass(frozen=True)
class SessionSpec:
    """
    Immutable spec for one session mode.

    Attributes:
        mode:           The SessionMode this spec describes.
        description:    Human-readable label.
        settings_delta: qutebrowser keys to *override* in this session.
                        Only keys that differ from base defaults are emitted.
        zoom_hint:      Informational: default zoom level for this session.
    """
    mode:           SessionMode
    description:    str        = ""
    settings_delta: ConfigDict = field(default_factory=dict[str, Any])
    zoom_hint:      str        = "100%"


# ─────────────────────────────────────────────
# Session Table (data-driven)
# ─────────────────────────────────────────────

_SESSION_TABLE: Dict[SessionMode, SessionSpec] = {

    # AUTO is a sentinel — resolved to one of the time-based modes at init.
    # If auto-detection fails, AUTO falls back to DAY.
    SessionMode.AUTO: SessionSpec(
        mode        = SessionMode.AUTO,
        description = "Auto (resolved from local time)",
        settings_delta = {},
        zoom_hint   = "100%",
    ),

    SessionMode.DAY: SessionSpec(
        mode        = SessionMode.DAY,
        description = "Day — standard working hours, full performance",
        settings_delta = {
            # Defaults: minimal delta, just be explicit about the important ones.
            "content.autoplay":              False,
            "content.notifications.enabled": False,
            "statusbar.show":                "always",
            "tabs.show":                     "always",
            "zoom.default":                  "100%",
        },
        zoom_hint = "100%",
    ),

    SessionMode.EVENING: SessionSpec(
        mode        = SessionMode.EVENING,
        description = "Evening — reduced brightness, slightly larger text",
        settings_delta = {
            "content.autoplay":              False,
            "content.notifications.enabled": False,
            "statusbar.show":                "always",
            "tabs.show":                     "always",
            # Slightly larger default web font for evening readability
            "fonts.web.size.default":        18,
            "zoom.default":                  "105%",
        },
        zoom_hint = "105%",
    ),

    SessionMode.NIGHT: SessionSpec(
        mode        = SessionMode.NIGHT,
        description = "Night — larger text, no autoplay, minimal UI chrome",
        settings_delta = {
            "content.autoplay":              False,
            "content.notifications.enabled": False,
            "statusbar.show":                "in-mode",
            "tabs.show":                     "multiple",
            # Larger font for low-light reading
            "fonts.web.size.default":        20,
            "zoom.default":                  "110%",
            # Reduce motion for late-night comfort
            "content.prefers_reduced_motion": True,
        },
        zoom_hint = "110%",
    ),

    SessionMode.FOCUS: SessionSpec(
        mode        = SessionMode.FOCUS,
        description = "Focus — deep work: minimal UI, no distractions",
        settings_delta = {
            "content.autoplay":              False,
            "content.notifications.enabled": False,
            # Hide chrome to maximise reading area
            "statusbar.show":                "in-mode",
            "tabs.show":                     "multiple",
            # Disable tab title in bar to reduce visual noise
            "tabs.title.format":             "{current_title}",
            # Larger, more readable web font
            "fonts.web.size.default":        18,
            "zoom.default":                  "100%",
            # Reduce motion
            "content.prefers_reduced_motion": True,
        },
        zoom_hint = "100%",
    ),

    SessionMode.COMMUTE: SessionSpec(
        mode        = SessionMode.COMMUTE,
        description = "Commute — bandwidth-constrained: no images, no autoplay",
        settings_delta = {
            "content.autoplay":              False,
            "content.notifications.enabled": False,
            # Conserve bandwidth
            "content.images":                False,
            # Fewer tabs visible to reduce distraction on small screen
            "tabs.show":                     "multiple",
            "statusbar.show":                "in-mode",
            "fonts.web.size.default":        18,
            "zoom.default":                  "110%",
        },
        zoom_hint = "110%",
    ),

    SessionMode.PRESENT: SessionSpec(
        mode        = SessionMode.PRESENT,
        description = "Present — screen-share / demo: large text, full UI",
        settings_delta = {
            "content.autoplay":              False,
            "content.notifications.enabled": False,
            # Full visibility for the audience
            "statusbar.show":                "always",
            "tabs.show":                     "always",
            # Large text for screen-share legibility
            "fonts.web.size.default":        22,
            "zoom.default":                  "125%",
        },
        zoom_hint = "125%",
    ),
}


# ─────────────────────────────────────────────
# Session File / Auto-Detect
# ─────────────────────────────────────────────

def _default_session_file() -> str:
    if override := os.environ.get(_SESSION_FILE_ENV):
        return override
    config_dir = os.environ.get(
        "QUTE_CONFIG_DIR",
        os.path.expanduser("~/.config/qutebrowser"),
    )
    return os.path.join(config_dir, ".session")


def _read_session_file(path: str) -> Optional[str]:
    try:
        raw = open(path).read().strip()
        return raw if raw else None
    except OSError:
        return None


def _auto_detect_session() -> SessionMode:
    """
    Derive a SessionMode from the current local time.

      06:00–08:00 → NIGHT  (early morning — treat as night for now)
      08:00–18:00 → DAY
      18:00–22:00 → EVENING
      22:00–06:00 → NIGHT
    """
    hour = datetime.now().hour
    if 8 <= hour < 18:
        return SessionMode.DAY
    elif 18 <= hour < 22:
        return SessionMode.EVENING
    else:
        return SessionMode.NIGHT


def _resolve_active_session(override: Optional[str]) -> SessionMode:
    """
    Resolve the active SessionMode.

    Priority order:
      1. ``override`` parameter (from config.py SESSION_MODE)     ← highest
      2. QUTE_SESSION environment variable
      3. ~/.config/qutebrowser/.session file
      4. auto-detect from local time                              ← lowest
    """
    raw: Optional[str] = (
        override
        or os.environ.get("QUTE_SESSION")
        or _read_session_file(_default_session_file())
    )

    if raw is not None:
        raw_l = raw.lower().strip()
        if raw_l != "auto":
            try:
                mode = SessionMode(raw_l)
                logger.info("[SessionLayer] active session: %s (from explicit source)", mode.value)
                return mode
            except ValueError:
                logger.warning(
                    "[SessionLayer] unknown session %r; valid: %s — auto-detecting",
                    raw,
                    [m.value for m in SessionMode],
                )

    # Auto-detect from time
    detected = _auto_detect_session()
    logger.info("[SessionLayer] active session: %s (auto-detected from time)", detected.value)
    return detected


# ─────────────────────────────────────────────
# Session Layer
# ─────────────────────────────────────────────

class SessionLayer(BaseConfigLayer):
    """
    Time/situation-aware session configuration layer.

    Emits a settings delta based on the active SessionMode.
    Registers keybindings for manual session switching (,S prefix).

    Args:
        session:  Active session name (or None → auto-detect).
        leader:   Leader key prefix (default ",").
    """

    name        = "session"
    priority    = 55
    description = "Time-aware session: day / evening / night / focus / commute / present"

    def __init__(
        self,
        session: Optional[str] = None,
        leader:  str           = ",",
    ) -> None:
        self._mode:   SessionMode = _resolve_active_session(session)
        self._leader: str         = leader

        # Resolve spec (AUTO maps to its detected concrete mode)
        self._spec: SessionSpec = _SESSION_TABLE.get(
            self._mode,
            _SESSION_TABLE[SessionMode.DAY],
        )

        logger.info(
            "[SessionLayer] session=%s (%s)",
            self._mode.value, self._spec.description,
        )

    # ── Properties ────────────────────────────────────────────────────

    @property
    def active_session(self) -> SessionMode:
        return self._mode

    @property
    def active_spec(self) -> SessionSpec:
        return self._spec

    # ── Layer Implementation ───────────────────────────────────────────

    def _settings(self) -> ConfigDict:
        return dict(self._spec.settings_delta)

    def _keybindings(self) -> List[Keybind]:
        L = self._leader
        switch_bindings: List[Keybind] = [
            # ,S prefix = Session switch
            (f"{L}Sd",  "spawn --userscript session_switch.py day",     "normal"),
            (f"{L}Se",  "spawn --userscript session_switch.py evening", "normal"),
            (f"{L}Sn",  "spawn --userscript session_switch.py night",   "normal"),
            (f"{L}Sf",  "spawn --userscript session_switch.py focus",   "normal"),
            (f"{L}Sc",  "spawn --userscript session_switch.py commute", "normal"),
            (f"{L}Sp",  "spawn --userscript session_switch.py present", "normal"),
            (f"{L}S0",  "spawn --userscript session_switch.py auto",    "normal"),
            # Show current session
            (f"{L}Si",
             f"message-info 'Session: {self._mode.value} — {self._spec.description}'",
             "normal"),
        ]
        return switch_bindings

    # ── Introspection ──────────────────────────────────────────────────

    @classmethod
    def available_sessions(cls) -> List[str]:
        return sorted(m.value for m in _SESSION_TABLE)

    def describe(self) -> str:
        return (
            f"Session: {self._mode.value}\n"
            f"  Description  : {self._spec.description}\n"
            f"  Zoom hint    : {self._spec.zoom_hint}\n"
            f"  Settings Δ   : {list(self._spec.settings_delta.keys())}\n"
        )


__all__ = [
    "SessionMode",
    "SessionSpec",
    "SessionLayer",
    "_SESSION_TABLE",
    "_resolve_active_session",
]
