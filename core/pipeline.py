"""
core/pipeline.py
================
Pipeline Engine

Architecture::

    ConfigSource → [Transform] → [Validate] → [Merge] → ConfigSink

Each stage receives an immutable ``ConfigPacket`` and returns a new one.
The pipeline halts on the first exception raised by a stage; all other
stages run to completion even if warnings accumulate.

Principles:
  - Single Responsibility: each stage does exactly one thing
  - Open/Closed: new stages via subclassing, no modification of existing
  - Dependency Inversion: stages depend on the PipeStage abstraction
  - Immutability: ConfigPacket is effectively immutable (always copied)

Pattern: Chain of Responsibility + Decorator

v7 changes:
  - ConfigPacket field default_factory values corrected:
      field(default_factory=ConfigDict)   → field(default_factory=dict)
      field(default_factory=dict[str,Any])→ field(default_factory=dict)
      field(default_factory=list[str])    → field(default_factory=list)
    These were Pyright strict-mode errors: ``dict[str, Any]`` and
    ``list[str]`` are generic aliases used for type hints, not callable
    factories.  The correct factories are plain ``dict`` and ``list``.

Strict-mode notes (Pyright):
  - Removed unused ``Generic`` and ``Optional`` imports.
  - ``_deep_merge`` annotated with explicit ``Dict[str, Any]`` signatures
    to avoid ``dict[Unknown, Unknown]`` inference.
  - ``TransformStage`` / ``ValidateStage`` use fully-typed ``Callable``
    parameters.
"""

from __future__ import annotations

import functools
import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, Iterator, List, TypeVar, cast

logger = logging.getLogger("qute.pipeline")

T = TypeVar("T")
ConfigDict = Dict[str, Any]


# ─────────────────────────────────────────────
# Domain Types
# ─────────────────────────────────────────────
@dataclass
class ConfigPacket:
    """
    Data unit flowing through the pipeline.

    All mutation methods return a *new* ConfigPacket — the original is
    never modified.  This makes pipeline stages easy to test and reason about.

    ``with_data``    merges additional keys on top of the current data.
    ``replace_data`` discards current data entirely and uses the new dict.
    Use ``replace_data`` in TransformStage when the transform produces a
    completely new key-set (e.g. key renaming).
    """
    source:   str            # origin label, e.g. "layer:base"
    data:     ConfigDict     = field(default_factory=dict)   # v7 fix: was ConfigDict
    meta:     Dict[str, Any] = field(default_factory=dict)   # v7 fix: was dict[str, Any]
    errors:   List[str]      = field(default_factory=list)   # v7 fix: was list[str]
    warnings: List[str]      = field(default_factory=list)   # v7 fix: was list[str]

    def with_data(self, extra: ConfigDict) -> "ConfigPacket":
        """Return a new packet with ``extra`` merged *on top of* current data."""
        return ConfigPacket(
            source=self.source,
            data={**self.data, **extra},
            meta=self.meta.copy(),
            errors=self.errors.copy(),
            warnings=self.warnings.copy(),
        )

    def replace_data(self, data: ConfigDict) -> "ConfigPacket":
        """Return a new packet whose data is *replaced* by ``data`` entirely."""
        return ConfigPacket(
            source=self.source,
            data=data,
            meta=self.meta.copy(),
            errors=self.errors.copy(),
            warnings=self.warnings.copy(),
        )

    def with_error(self, msg: str) -> "ConfigPacket":
        return ConfigPacket(
            source=self.source,
            data=self.data.copy(),
            meta=self.meta.copy(),
            errors=self.errors + [msg],
            warnings=self.warnings.copy(),
        )

    def with_warning(self, msg: str) -> "ConfigPacket":
        return ConfigPacket(
            source=self.source,
            data=self.data.copy(),
            meta=self.meta.copy(),
            errors=self.errors.copy(),
            warnings=self.warnings + [msg],
        )

    def with_meta(self, key: str, value: Any) -> "ConfigPacket":
        new_meta = {**self.meta, key: value}
        return ConfigPacket(
            source=self.source,
            data=self.data.copy(),
            meta=new_meta,
            errors=self.errors.copy(),
            warnings=self.warnings.copy(),
        )

    @property
    def ok(self) -> bool:
        return len(self.errors) == 0

    def __repr__(self) -> str:
        return (
            f"ConfigPacket(source={self.source!r}, "
            f"keys={list(self.data)[:5]}, "
            f"errors={len(self.errors)}, "
            f"warnings={len(self.warnings)})"
        )


# ─────────────────────────────────────────────
# Pipeline Stage Abstraction
# ─────────────────────────────────────────────
class PipeStage(ABC):
    """
    Abstract pipeline stage.
    Receives a packet, returns a (possibly modified) packet.
    Raising an exception aborts the pipeline.
    """

    @property
    @abstractmethod
    def name(self) -> str: ...

    @abstractmethod
    def process(self, packet: ConfigPacket) -> ConfigPacket: ...

    def __repr__(self) -> str:
        return f"<Stage:{self.name}>"


