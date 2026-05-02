"""
core/strategy.py
================
Strategy + Policy System

Architecture:
  PolicyRegistry → [Policy] → PolicyResolver → decision
  StrategyRegistry → Strategy → execution

Principles:
  - Strategy Pattern: algorithms are interchangeable
  - Policy Pattern: rules that govern behavior selection
  - Open/Closed: new strategies/policies via registration
  - Data-Driven: policy rules expressed as data, not code

Patterns: Strategy, Policy, Registry, Chain of Responsibility

Strict-mode notes (Pyright):
  - Removed unused ``field`` and ``Callable`` imports.
  - ``recursive_merge`` uses ``Dict[str, Any]`` instead of bare ``dict``.
  - ``all_decisions`` return type is fully annotated.
  - ``PolicyChain.__init__`` has an explicit ``-> None`` return type.
"""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass
from enum import Enum, auto
from typing import Any, Dict, Generic, List, Optional, Tuple, TypeVar, cast

from core.types import ConfigDict

logger = logging.getLogger("qute.strategy")

T = TypeVar("T")

# ─────────────────────────────────────────────
# Strategy Abstraction
# ─────────────────────────────────────────────
class Strategy(ABC, Generic[T]):
    """Base strategy interface."""
    name: str = "unnamed"

    @abstractmethod
    def apply(self, context: ConfigDict) -> T:
        ...

    def can_handle(self, context: ConfigDict) -> bool:
        """Guard: returns True if this strategy is applicable."""
        return True

    def __repr__(self) -> str:
        return f"<Strategy:{self.name}>"


class StrategyRegistry(Generic[T]):
    """
    Registry of named strategies.
    Supports fallback and priority-based selection.
    """

    def __init__(self, default: Optional[Strategy[T]] = None) -> None:
        self._strategies: Dict[str, Strategy[T]] = {}
        self._default = default

    def register(self, strategy: Strategy[T]) -> "StrategyRegistry[T]":
        self._strategies[strategy.name] = strategy
        logger.debug("[StrategyRegistry] registered: %s", strategy.name)
        return self

    def get(self, name: str) -> Strategy[T]:
        s = self._strategies.get(name)
        if s is None:
            if self._default:
                logger.warning("[StrategyRegistry] unknown strategy %r, using default", name)
                return self._default
            raise KeyError(f"No strategy named: {name}")
        return s

    def apply(self, name: str, context: ConfigDict) -> T:
        return self.get(name).apply(context)

    def auto_select(self, context: ConfigDict) -> Optional[Strategy[T]]:
        """Return first strategy that can_handle the context."""
        for s in self._strategies.values():
            if s.can_handle(context):
                return s
        return self._default

    def names(self) -> List[str]:
        return list(self._strategies.keys())


# ─────────────────────────────────────────────
# Policy System
# ─────────────────────────────────────────────
class PolicyAction(Enum):
    ALLOW  = auto()
    DENY   = auto()
    MODIFY = auto()
    WARN   = auto()
    BLOCK  = auto()


@dataclass
class PolicyDecision:
    action: PolicyAction
    reason: str = ""
    modified_value: Any = None


class Policy(ABC):
    """
    A policy evaluates a (key, value) pair and returns a decision.
    Policies are composable via PolicyChain.
    """
    name: str = "unnamed_policy"
    priority: int = 50

    @abstractmethod
    def evaluate(self, key: str, value: Any, context: ConfigDict) -> Optional[PolicyDecision]:
        """
        Return a PolicyDecision or None (= this policy doesn't apply).
        """
        ...

    def __repr__(self) -> str:
        return f"<Policy:{self.name}>"


class PolicyChain:
    """
    Chain of Responsibility for policies.
    Stops at first non-None decision or returns ALLOW by default.
    """

    def __init__(self) -> None:
        self._policies: List[Policy] = []

    def add(self, policy: Policy) -> "PolicyChain":
        self._policies.append(policy)
        self._policies.sort(key=lambda p: p.priority)
        return self

    def evaluate(self, key: str, value: Any, context: ConfigDict) -> PolicyDecision:
        for policy in self._policies:
            decision = policy.evaluate(key, value, context)
            if decision is not None:
                logger.debug(
                    "[PolicyChain] %s → %s (%s)",
                    policy.name, decision.action.name, decision.reason
                )
                return decision
        return PolicyDecision(action=PolicyAction.ALLOW, reason="no policy matched")

    def all_decisions(
        self,
        key: str,
        value: Any,
        context: ConfigDict,
    ) -> List[Tuple[Policy, PolicyDecision]]:
        """Non-short-circuit: collect all applicable decisions."""
        results: List[Tuple[Policy, PolicyDecision]] = []
        for policy in self._policies:
            d = policy.evaluate(key, value, context)
            if d is not None:
                results.append((policy, d))
        return results


