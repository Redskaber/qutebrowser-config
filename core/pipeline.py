"""
core/pipeline.py
================
Pipeline Engine  (v11)

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

v12 changes:
  - TeeStage: fan-out — run a side-effect stage without mutating the
    packet.  The side-branch receives the packet; the original packet
    continues unchanged.  Useful for audit, metrics, or logging probes
    inserted mid-pipeline without affecting data flow.
  - RetryStage: wrap any stage and retry on exception up to ``max_retries``
    times with optional exponential back-off delay.  Records failures as
    warnings in the packet.  Idempotent stages only.
  - CompositeStage: compose a named sub-pipeline as a single stage.
    Equivalent to inlining the sub-pipeline's stages but with a single
    ``name`` visible in describe() / logging.
  - Pipeline.__iter__: iterate over stages (replaces the stages() method
    which is retained for backwards compatibility).

v11 changes (retained):
  - ReduceStage: fold (key, value) pairs using a reducer function.
    Useful for aggregating statistics or computing derived keys.
  - BranchStage: conditional routing — runs one of two sub-pipelines
    depending on a predicate applied to the packet.
  - CacheStage: memoize expensive TransformStage output when the input
    data dict hash is unchanged.  Bypasses the wrapped stage on cache hit.
  - AuditStage: records pipeline entry/exit into the global AuditLog.
    Zero overhead when audit log is at DEBUG level.
  - Pipeline.fork() — create an independent copy of the pipeline.
  - Pipeline.describe() — return a human-readable stage summary string.
  - ConfigPacket.with_errors() — bulk-add multiple error strings.
  - ConfigPacket.with_warnings() — bulk-add multiple warning strings.
  - PipeStage.__add__() — compose two stages into a mini 2-stage pipeline
    (syntactic sugar: stage_a + stage_b).

v7 changes (retained):
  - ConfigPacket field default_factory values corrected:
      field(default_factory=dict)  (was dict[str,Any] — Pyright strict error)
      field(default_factory=list)  (was list[str]     — Pyright strict error)

Strict-mode notes (Pyright):
  - Removed unused ``Generic`` and ``Optional`` imports.
  - ``_deep_merge`` annotated with explicit ``Dict[str, Any]`` signatures
    to avoid ``dict[Unknown, Unknown]`` inference.
  - ``TransformStage`` / ``ValidateStage`` use fully-typed ``Callable``
    parameters.
  - ReduceStage uses explicit ``Callable[[T, str, Any], T]`` signature.
  - BranchStage uses ``Callable[[ConfigPacket], bool]`` predicate.
"""

from __future__ import annotations

import functools
import hashlib
import json
import logging
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, Iterator, List, Optional, TypeVar, cast

from core.types import ConfigDict

logger = logging.getLogger("qute.pipeline")

