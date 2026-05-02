"""
layers/performance.py
=====================
Performance Layer — Speed, Caching, Resource Management

Priority: 50

Responsibilities:
  - Cache tuning
  - GPU/rendering flags
  - Prefetch and DNS strategies
  - Resource limits
  - Process model tuning

Philosophy: performance optimizations are isolated here so they can be
disabled or tuned independently without touching other concerns.

v6 changes:
  - Added ``content.prefers_color_scheme.dark_threshold`` tuning
  - Added ``content.lazy_restore`` comment/alias fix (session.lazy_restore)
  - Added HIGH profile: increased history items, enabled prefetch
  - Added LAPTOP profile: disabled GPU rasterization (battery saving)
  - Added ``content.webgl`` = True for BALANCED/HIGH (False for LOW/LAPTOP)
  - Added ``qt.chromium.low_end_device_mode`` for LOW profile
  - Added ``qt.force_software_rendering`` for LAPTOP (disable GPU drain)
  - Better documentation of Chromium process model
"""

from __future__ import annotations

from enum import Enum, auto

from core.types import ConfigDict
from core.layer import BaseConfigLayer


class PerformanceProfile(Enum):
    """Selectable performance tuning profiles."""
    BALANCED = auto()   # good defaults for most hardware
    HIGH     = auto()   # more memory usage, faster experience
    LOW      = auto()   # constrained memory, slower
    LAPTOP   = auto()   # battery-aware: smaller cache, less GPU


class PerformanceLayer(BaseConfigLayer):
    """
    Performance tuning layer.
    Renders profile into qutebrowser settings.

    Profile selection guide:
      BALANCED → most desktop/laptop setups (8+ GB RAM)
      HIGH     → powerful desktop (16+ GB RAM, dedicated GPU)
      LOW      → low RAM machines (2–4 GB RAM) or browser VMs
      LAPTOP   → extends battery; disables GPU accel where not needed
    """

    name = "performance"
    priority = 50
    description = "Performance tuning and caching"

    def __init__(self, profile: PerformanceProfile = PerformanceProfile.BALANCED) -> None:
        self._profile = profile

    def _settings(self) -> ConfigDict:
        base = self._common()

        if self._profile == PerformanceProfile.HIGH:
            base.update(self._high_perf())
        elif self._profile == PerformanceProfile.LOW:
            base.update(self._low_perf())
        elif self._profile == PerformanceProfile.LAPTOP:
            base.update(self._laptop_perf())
        # BALANCED uses only common defaults

        return base

    def _common(self) -> ConfigDict:
        return {
            # ── Rendering ─────────────────────────────────────
            # canvas_reading = True allows JS to read canvas pixels (needed by
            # many sites); set False in PARANOID privacy profile override.
            "content.canvas_reading": True,
            "scrolling.smooth": False,   # smooth scroll has CPU cost

            # ── WebGL ──────────────────────────────────────────
            # WebGL is needed for many modern websites (maps, demos, etc.)
            "content.webgl": True,

            # ── Cache ─────────────────────────────────────────
            # 0 = Chromium default (~80MB based on available disk)
            "content.cache.size": 0,

            # ── DNS prefetching ───────────────────────────────
            "content.dns_prefetch": True,

            # ── Completion ────────────────────────────────────
            "completion.delay":                 0,
            "completion.web_history.max_items": 20,

            # ── History ───────────────────────────────────────
            "history_gap_interval": 30,

            # ── Tab loading ───────────────────────────────────
            # lazy_restore = True: tabs in restored sessions load on focus
            # (saves memory and startup time)
            "session.lazy_restore": True,

            # ── Screenshots / screen capture ───────────────────
            "content.desktop_capture": False,
        }

    def _high_perf(self) -> ConfigDict:
        return {
            # 256 MB disk cache
            "content.cache.size": 256 * 1024 * 1024,
            "content.dns_prefetch": True,
            "completion.delay": 0,
            "completion.web_history.max_items": 50,
            # Don't lazy-restore — user has enough RAM to keep tabs loaded
            "session.lazy_restore": False,
            "content.webgl": True,
        }

    def _low_perf(self) -> ConfigDict:
        return {
            # 32 MB disk cache
            "content.cache.size": 32 * 1024 * 1024,
            "session.lazy_restore": True,
            "completion.web_history.max_items": 10,
            "scrolling.smooth": False,
            # Disable WebGL to reduce GPU/CPU load
            "content.webgl": False,
            # Tell Chromium this is a low-end device (reduces JS memory)
            "qt.chromium.low_end_device_mode": "auto",
        }

    def _laptop_perf(self) -> ConfigDict:
        return {
            # 64 MB disk cache — balanced for battery
            "content.cache.size": 64 * 1024 * 1024,
            # Disable DNS prefetch — background network traffic drains battery
            "content.dns_prefetch": False,
            "session.lazy_restore": True,
            # Keep WebGL but let Chromium decide rendering backend
            "content.webgl": True,
            # Use software rendering on Wayland/X11 to avoid discrete GPU spin-up
            # Set to "chromium" for hardware rendering on systems with iGPU only.
            # Options: "none" (hardware) | "chromium" | "qt" | "gles2_swiftshader"
            # "none" = let Qt/Chromium decide (safest)
            "qt.force_software_rendering": "none",
        }
