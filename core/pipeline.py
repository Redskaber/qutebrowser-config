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
"""

from __future__ import annotations

import functools
import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, Generic, Iterator, List, Optional, TypeVar

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
    source:   str                         # origin label, e.g. "layer:base"
    data:     ConfigDict = field(default_factory=dict)
    meta:     Dict[str, Any] = field(default_factory=dict)
    errors:   List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)

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

    def with_meta(self, **kw: Any) -> "ConfigPacket":
        return ConfigPacket(
            source=self.source,
            data=self.data.copy(),
            meta={**self.meta, **kw},
            errors=self.errors.copy(),
            warnings=self.warnings.copy(),
        )

    @property
    def ok(self) -> bool:
        return len(self.errors) == 0


# ─────────────────────────────────────────────
# Stage Abstraction  (Dependency Inversion)
# ─────────────────────────────────────────────

class PipeStage(ABC):
    """Base abstraction for a pipeline stage."""

    name: str = "unnamed"

    @abstractmethod
    def process(self, packet: ConfigPacket) -> ConfigPacket:
        ...

    def __repr__(self) -> str:
        return f"<PipeStage:{self.name}>"


class PipeFilter(PipeStage):
    """Stage that conditionally passes or marks a packet."""

    @abstractmethod
    def should_pass(self, packet: ConfigPacket) -> bool:
        ...

    def process(self, packet: ConfigPacket) -> ConfigPacket:
        if self.should_pass(packet):
            return packet
        return packet.with_warning(f"[{self.name}] packet filtered out")


# ─────────────────────────────────────────────
# Pipeline Engine
# ─────────────────────────────────────────────

class Pipeline:
    """
    Composable, ordered pipeline of ``PipeStage`` instances.

    Usage::

        pipeline = (
            Pipeline("config")
            .pipe(ExpandEnvVars())
            .pipe(ValidateKeys())
            .pipe(MergeDefaults())
        )
        result = pipeline.run(packet)
    """

    def __init__(self, name: str = "pipeline") -> None:
        self.name = name
        self._stages: List[PipeStage] = []
        self._hooks_pre:  List[Callable[[ConfigPacket], None]] = []
        self._hooks_post: List[Callable[[ConfigPacket], None]] = []

    def pipe(self, stage: PipeStage) -> "Pipeline":
        """Append a stage and return ``self`` for fluent chaining."""
        self._stages.append(stage)
        logger.debug("[%s] registered stage: %s", self.name, stage.name)
        return self

    def on_packet(self, hook: Callable[[ConfigPacket], None]) -> "Pipeline":
        """Register a pre-run hook (observability, e.g. logging)."""
        self._hooks_pre.append(hook)
        return self

    def after_packet(self, hook: Callable[[ConfigPacket], None]) -> "Pipeline":
        """Register a post-run hook."""
        self._hooks_post.append(hook)
        return self

    def run(self, packet: ConfigPacket) -> ConfigPacket:
        """
        Execute all stages in order.

        Halts immediately when a stage raises an exception (the error is
        captured in ``packet.errors``); warnings do NOT halt the pipeline.
        """
        current = packet
        for hook in self._hooks_pre:
            hook(current)

        for stage in self._stages:
            try:
                current = stage.process(current)
                logger.debug(
                    "[%s/%s] ok  keys=%d  errors=%d",
                    self.name, stage.name,
                    len(current.data), len(current.errors),
                )
            except Exception as exc:
                current = current.with_error(f"[{stage.name}] exception: {exc}")
                logger.exception("[%s/%s] fatal — halting pipeline", self.name, stage.name)
                break  # halt on unhandled exception

        for hook in self._hooks_post:
            hook(current)
        return current

    def __iter__(self) -> Iterator[PipeStage]:
        return iter(self._stages)

    def __repr__(self) -> str:
        stages = " → ".join(s.name for s in self._stages)
        return f"<Pipeline:{self.name} [{stages}]>"


# ─────────────────────────────────────────────
# Built-in Stages
# ─────────────────────────────────────────────

class MergeStage(PipeStage):
    """
    Merge a static dict overlay into the packet data.

    ``deep=True``  (default): nested dicts are merged recursively.
    ``deep=False``: flat last-write-wins merge.
    The overlay always wins over packet data for the same key.
    """
    name = "merge"

    def __init__(self, overlay: ConfigDict, deep: bool = True) -> None:
        self._overlay = overlay
        self._deep = deep

    def process(self, packet: ConfigPacket) -> ConfigPacket:
        if self._deep:
            merged = _deep_merge(packet.data, self._overlay)
        else:
            merged = {**packet.data, **self._overlay}
        return ConfigPacket(
            source=packet.source,
            data=merged,
            meta=packet.meta,
            errors=packet.errors,
            warnings=packet.warnings,
        )


class TransformStage(PipeStage):
    """
    Apply a pure function ``ConfigDict → ConfigDict`` to the packet data.

    The function receives the *entire* current data dict and must return the
    *entire* new data dict.  The packet data is **replaced** (not merged) with
    the function's return value — this is correct for key-renaming or
    structural transforms.

    If the function raises, the error is recorded and the original packet is
    returned unchanged (no halt — use a pipeline halt only for fatal stages).
    """
    name = "transform"

    def __init__(
        self,
        fn: Callable[[ConfigDict], ConfigDict],
        label: str = "transform",
    ) -> None:
        self._fn = fn
        self.name = label

    def process(self, packet: ConfigPacket) -> ConfigPacket:
        try:
            new_data = self._fn(packet.data)
            # replace_data: fn owns the full output dict, do not merge with old.
            return packet.replace_data(new_data)
        except Exception as exc:
            return packet.with_error(f"transform [{self.name}]: {exc}")


class ValidateStage(PipeStage):
    """
    Validate packet data against a set of predicate rules.

    ``rules`` maps a dot-notation key to a ``Callable[[value], bool]``.
    The stage looks up keys in ``packet.data`` **and** inside a nested
    ``packet.data["settings"]`` dict (which is the structure layers produce).
    Failures add warnings — they do NOT halt the pipeline.
    """
    name = "validate"

    def __init__(self, rules: Dict[str, Callable[[Any], bool]]) -> None:
        self._rules = rules

    def process(self, packet: ConfigPacket) -> ConfigPacket:
        result = packet
        # Support both flat packets and the nested {settings: {…}} structure.
        flat   = packet.data
        nested = packet.data.get("settings", {})

        for key, rule in self._rules.items():
            val = flat.get(key) if key in flat else nested.get(key)
            if val is not None and not rule(val):
                result = result.with_warning(
                    f"validation: {key}={val!r} failed rule"
                )
        return result


class ConditionalStage(PipeStage):
    """Apply ``inner`` stage only when ``predicate(packet)`` is True."""
    name = "conditional"

    def __init__(
        self,
        predicate: Callable[[ConfigPacket], bool],
        inner: PipeStage,
    ) -> None:
        self._predicate = predicate
        self._inner = inner
        self.name = f"if({inner.name})"

    def process(self, packet: ConfigPacket) -> ConfigPacket:
        if self._predicate(packet):
            return self._inner.process(packet)
        return packet


class LogStage(PipeStage):
    """Observability tap — logs packet state without modification."""
    name = "log"

    def __init__(self, label: str = "") -> None:
        self.name = f"log[{label}]" if label else "log"
        self._label = label

    def process(self, packet: ConfigPacket) -> ConfigPacket:
        logger.info(
            "[%s] source=%s  keys=%d  errors=%d  warnings=%d",
            self._label, packet.source,
            len(packet.data), len(packet.errors), len(packet.warnings),
        )
        return packet


# ─────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────

def _deep_merge(base: dict, overlay: dict) -> dict:
    """Recursively merge ``overlay`` into ``base``.  Overlay wins."""
    result = base.copy()
    for k, v in overlay.items():
        if k in result and isinstance(result[k], dict) and isinstance(v, dict):
            result[k] = _deep_merge(result[k], v)
        else:
            result[k] = v
    return result


def stage(label: str):
    """Decorator: wrap a plain function as a named ``TransformStage`` factory."""
    def decorator(fn: Callable[[ConfigDict], ConfigDict]) -> Callable[[], TransformStage]:
        @functools.wraps(fn)
        def factory() -> TransformStage:
            return TransformStage(fn, label=label)
        return factory
    return decorator
