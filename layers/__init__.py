"""
layers/__init__.py
==================
Public surface for the layers package.

Layer priority table:
  10  BaseLayer        — foundational qutebrowser defaults
  20  PrivacyLayer     — security & privacy hardening
  27  Network Layer    — Proxy, DNS, and Network-Level Configuration
  30  AppearanceLayer  — themes, fonts, colors
  40  BehaviorLayer    — UX, Vim keybindings, per-host overrides
  45  ContextLayer     — Context, Situational Browser Modes
  50  PerformanceLayer — cache, DNS, rendering
  55  Session Layer    — Time-Aware and System-Aware Configuration
  90  UserLayer        — personal overrides (highest priority)

Space between 50–90 reserved for user-inserted layers (60–80).
"""
from layers.base        import BaseLayer
from layers.privacy     import PrivacyLayer, PrivacyProfile
from layers.network     import NetworkMode, NetworkSpec, NetworkLayer, _NETWORK_TABLE, _build_spec_table, _resolve_active_mode # type: ignore[import]
from layers.appearance  import AppearanceLayer, ColorScheme, THEMES, parse_px
from layers.behavior    import BehaviorLayer, HostPolicy
from layers.context     import ContextMode, ContextSpec, ContextLayer
from layers.performance import PerformanceLayer, PerformanceProfile
from layers.session     import SessionMode, SessionSpec, SessionLayer, _SESSION_TABLE, _resolve_active_session # type: ignore[import]
from layers.user        import UserLayer

__all__ = [
    "BaseLayer",
    "PrivacyLayer", "PrivacyProfile",
    "NetworkLayer", "NetworkMode", "NetworkSpec",
    "_NETWORK_TABLE", "_build_spec_table", "_resolve_active_mode",
    "AppearanceLayer", "ColorScheme", "THEMES", "parse_px",
    "BehaviorLayer", "HostPolicy",
    "ContextMode", "ContextSpec", "ContextLayer",
    "PerformanceLayer", "PerformanceProfile",
    "SessionMode", "SessionSpec", "SessionLayer",
    "_SESSION_TABLE", "_resolve_active_session",
    "UserLayer",
]