# ─────────────────────────────────────────────
# Pipeline
# ─────────────────────────────────────────────
class Pipeline:
    """
    Ordered chain of PipeStages.

    Usage::

        pipeline = (
            Pipeline("privacy")
            .pipe(LogStage("pre"))
            .pipe(ValidateStage({...}))
            .pipe(LogStage("post"))
        )
        result = pipeline.run(packet)
    """

    def __init__(self, name: str = "pipeline") -> None:
        self._name   = name
        self._stages: List[PipeStage] = []

    @property
    def name(self) -> str:
        return self._name

    def pipe(self, stage: PipeStage) -> "Pipeline":
        """Fluent: append a stage and return self."""
        self._stages.append(stage)
        return self

    def run(self, packet: ConfigPacket) -> ConfigPacket:
        """
        Execute all stages in order.
        Any stage that raises will propagate; the pipeline is aborted.
        """
        current = packet
        for stage in self._stages:
            try:
                current = stage.process(current)
                logger.debug(
                    "[Pipeline:%s] stage=%s ok=%s",
                    self._name, stage.name, current.ok,
                )
            except Exception as exc:
                logger.error(
                    "[Pipeline:%s] stage=%s raised: %s",
                    self._name, stage.name, exc,
                )
                raise
        return current

    def stages(self) -> Iterator[PipeStage]:
        yield from self._stages

    def __len__(self) -> int:
        return len(self._stages)

    def __repr__(self) -> str:
        return f"<Pipeline:{self._name} stages={[s.name for s in self._stages]}>"


# ─────────────────────────────────────────────
# Built-in Stages
# ─────────────────────────────────────────────

class LogStage(PipeStage):
    """Emit a debug log line; pass packet through unchanged."""

    def __init__(self, label: str = "") -> None:
        self._label = label

    @property
    def name(self) -> str:
        return f"log:{self._label}"

    def process(self, packet: ConfigPacket) -> ConfigPacket:
        logger.debug(
            "[LogStage:%s] source=%s keys=%d errors=%d",
            self._label,
            packet.source,
            len(packet.data),
            len(packet.errors),
        )
        return packet


class ValidateStage(PipeStage):
    """
    Run key-specific validators; add errors to packet on failure.

    Args:
        rules: mapping of key → predicate(value) → bool
               Predicate returns True if the value is valid.

    Example::

        ValidateStage({
            "content.blocking.enabled": lambda v: isinstance(v, bool),
            "content.cookies.accept": lambda v: v in ("all", "no-3rdparty", "never"),
        })

    The stage inspects both the top-level dict and ``data["settings"]`` so it
    works correctly whether the packet carries a raw flat dict or the nested
    structure produced by ``BaseConfigLayer.build()``.
    """

    def __init__(self, rules: Dict[str, Callable[[Any], bool]]) -> None:
        self._rules = rules

    @property
    def name(self) -> str:
        return "validate"

    def process(self, packet: ConfigPacket) -> ConfigPacket:
        # Support both flat {"key": value} and nested {"settings": {"key": value}}
        flat     = packet.data
        settings = packet.data.get("settings", {})

        errors: List[str] = []
        for key, predicate in self._rules.items():
            value = flat.get(key) if key in flat else settings.get(key)
            if value is not None and not predicate(value):
                errors.append(
                    f"[ValidateStage] key={key!r} value={value!r} failed validation"
                )

        if errors:
            result = packet
            for err in errors:
                result = result.with_warning(err)
                logger.warning("[ValidateStage] %s", err)
            return result

        return packet


class TransformStage(PipeStage):
    """
    Apply a transform function to the packet's data dict.

    Args:
        fn:    (data: ConfigDict) → ConfigDict — must return a new dict.
        label: descriptive name for logging.
    """

    def __init__(
        self,
        fn:    Callable[[ConfigDict], ConfigDict],
        label: str = "transform",
    ) -> None:
        self._fn    = fn
        self._label = label

    @property
    def name(self) -> str:
        return f"transform:{self._label}"

    def process(self, packet: ConfigPacket) -> ConfigPacket:
        try:
            new_data = self._fn(packet.data)
            return packet.replace_data(new_data)
        except Exception as exc:
            logger.error("[TransformStage:%s] transform raised: %s", self._label, exc)
            return packet.with_error(f"transform:{self._label}: {exc}")


class FilterStage(PipeStage):
    """
    Remove keys from the data dict that fail a predicate.

    Args:
        predicate: (key, value) → bool — return True to KEEP the key.
    """

    def __init__(
        self,
        predicate: Callable[[str, Any], bool],
        label:     str = "filter",
    ) -> None:
        self._predicate = predicate
        self._label     = label

    @property
    def name(self) -> str:
        return f"filter:{self._label}"

    def process(self, packet: ConfigPacket) -> ConfigPacket:
        filtered = {
            k: v for k, v in packet.data.items()
            if self._predicate(k, v)
        }
        removed = len(packet.data) - len(filtered)
        if removed:
            logger.debug("[FilterStage:%s] removed %d keys", self._label, removed)
        return packet.replace_data(filtered)


class MergeStage(PipeStage):
    """
    Merge a static overlay dict *on top of* the current packet data.
    Useful for injecting last-minute defaults.
    """

    def __init__(self, overlay: ConfigDict, label: str = "merge") -> None:
        self._overlay = overlay
        self._label   = label

    @property
    def name(self) -> str:
        return f"merge:{self._label}"

    def process(self, packet: ConfigPacket) -> ConfigPacket:
        merged = {**packet.data, **self._overlay}
        return packet.replace_data(merged)


# ─────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────

@functools.lru_cache(maxsize=None)
def _noop_pipeline() -> Pipeline:
    """Return a shared empty pipeline (identity transform)."""
    return Pipeline("noop")


def _deep_merge(
    base:    Dict[str, Any],
    overlay: Dict[str, Any],
) -> Dict[str, Any]:
    """Recursively merge *overlay* into *base*.  Overlay wins on conflicts."""
    result: Dict[str, Any] = base.copy()
    for k, v in overlay.items():
        existing = result.get(k)
        if isinstance(existing, dict) and isinstance(v, dict):
            existing = cast(Dict[str, Any], existing)
            v_dict   = cast(Dict[str, Any], v)
            result[k] = _deep_merge(existing, v_dict)
        else:
            result[k] = v
    return result
