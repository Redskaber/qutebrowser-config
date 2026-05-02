"""
strategies/download.py
======================
Download Handling Strategy

Strategies for resolving the download dispatcher and open-dispatcher
based on environment (Wayland, X11, NixOS, etc.) and user preference.

The download dispatcher is an external command qutebrowser invokes when
a download completes.  Selecting the right one is environment-dependent.

Strategy → dict[str, Any]  (a partial ConfigDict for download settings)
"""

from __future__ import annotations

import logging
import shutil
from typing import Any, Dict

from core.types import ConfigDict
from core.strategy import Strategy, StrategyRegistry

logger = logging.getLogger("qute.strategies.download")

DownloadConfig = Dict[str, Any]


# ─────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────
def _has(*cmds: str) -> bool:
    """Return True if all commands are on PATH."""
    return all(shutil.which(c) is not None for c in cmds)


# ─────────────────────────────────────────────
# Strategies
# ─────────────────────────────────────────────
class NoDispatcherStrategy(Strategy[DownloadConfig]):
    """No open-dispatcher — qutebrowser handles opens internally."""
    name = "none"

    def apply(self, context: ConfigDict) -> DownloadConfig:
        return {
            "downloads.location.directory": "~/Downloads",
            "downloads.location.prompt":    False,
            "downloads.open_dispatcher":    None,
            "downloads.prevent_mixed_content": True,
        }


class XdgOpenStrategy(Strategy[DownloadConfig]):
    """Use xdg-open to open completed downloads."""
    name = "xdg_open"

    def apply(self, context: ConfigDict) -> DownloadConfig:
        return {
            "downloads.location.directory": "~/Downloads",
            "downloads.location.prompt":    False,
            "downloads.open_dispatcher":    "xdg-open",
            "downloads.prevent_mixed_content": True,
        }

    def can_handle(self, context: ConfigDict) -> bool:
        return _has("xdg-open")


class RifleStrategy(Strategy[DownloadConfig]):
    """Use ranger's rifle as file dispatcher."""
    name = "rifle"

    def apply(self, context: ConfigDict) -> DownloadConfig:
        return {
            "downloads.location.directory": "~/Downloads",
            "downloads.location.prompt":    False,
            "downloads.open_dispatcher":    "rifle",
            "downloads.prevent_mixed_content": True,
        }

    def can_handle(self, context: ConfigDict) -> bool:
        return _has("rifle")


class HandlrStrategy(Strategy[DownloadConfig]):
    """Use handlr (xdg-utils replacement) for MIME-based dispatch."""
    name = "handlr"

    def apply(self, context: ConfigDict) -> DownloadConfig:
        return {
            "downloads.location.directory": "~/Downloads",
            "downloads.location.prompt":    False,
            "downloads.open_dispatcher":    "handlr open",
            "downloads.prevent_mixed_content": True,
        }

    def can_handle(self, context: ConfigDict) -> bool:
        return _has("handlr")


class AutoDetectDownloadStrategy(Strategy[DownloadConfig]):
    """
    Auto-detect the best download dispatcher.
    Falls back through: handlr → rifle → xdg-open → none
    """
    name = "auto"

    def apply(self, context: ConfigDict) -> DownloadConfig:
        candidates = [
            HandlrStrategy(),
            RifleStrategy(),
            XdgOpenStrategy(),
            NoDispatcherStrategy(),
        ]
        for candidate in candidates:
            if candidate.can_handle(context):
                logger.debug("[DownloadStrategy] auto-selected: %s", candidate.name)
                return candidate.apply(context)
        return NoDispatcherStrategy().apply(context)


# ─────────────────────────────────────────────
# Registry Factory
# ─────────────────────────────────────────────
def build_download_registry() -> StrategyRegistry[DownloadConfig]:
    """Return a populated download strategy registry."""
    registry: StrategyRegistry[DownloadConfig] = StrategyRegistry(
        default=AutoDetectDownloadStrategy()
    )
    for s in [
        NoDispatcherStrategy(),
        XdgOpenStrategy(),
        RifleStrategy(),
        HandlrStrategy(),
        AutoDetectDownloadStrategy(),
    ]:
        registry.register(s)

    logger.debug("[DownloadRegistry] registered: %s", registry.names())
    return registry


