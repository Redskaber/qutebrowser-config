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
"""

from __future__ import annotations

from enum import Enum, auto
from typing import Any, Dict

from core.layer import BaseConfigLayer

ConfigDict = Dict[str, Any]


class PerformanceProfile(Enum):
    """Selectable performance tuning profiles."""
    BALANCED  = auto()   # good defaults for most hardware
    HIGH      = auto()   # more memory usage, faster experience
    LOW       = auto()   # constrained memory, slower
    LAPTOP    = auto()   # battery-aware


class PerformanceLayer(BaseConfigLayer):
    """
    Performance tuning layer.
    Renders profile into qutebrowser settings.
    """

    name = "performance"
    priority = 50
    description = "Performance tuning and caching"

    def __init__(self, profile: PerformanceProfile = PerformanceProfile.BALANCED):
        self._profile = profile

    def _settings(self) -> ConfigDict:
        common = self._common()

        if self._profile == PerformanceProfile.HIGH:
            common.update(self._high_perf())
        elif self._profile == PerformanceProfile.LOW:
            common.update(self._low_perf())
        elif self._profile == PerformanceProfile.LAPTOP:
            common.update(self._laptop_perf())

        return common

    def _common(self) -> ConfigDict:
        return {
            # ── Rendering ─────────────────────────────────────
            "content.canvas_reading": True,
            "scrolling.smooth": False,   # smooth scroll has CPU cost

            # ── Cache ─────────────────────────────────────────
            # 0 = Chromium default (~80MB)
            "content.cache.size": 0,

            # ── DNS prefetching ───────────────────────────────
            "content.dns_prefetch": True,

            # ── Completion ────────────────────────────────────
            "completion.delay": 0,
            "completion.web_history.max_items": 20,

            # ── History ───────────────────────────────────────
            "history_gap_interval": 30,

            # ── Tab loading ───────────────────────────────────
            "session.lazy_restore": True,

            # ── Screenshots ───────────────────────────────────
            "content.desktop_capture": False,
        }

    def _high_perf(self) -> ConfigDict:
        return {
            "content.cache.size": 256 * 1024 * 1024,   # 256 MB
            "content.dns_prefetch": True,
            "completion.delay": 0,
            "completion.web_history.max_items": 30,
        }

    def _low_perf(self) -> ConfigDict:
        return {
            "content.cache.size": 32 * 1024 * 1024,    # 32 MB
            "session.lazy_restore": True,
            "completion.web_history.max_items": 10,
            "scrolling.smooth": False,
        }

    def _laptop_perf(self) -> ConfigDict:
        return {
            "content.cache.size": 64 * 1024 * 1024,    # 64 MB
            "content.dns_prefetch": False,
            "session.lazy_restore": True,
        }


