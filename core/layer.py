"""
core/layer.py
=============
Hierarchical Layer System

Architecture:
  Layer[0:base] → Layer[1:privacy] → Layer[2:appearance] → Layer[N:user]
                   ↑ priority ordering, later layers override earlier

Principles:
  - Layered Architecture: clear separation of concern per layer
  - Dependency Inversion: layers depend on LayerProtocol, not each other
  - Open/Closed: new layers without touching existing ones
  - Incremental/Delta: layers emit only their changes (deltas)

Pattern: Composite + Strategy + Template Method
"""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Dict, Iterator, List, Optional, Tuple, cast

from .pipeline import ConfigPacket, Pipeline

logger = logging.getLogger("qute.layer")

ConfigDict = Dict[str, Any]


# ─────────────────────────────────────────────
# Layer Protocol (Dependency Inversion boundary)
# ─────────────────────────────────────────────
class LayerProtocol(ABC):
    """
    Abstract contract every configuration layer must satisfy.
    Layers are independent units; the LayerStack wires them.
    """

    #: unique machine name, e.g. "base", "privacy", "appearance"
    name: str

    #: lower = applied earlier (can be overridden by higher layers)
    priority: int = 50

    #: human description
    description: str = ""

    @abstractmethod
    def build(self) -> ConfigDict:
        """
        Return this layer's configuration delta.
        Must be pure (no side effects).
        Keys that are absent means "I don't care about this key".
        """
        ...

    def validate(self, data: ConfigDict) -> List[str]:
        """
        Optional: return list of error strings.
        Empty list = valid.
        """
        return []

    def pipeline(self) -> Optional[Pipeline]:
        """
        Optional: return a Pipeline to post-process this layer's output.
        None = no extra processing.
        """
        return None

    def __repr__(self) -> str:
        return f"<Layer:{self.name}[{self.priority}]>"


# ─────────────────────────────────────────────
# Layer Registration Record
# ─────────────────────────────────────────────
@dataclass
class LayerRecord:
    layer: LayerProtocol
    enabled: bool = True
    tags: List[str] = field(default_factory=list[str])


# ─────────────────────────────────────────────
# Layer Stack (Composite)
# ─────────────────────────────────────────────
class LayerStack:
    """
    Ordered collection of layers.
    Resolves final config by merging in priority order (lowest first).

    Usage:
        stack = LayerStack()
        stack.register(BaseLayer())
        stack.register(PrivacyLayer())
        final = stack.resolve()
    """

    def __init__(self):
        self._records: List[LayerRecord] = []

    def register(
        self,
        layer: LayerProtocol,
        enabled: bool = True,
        tags: Optional[List[str]] = None,
    ) -> "LayerStack":
        record = LayerRecord(
            layer=layer,
            enabled=enabled,
            tags=tags or [],
        )
        self._records.append(record)
        # Sort by priority after each registration
        self._records.sort(key=lambda r: r.layer.priority)
        logger.debug("[LayerStack] registered: %s (priority=%d)", layer.name, layer.priority)
        return self

    def enable(self, name: str) -> None:
        for r in self._records:
            if r.layer.name == name:
                r.enabled = True
                logger.info("[LayerStack] enabled: %s", name)
                return
        raise KeyError(f"Layer not found: {name}")

    def disable(self, name: str) -> None:
        for r in self._records:
            if r.layer.name == name:
                r.enabled = False
                logger.info("[LayerStack] disabled: %s", name)
                return
        raise KeyError(f"Layer not found: {name}")

    def resolve(self) -> Dict[str, ConfigPacket]:
        """
        Build and merge all enabled layers.
        Returns dict of layer_name → packet (for introspection).
        Also computes final merged config accessible via .merged.
        """
        results: Dict[str, ConfigPacket] = {}
        self._merged: ConfigDict = {}

        for record in self._records:
            if not record.enabled:
                logger.debug("[LayerStack] skip disabled: %s", record.layer.name)
                continue

            layer = record.layer
            try:
                raw = layer.build()
            except Exception as e:
                logger.error("[LayerStack] build error in %s: %s", layer.name, e)
                raw = {}

            errors = layer.validate(raw)
            packet = ConfigPacket(
                source=f"layer:{layer.name}",
                data=raw,
                errors=errors,
            )

            # Run layer-specific pipeline if defined
            pipe = layer.pipeline()
            if pipe is not None:
                packet = pipe.run(packet)

            results[layer.name] = packet

            # Merge into accumulated config (later = higher priority)
            self._merged = _deep_merge(self._merged, packet.data)
            logger.info(
                "[LayerStack] merged layer=%s keys=%d total_keys=%d",
                layer.name, len(packet.data), len(self._merged)
            )

        return results

    @property
    def merged(self) -> ConfigDict:
        """Access last resolved merged config."""
        if not hasattr(self, "_merged"):
            raise RuntimeError("Call resolve() before accessing merged config")
        return self._merged

    def layers(self) -> Iterator[LayerProtocol]:
        for r in self._records:
            yield r.layer

    def get(self, name: str) -> Optional[LayerProtocol]:
        for r in self._records:
            if r.layer.name == name:
                return r.layer
        return None

    def summary(self) -> str:
        lines = ["LayerStack:"]
        for r in self._records:
            status = "✓" if r.enabled else "✗"
            lines.append(f"  [{status}] {r.layer.name:20s} priority={r.layer.priority}")
        return "\n".join(lines)


# ─────────────────────────────────────────────
# Base Layer (template for all concrete layers)
# ─────────────────────────────────────────────
class BaseConfigLayer(LayerProtocol, ABC):
    """
    Template Method pattern:
    Subclasses implement _settings(), _keybindings(), _aliases() separately;
    build() orchestrates them.
    """

    def build(self) -> ConfigDict:
        result: ConfigDict = {}

        settings = self._settings()
        if settings:
            result["settings"] = settings

        keybindings = self._keybindings()
        if keybindings:
            result["keybindings"] = keybindings

        aliases = self._aliases()
        if aliases:
            result["aliases"] = aliases

        return result

    def _settings(self) -> ConfigDict:
        return {}

    def _keybindings(self) -> List[Tuple[str, str, str]]:
        # [(key, command, mode), ...]
        return []

    def _aliases(self) -> ConfigDict:
        return {}


# ─────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────
def _deep_merge(base: ConfigDict, overlay: ConfigDict) -> ConfigDict:
    result = base.copy()
    for k, v in overlay.items():
        if k in result and isinstance(result[k], dict) and isinstance(v, dict):
            v = cast(ConfigDict, v)
            result[k] = _deep_merge(result[k], v)
        elif k in result and isinstance(result[k], list) and isinstance(v, list):
            result[k] = result[k] + v   # lists: extend (for keybindings)
        else:
            result[k] = v
    return result