# ─────────────────────────────────────────────
# Concrete Policies
# ─────────────────────────────────────────────
class ReadOnlyPolicy(Policy):
    """Prevent certain keys from being overridden."""
    name = "readonly"
    priority = 10

    def __init__(self, protected_keys: List[str]) -> None:
        self._protected = set(protected_keys)

    def evaluate(self, key: str, value: Any, context: ConfigDict) -> Optional[PolicyDecision]:
        if key in self._protected:
            return PolicyDecision(
                action=PolicyAction.DENY,
                reason=f"key '{key}' is protected"
            )
        return None


class TypeEnforcePolicy(Policy):
    """Enforce value types for specific keys."""
    name = "type_enforce"
    priority = 20

    def __init__(self, type_map: Dict[str, type]) -> None:
        self._types = type_map

    def evaluate(self, key: str, value: Any, context: ConfigDict) -> Optional[PolicyDecision]:
        expected = self._types.get(key)
        if expected and not isinstance(value, expected):
            return PolicyDecision(
                action=PolicyAction.WARN,
                reason=f"key '{key}' expected {expected.__name__}, got {type(value).__name__}"
            )
        return None


class RangePolicy(Policy):
    """Enforce numeric ranges."""
    name = "range"
    priority = 25

    def __init__(self, ranges: Dict[str, Tuple[Any, Any]]) -> None:
        self._ranges = ranges

    def evaluate(self, key: str, value: Any, context: ConfigDict) -> Optional[PolicyDecision]:
        if key in self._ranges:
            lo, hi = self._ranges[key]
            if not (lo <= value <= hi):
                clamped = max(lo, min(hi, value))
                return PolicyDecision(
                    action=PolicyAction.MODIFY,
                    reason=f"key '{key}' value {value} clamped to [{lo},{hi}]",
                    modified_value=clamped,
                )
        return None


class AllowlistPolicy(Policy):
    """Only allow keys from a known set."""
    name = "allowlist"
    priority = 5

    def __init__(self, allowed_keys: List[str], strict: bool = False) -> None:
        self._allowed = set(allowed_keys)
        self._strict = strict

    def evaluate(self, key: str, value: Any, context: ConfigDict) -> Optional[PolicyDecision]:
        if self._allowed and key not in self._allowed:
            action = PolicyAction.DENY if self._strict else PolicyAction.WARN
            return PolicyDecision(action=action, reason=f"key '{key}' not in allowlist")
        return None


# ─────────────────────────────────────────────
# Concrete Strategies
# ─────────────────────────────────────────────
class MergeStrategy(Strategy[ConfigDict]):
    """Different merge algorithms as strategies."""

    class LastWins(Strategy[ConfigDict]):
        name = "last_wins"
        def apply(self, context: ConfigDict) -> ConfigDict:
            base:    ConfigDict = context.get("base", {})    # type: ignore[assignment]
            overlay: ConfigDict = context.get("overlay", {}) # type: ignore[assignment]
            return {**base, **overlay}

    class FirstWins(Strategy[ConfigDict]):
        name = "first_wins"
        def apply(self, context: ConfigDict) -> ConfigDict:
            base:    ConfigDict = context.get("base", {})    # type: ignore[assignment]
            overlay: ConfigDict = context.get("overlay", {}) # type: ignore[assignment]
            return {**overlay, **base}

    class DeepMerge(Strategy[ConfigDict]):
        name = "deep_merge"
        def apply(self, context: ConfigDict) -> ConfigDict:
            base:    ConfigDict = context.get("base", {})    # type: ignore[assignment]
            overlay: ConfigDict = context.get("overlay", {}) # type: ignore[assignment]
            return recursive_merge(base, overlay)

    # MergeStrategy itself is abstract; its inner classes are the concrete ones.
    def apply(self, context: ConfigDict) -> ConfigDict:
        raise NotImplementedError("Use MergeStrategy.LastWins, .FirstWins, or .DeepMerge")


def recursive_merge(base: Dict[str, Any], overlay: Dict[str, Any]) -> Dict[str, Any]:
    """Recursively merge *overlay* into *base*.  Overlay wins on conflicts."""
    result: Dict[str, Any] = base.copy()
    for k, v in overlay.items():
        existing = result.get(k)
        if isinstance(existing, dict) and isinstance(v, dict):
            existing = cast(Dict[str, Any], existing)
            v = cast(Dict[str, Any], v)
            result[k] = recursive_merge(existing, v)
        else:
            result[k] = v
    return result


