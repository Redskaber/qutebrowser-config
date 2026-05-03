"""
core/validator.py
=================
Declarative Config Validator  (v13)

Separates **structural validation** (schema correctness) from
**semantic health checks** (``core/health.py``).

Design distinction
------------------
=============  ===========================================================
Module         Purpose
=============  ===========================================================
health.py      Semantic / operational checks: "Is your proxy URL well-formed?"
               "Is your spellcheck language a valid BCP-47 tag?"
               Runs AFTER the full config is built.
validator.py   Structural / schema validation: "Is this key a known qutebrowser
               setting?"  "Is the value the correct type?"
               Runs PER-LAYER at build time (inside ``LayerProtocol.validate``).
=============  ===========================================================

Architecture
------------
::

    Schema  ← Dict[key, FieldSpec]
        ↓
    ConfigValidator.validate(settings) → ValidationResult
        ↑
    FieldSpec:
        type_     : expected Python type(s)
        required  : must be present
        choices   : allowed value set (optional)
        min_/max_ : numeric range (optional)
        pattern   : regex (optional)
        custom    : Callable[[value] → str|None]  (optional, returns error or None)

Pattern: Schema (data-driven), Strategy (custom validators), Value Object (FieldSpec).

Strict-mode (Pyright)
---------------------
  All attrs typed; FieldSpec is a frozen dataclass.
  ValidationResult.ok is a property (not a stored bool) for correctness.

v13 (new module):
  - FieldSpec frozen dataclass
  - SchemaType = Dict[str, FieldSpec]
  - ValidationResult (errors, warnings)
  - ConfigValidator
  - COMMON_SCHEMA: partial schema for the most frequently configured keys
  - SchemaRegistry: named schema store
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Set, Tuple, Type, Union

from core.types import ConfigDict

logger = logging.getLogger("qute.validator")

# Validator function: receives value, returns error string or None
ValidatorFn = Callable[[Any], Optional[str]]

# Type alias
SchemaType = Dict[str, "FieldSpec"]


# ─────────────────────────────────────────────
# FieldSpec
# ─────────────────────────────────────────────

@dataclass(frozen=True)
class FieldSpec:
    """
    Declarative specification for one config key.

    All constraints are optional; specify only what you want to enforce.

    Parameters
    ----------
    type_    : expected Python type or tuple of types
    required : if True, key must be present
    choices  : value must be in this set (strings/ints)
    min_     : minimum numeric value (float comparison)
    max_     : maximum numeric value
    pattern  : regex the string value must match (re.search)
    custom   : Callable[[value] → Optional[str]]  — None = pass, str = error
    description : human-readable description for docs
    """
    type_:       Optional[Union[Type[Any], Tuple[Type[Any], ...]]] = None
    required:    bool                                              = False
    choices:     Optional[Set[Any]]                                = None
    min_:        Optional[float]                                   = None
    max_:        Optional[float]                                   = None
    pattern:     Optional[str]                                     = None
    custom:      Optional[ValidatorFn]                             = None
    description: str                                               = ""


# ─────────────────────────────────────────────
# Validation Result
# ─────────────────────────────────────────────

@dataclass
class ValidationResult:
    """
    Structured output of ConfigValidator.validate().

    Attributes
    ----------
    errors   : fatal validation failures
    warnings : non-fatal issues
    """
    errors:   List[str] = field(default_factory=list[str])
    warnings: List[str] = field(default_factory=list[str])

    @property
    def ok(self) -> bool:
        return len(self.errors) == 0

    def merge(self, other: "ValidationResult") -> "ValidationResult":
        """Merge two results into a new one."""
        return ValidationResult(
            errors=self.errors + other.errors,
            warnings=self.warnings + other.warnings,
        )

    def __str__(self) -> str:
        lines: List[str] = []
        for e in self.errors:
            lines.append(f"  ERROR:   {e}")
        for w in self.warnings:
            lines.append(f"  WARNING: {w}")
        if not lines:
            return "ValidationResult: OK"
        return "ValidationResult:\n" + "\n".join(lines)


# ─────────────────────────────────────────────
# ConfigValidator
# ─────────────────────────────────────────────

class ConfigValidator:
    """
    Validate a settings dict against a ``SchemaType``.

    Usage::

        schema = {
            "zoom.default": FieldSpec(type_=str, pattern=r"^\\d+%$"),
            "content.javascript.enabled": FieldSpec(type_=bool, required=True),
        }
        result = ConfigValidator(schema).validate(settings)
        if not result.ok:
            for err in result.errors:
                print(err)

    Unknown keys are ignored by default (set ``strict=True`` to warn on them).
    """

    def __init__(self, schema: SchemaType, strict: bool = False) -> None:
        self._schema = schema
        self._strict = strict

    def validate(self, settings: ConfigDict) -> ValidationResult:
        """
        Validate *settings* against the schema.

        Parameters
        ----------
        settings : the config dict to validate (e.g. from a layer's _settings())

        Returns
        -------
        ValidationResult with errors and warnings lists.
        """
        result = ValidationResult()

        # Check required fields
        for key, spec in self._schema.items():
            if spec.required and key not in settings:
                result.errors.append(f"required key missing: {key!r}")

        # Validate present fields
        for key, value in settings.items():
            spec = self._schema.get(key)
            if spec is None:
                if self._strict:
                    result.warnings.append(f"unknown key: {key!r}")
                continue

            errs = self._check(key, value, spec)
            result.errors.extend([e for e in errs if not e.startswith("WARN:")])
            result.warnings.extend([e[5:].strip() for e in errs if e.startswith("WARN:")])

        return result

    def _check(self, key: str, value: Any, spec: FieldSpec) -> List[str]:
        issues: List[str] = []

        # Type check
        if spec.type_ is not None:
            if not isinstance(value, spec.type_):
                expected = (
                    spec.type_.__name__
                    if isinstance(spec.type_, type)
                    else " | ".join(t.__name__ for t in spec.type_)  # type: ignore[union-attr]
                )
                issues.append(
                    f"{key!r}: expected {expected}, got {type(value).__name__}"
                )
                return issues  # further checks meaningless if type is wrong

        # Choices
        if spec.choices is not None and value not in spec.choices:
            issues.append(
                f"{key!r}: value {value!r} not in allowed set {spec.choices!r}"
            )

        # Numeric range
        if isinstance(value, (int, float)):
            if spec.min_ is not None and value < spec.min_:
                issues.append(f"{key!r}: value {value} below minimum {spec.min_}")
            if spec.max_ is not None and value > spec.max_:
                issues.append(f"{key!r}: value {value} above maximum {spec.max_}")

        # Pattern
        if spec.pattern is not None and isinstance(value, str):
            if not re.search(spec.pattern, value):
                issues.append(
                    f"{key!r}: value {value!r} does not match pattern {spec.pattern!r}"
                )

        # Custom
        if spec.custom is not None:
            try:
                error = spec.custom(value)
                if error:
                    issues.append(f"{key!r}: {error}")
            except Exception as exc:
                logger.warning("[Validator] custom check for %r raised: %s", key, exc)

        return issues


# ─────────────────────────────────────────────
# Common Schema (partial reference)
# ─────────────────────────────────────────────

#: Partial schema covering the most commonly validated qutebrowser keys.
#: Import and extend this in your layer's validator; don't modify it.
COMMON_SCHEMA: SchemaType = {
    # ── Content ───────────────────────────────────────────────────────
    "content.javascript.enabled": FieldSpec(type_=bool),
    "content.blocking.enabled":   FieldSpec(type_=bool),
    "content.autoplay":           FieldSpec(type_=bool),
    "content.cookies.accept":     FieldSpec(
        type_=str,
        choices={"all", "no-3rdparty", "no-unknown-3rdparty", "never"},
    ),
    "content.webrtc_ip_handling_policy": FieldSpec(
        type_=str,
        choices={
            "all-interfaces",
            "default-public-and-private-interfaces",
            "default-public-interface-only",
            "disable-non-proxied-udp",
        },
    ),
    "content.proxy": FieldSpec(
        type_=str,
        custom=lambda v: (
            None if v in ("system", "none")
            else (None if "://" in v else "proxy URL should contain '://'")
        ),
    ),

    # ── Zoom ───────────────────────────────────────────────────────────
    "zoom.default": FieldSpec(
        type_=str,
        pattern=r"^\d+%$",
        description="e.g. '100%'",
    ),

    # ── Fonts ──────────────────────────────────────────────────────────
    "fonts.default_family": FieldSpec(type_=str),
    "fonts.default_size":   FieldSpec(
        type_=str,
        pattern=r"^\d+(pt|px)$",
        description="e.g. '10pt'",
    ),
    "fonts.web.size.default": FieldSpec(type_=int, min_=1, max_=200),
    "fonts.web.size.minimum": FieldSpec(type_=int, min_=0, max_=100),

    # ── Tabs ───────────────────────────────────────────────────────────
    "tabs.position": FieldSpec(
        type_=str,
        choices={"top", "bottom", "left", "right"},
    ),
    "tabs.show": FieldSpec(
        type_=str,
        choices={"always", "never", "multiple", "switching"},
    ),

    # ── Downloads ──────────────────────────────────────────────────────
    "downloads.location.prompt": FieldSpec(type_=bool),

    # ── Messages ───────────────────────────────────────────────────────
    "messages.timeout": FieldSpec(type_=int, min_=0),

    # ── Spell check ────────────────────────────────────────────────────
    "spellcheck.languages": FieldSpec(type_=list),

    # ── Editor ─────────────────────────────────────────────────────────
    "editor.command": FieldSpec(
        type_=list,
        custom=lambda v: (
            None if (isinstance(v, list) and "{}" in " ".join(str(x) for x in v)) # type: ignore[new]
            else "editor.command list must contain '{}' placeholder"
        ),
    ),
}


# ─────────────────────────────────────────────
# Schema Registry
# ─────────────────────────────────────────────

class SchemaRegistry:
    """
    Named store of SchemaType dicts.

    Allows layers/modules to register their schemas and the orchestrator
    to run all registered validators in one pass.
    """

    def __init__(self) -> None:
        self._schemas: Dict[str, SchemaType] = {}

    def register(self, name: str, schema: SchemaType) -> "SchemaRegistry":
        """Register a named schema.  Returns self."""
        self._schemas[name] = dict(schema)
        return self

    def extend(self, name: str, extra: SchemaType) -> "SchemaRegistry":
        """Merge *extra* into the named schema (or create it)."""
        base = self._schemas.get(name, {})
        self._schemas[name] = {**base, **extra}
        return self

    def get(self, name: str) -> Optional[SchemaType]:
        return self._schemas.get(name)

    def validate_all(
        self,
        settings: ConfigDict,
        strict: bool = False,
    ) -> ValidationResult:
        """
        Run ALL registered schemas against *settings* and merge results.
        """
        combined = ValidationResult()
        for name, schema in self._schemas.items():
            result = ConfigValidator(schema, strict=strict).validate(settings)
            logger.debug(
                "[SchemaRegistry] schema=%s  errors=%d  warnings=%d",
                name, len(result.errors), len(result.warnings),
            )
            combined = combined.merge(result)
        return combined

    def names(self) -> List[str]:
        return list(self._schemas.keys())


# ─────────────────────────────────────────────
# Module-level singleton
# ─────────────────────────────────────────────

_default_registry: Optional[SchemaRegistry] = None


def get_schema_registry() -> SchemaRegistry:
    """Return the module-level SchemaRegistry singleton."""
    global _default_registry
    if _default_registry is None:
        _default_registry = SchemaRegistry()
        _default_registry.register("common", COMMON_SCHEMA)
    return _default_registry


def reset_schema_registry() -> SchemaRegistry:
    """Replace the singleton with a fresh registry (for tests)."""
    global _default_registry
    _default_registry = SchemaRegistry()
    return _default_registry
