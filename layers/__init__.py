"""
layers/__init__.py
==================
Public surface for the layers package.

Layer priority table:
  10  BaseLayer        — foundational qutebrowser defaults
  20  PrivacyLayer     — security & privacy hardening
  30  AppearanceLayer  — themes, fonts, colors
  40  BehaviorLayer    — UX, Vim keybindings, per-host overrides
  50  PerformanceLayer — cache, DNS, rendering
  90  UserLayer        — personal overrides (highest priority)

Space between 50–90 reserved for user-inserted layers (60–80).
"""
from layers.base        import BaseLayer
from layers.privacy     import PrivacyLayer, PrivacyProfile
from layers.appearance  import AppearanceLayer, ColorScheme, THEMES
from layers.behavior    import BehaviorLayer, HostPolicy
from layers.performance import PerformanceLayer, PerformanceProfile
from layers.user        import UserLayer

__all__ = [
    "BaseLayer",
    "PrivacyLayer", "PrivacyProfile",
    "AppearanceLayer", "ColorScheme", "THEMES",
    "BehaviorLayer", "HostPolicy",
    "PerformanceLayer", "PerformanceProfile",
    "UserLayer",
]