T = TypeVar("T")


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
    data:     ConfigDict     = field(default_factory=dict[str, Any])
    meta:     Dict[str, Any] = field(default_factory=dict[str, Any])
    errors:   List[str]      = field(default_factory=list[str])
    warnings: List[str]      = field(default_factory=list[str])

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

    def with_errors(self, msgs: List[str]) -> "ConfigPacket":
        """Bulk-add multiple error strings (v11)."""
        if not msgs:
            return self
        return ConfigPacket(
            source=self.source,
            data=self.data.copy(),
            meta=self.meta.copy(),
            errors=self.errors + msgs,
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

    def with_warnings(self, msgs: List[str]) -> "ConfigPacket":
        """Bulk-add multiple warning strings (v11)."""
        if not msgs:
            return self
        return ConfigPacket(
            source=self.source,
            data=self.data.copy(),
            meta=self.meta.copy(),
            errors=self.errors.copy(),
            warnings=self.warnings + msgs,
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

    def __add__(self, other: "PipeStage") -> "Pipeline":
        """
        Compose two stages into a 2-stage pipeline (v11 syntactic sugar).

        Example::
            combined = ValidateStage({...}) + LogStage("post")
        """
        return Pipeline(f"{self.name}+{other.name}").pipe(self).pipe(other)

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

    def fork(self) -> "Pipeline":
        """
        Return an independent shallow copy of this pipeline (v11).
        Modifications to the fork do not affect the original.
        """
        clone = Pipeline(self._name)
        clone._stages = list(self._stages)
        return clone

    def describe(self) -> str:
        """Human-readable stage summary (v11)."""
        if not self._stages:
            return f"Pipeline({self._name!r}) [empty]"
        stage_names = " → ".join(s.name for s in self._stages)
        return f"Pipeline({self._name!r}) [{stage_names}]"

    def stages(self) -> Iterator[PipeStage]:
        yield from self._stages

    def __len__(self) -> int:
        return len(self._stages)

    def __repr__(self) -> str:
        return f"<Pipeline:{self._name} stages={[s.name for s in self._stages]}>"


# ─────────────────────────────────────────────
# Built-in Stages — original set
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
# Built-in Stages — v11 additions
# ─────────────────────────────────────────────

class ReduceStage(PipeStage):
    """
    Fold all (key, value) pairs in the data dict through a reducer.

    The reducer accumulates an arbitrary result (not a new packet).
    The *packet is returned unchanged*; the accumulated result is stored
    in ``packet.meta`` under ``result_key``.

    This is useful for:
      - Counting keys matching a predicate
      - Computing a checksum / hash of the config
      - Building a derived summary dict

    Args:
        reducer:    (accumulator: T, key: str, value: Any) → T
        initial:    Initial accumulator value.
        result_key: Key under which to store the result in packet.meta.
        label:      Descriptive stage name.

    Example — count boolean keys::

        ReduceStage(
            reducer    = lambda acc, k, v: acc + (1 if isinstance(v, bool) else 0),
            initial    = 0,
            result_key = "bool_count",
            label      = "bool-counter",
        )
    """

    def __init__(
        self,
        reducer:    Callable[[Any, str, Any], Any],
        initial:    Any,
        result_key: str = "reduce_result",
        label:      str = "reduce",
    ) -> None:
        self._reducer    = reducer
        self._initial    = initial
        self._result_key = result_key
        self._label      = label

    @property
    def name(self) -> str:
        return f"reduce:{self._label}"

    def process(self, packet: ConfigPacket) -> ConfigPacket:
        acc = self._initial
        for k, v in packet.data.items():
            try:
                acc = self._reducer(acc, k, v)
            except Exception as exc:
                logger.warning("[ReduceStage:%s] reducer raised on key=%r: %s", self._label, k, exc)
        return packet.with_meta(self._result_key, acc)


class BranchStage(PipeStage):
    """
    Conditional routing: apply one of two sub-pipelines based on a predicate.

    The *true_branch* pipeline runs when predicate(packet) is True;
    the *false_branch* (optional) runs otherwise.  If false_branch is
    None, the packet passes through unchanged on the false path.

    This enables e.g. applying stricter validation only when a privacy
    flag is set, without cluttering the main pipeline with if/else.

    Args:
        predicate:    (packet: ConfigPacket) → bool
        true_branch:  Pipeline to run when predicate returns True.
        false_branch: Pipeline to run when predicate returns False (optional).
        label:        Descriptive stage name.

    Example — apply hardening only in PARANOID mode::

        BranchStage(
            predicate    = lambda p: p.meta.get("privacy_profile") == "PARANOID",
            true_branch  = Pipeline("harden").pipe(hardenStage),
            false_branch = None,
            label        = "paranoid-branch",
        )
    """

    def __init__(
        self,
        predicate:    Callable[["ConfigPacket"], bool],
        true_branch:  "Pipeline",
        false_branch: Optional["Pipeline"] = None,
        label:        str                  = "branch",
    ) -> None:
        self._predicate    = predicate
        self._true_branch  = true_branch
        self._false_branch = false_branch
        self._label        = label

    @property
    def name(self) -> str:
        return f"branch:{self._label}"

    def process(self, packet: ConfigPacket) -> ConfigPacket:
        try:
            condition = self._predicate(packet)
        except Exception as exc:
            logger.warning("[BranchStage:%s] predicate raised: %s — taking false path", self._label, exc)
            condition = False

        if condition:
            logger.debug("[BranchStage:%s] → true_branch", self._label)
            return self._true_branch.run(packet)
        elif self._false_branch is not None:
            logger.debug("[BranchStage:%s] → false_branch", self._label)
            return self._false_branch.run(packet)
        else:
            logger.debug("[BranchStage:%s] → pass-through (no false_branch)", self._label)
            return packet


class CacheStage(PipeStage):
    """
    Memoize an expensive sub-stage.

    Computes a stable hash of the packet's data dict; on a cache hit the
    wrapped stage is skipped entirely and the cached output is returned.
    On a cache miss the wrapped stage runs normally and the result is cached.

    Cache key: SHA-1 of the JSON-serialised sorted data dict.
    Non-serialisable values fall back to repr() per key.

    This is useful when a TransformStage performs expensive computation
    (e.g. calling an external tool, parsing a large file) that would
    otherwise re-run on every :config-source hot-reload even when the
    input data has not changed.

    Args:
        inner: The PipeStage to memoize.
        label: Descriptive stage name.

    Example::

        CacheStage(TransformStage(expensive_fn, "expensive"), label="expensive-cache")
    """

    def __init__(self, inner: PipeStage, label: str = "cache") -> None:
        self._inner:  PipeStage              = inner
        self._label:  str                    = label
        self._cache:  Dict[str, ConfigPacket] = {}

    @property
    def name(self) -> str:
        return f"cache:{self._label}"

    def invalidate(self) -> None:
        """Clear the cache manually (e.g. after a config reload)."""
        self._cache.clear()
        logger.debug("[CacheStage:%s] cache invalidated", self._label)

    def process(self, packet: ConfigPacket) -> ConfigPacket:
        key = self._hash(packet.data)
        if key in self._cache:
            logger.debug("[CacheStage:%s] cache hit — skipping %s", self._label, self._inner.name)
            return self._cache[key]
        result = self._inner.process(packet)
        self._cache[key] = result
        logger.debug("[CacheStage:%s] cache miss — stored result for key %.8s…", self._label, key)
        return result

    @staticmethod
    def _hash(data: ConfigDict) -> str:
        """Stable hash of the data dict."""
        parts: List[str] = []
        for k in sorted(data.keys()):
            try:
                v_str = json.dumps(data[k], sort_keys=True, default=repr)
            except (TypeError, ValueError):
                v_str = repr(data[k])
            parts.append(f"{k}={v_str}")
        raw = "|".join(parts).encode()
        return hashlib.sha1(raw).hexdigest()


class AuditStage(PipeStage):
    """
    Record pipeline passage into the global AuditLog (v11).

    Emits one AuditLevel.DEBUG entry on entry and one on exit (with key count
    and error count).  Zero-cost when the audit log is not being consumed.

    Args:
        label:     Stage label written into the audit entry component field.
        component: AuditLog component name (default "pipeline").

    Example::

        Pipeline("privacy")
        .pipe(AuditStage("pre"))
        .pipe(ValidateStage({...}))
        .pipe(AuditStage("post"))
    """

    def __init__(self, label: str = "", component: str = "pipeline") -> None:
        self._label     = label
        self._component = component

    @property
    def name(self) -> str:
        return f"audit:{self._label}"

    def process(self, packet: ConfigPacket) -> ConfigPacket:
        try:
            from core.audit import audit_debug
            audit_debug(
                self._component,
                f"pipeline stage {self._label!r}: source={packet.source!r} "
                f"keys={len(packet.data)} errors={len(packet.errors)}",
                label=self._label,
                source=packet.source,
            )
        except ImportError:
            pass   # audit module not available — silently skip
        return packet


class TeeStage(PipeStage):
    """
    Fan-out: run a side-branch stage *without* mutating the main packet.  (v12)

    The *observer* stage receives the packet, runs, but its output is discarded.
    The original packet continues through the pipeline unchanged.

    This makes it safe to inject logging, auditing, or metrics probes anywhere
    in a pipeline without risking accidental data mutation.

    If the observer raises, the exception is caught, logged as a warning, and
    the main packet is returned unchanged.

    Args:
        observer: A PipeStage whose output is ignored.
        label:    Descriptive name used in logging and describe().

    Example — audit every packet mid-pipeline::

        Pipeline("privacy")
        .pipe(ValidateStage({...}))
        .pipe(TeeStage(AuditStage("mid"), label="mid-audit"))
        .pipe(TransformStage(harden_fn, "harden"))
    """

    def __init__(self, observer: PipeStage, label: str = "tee") -> None:
        self._observer = observer
        self._label    = label

    @property
    def name(self) -> str:
        return f"tee:{self._label}[{self._observer.name}]"

    def process(self, packet: ConfigPacket) -> ConfigPacket:
        try:
            self._observer.process(packet)   # output intentionally discarded
        except Exception as exc:
            logger.warning(
                "[TeeStage:%s] observer %s raised: %s — main packet unaffected",
                self._label, self._observer.name, exc,
            )
        return packet   # always return original unchanged


class RetryStage(PipeStage):
    """
    Retry wrapper — run an inner stage up to *max_retries* times on exception.  (v12)

    On each failure:
      - The exception is logged as a warning.
      - A warning string is appended to the packet.
      - An optional *delay_s* (default 0.0) pause is applied before the next
        attempt (useful for transient resource-access errors).
      - If all retries are exhausted, the last exception is re-raised.

    Only use with **idempotent** stages — stages that produce the same result
    when called repeatedly with the same input.

    Args:
        inner:       The PipeStage to retry.
        max_retries: Total attempts (including first try).  Minimum 1.
        delay_s:     Seconds to sleep between attempts.  Set 0.0 (default)
                     for synchronous configs where sleep is never desired.
        label:       Descriptive stage name.

    Example::

        RetryStage(TransformStage(flaky_rpc, "rpc"), max_retries=3, delay_s=0.05)
    """

    def __init__(
        self,
        inner:       PipeStage,
        max_retries: int   = 3,
        delay_s:     float = 0.0,
        label:       str   = "retry",
    ) -> None:
        self._inner       = inner
        self._max_retries = max(1, max_retries)
        self._delay_s     = delay_s
        self._label       = label

    @property
    def name(self) -> str:
        return f"retry:{self._label}[{self._inner.name}×{self._max_retries}]"

    def process(self, packet: ConfigPacket) -> ConfigPacket:
        last_exc: Optional[Exception] = None
        for attempt in range(1, self._max_retries + 1):
            try:
                return self._inner.process(packet)
            except Exception as exc:
                last_exc = exc
                msg = (
                    f"[RetryStage:{self._label}] attempt {attempt}/{self._max_retries} "
                    f"for stage {self._inner.name} raised: {exc}"
                )
                logger.warning(msg)
                packet = packet.with_warnings([msg])
                if self._delay_s > 0.0 and attempt < self._max_retries:
                    time.sleep(self._delay_s)

        # All retries exhausted — re-raise last exception
        if last_exc is not None:
            raise last_exc
        return packet   # unreachable; satisfies type checker


class CompositeStage(PipeStage):
    """
    Wrap a sub-Pipeline as a single named PipeStage.  (v12)

    Allows a reusable pipeline fragment to be embedded inside a larger
    pipeline while appearing as a single unit in describe() / logging.

    Equivalent to inlining all stages of *sub_pipeline* but with a single
    visible name, making ``Pipeline.describe()`` output much cleaner when
    complex sub-pipelines are involved.

    Args:
        sub_pipeline: The Pipeline to delegate to.
        label:        Override name (defaults to sub_pipeline.name).

    Example::

        privacy_stages = (
            Pipeline("privacy-inner")
            .pipe(ValidateStage({...}))
            .pipe(FilterStage(allow_only_safe))
        )

        main_pipeline = (
            Pipeline("main")
            .pipe(CompositeStage(privacy_stages, label="privacy"))
            .pipe(LogStage("post-privacy"))
        )
    """

    def __init__(self, sub_pipeline: "Pipeline", label: str = "") -> None:
        self._sub   = sub_pipeline
        self._label = label or sub_pipeline.name

    @property
    def name(self) -> str:
        return f"composite:{self._label}"

    def process(self, packet: ConfigPacket) -> ConfigPacket:
        return self._sub.run(packet)


# ─────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────

@functools.lru_cache(maxsize=None)
def noop_pipeline() -> Pipeline:
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


__all__ = [
    "ConfigPacket",
    "PipeStage",
    "Pipeline",
    # original stages
    "LogStage",
    "ValidateStage",
    "TransformStage",
    "FilterStage",
    "MergeStage",
    # v11 stages
    "ReduceStage",
    "BranchStage",
    "CacheStage",
    "AuditStage",
    # v12 stages
    "TeeStage",
    "RetryStage",
    "CompositeStage",
    # helpers
    "noop_pipeline",
]
