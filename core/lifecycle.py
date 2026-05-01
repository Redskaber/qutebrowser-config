"""
core/lifecycle.py
=================
Lifecycle Manager

Manages ordered hook execution across lifecycle phases.
Components register callable handlers; the manager runs them in
priority order and swallows exceptions so one bad hook never
prevents the rest from executing.

Principles:
  - Single Responsibility: only manages hook registration and dispatch
  - Open/Closed: new hooks via LifecycleHook enum; no code changes needed
  - Fail-safe: handler exceptions are logged, not re-raised

Strict-mode notes (Pyright):
  - ``Handler = Callable[..., Any]`` gives Pyright a concrete alias to
    check against, replacing bare ``Callable`` (which triggers
    reportMissingTypeArgument).
  - ``run()`` uses ``*args: Any, **kwargs: Any`` instead of bare ``*args``.
  - ``decorator()`` return type is fully spelled out.
"""

from __future__ import annotations

import logging
from enum import Enum
from typing import Any, Callable, Dict, List, Tuple

logger = logging.getLogger("qute.lifecycle")

# Concrete type alias used throughout this module.
# Callable[..., Any] means "any callable, any signature, any return".
Handler = Callable[..., Any]


class LifecycleHook(Enum):
    PRE_INIT    = "pre_init"
    POST_INIT   = "post_init"
    PRE_APPLY   = "pre_apply"
    POST_APPLY  = "post_apply"
    PRE_RELOAD  = "pre_reload"
    POST_RELOAD = "post_reload"
    ON_ERROR    = "on_error"
    ON_TEARDOWN = "on_teardown"


class LifecycleManager:
    """
    Manages ordered hook execution across lifecycle phases.

    Handlers are registered with an integer ``priority`` (lower = earlier).
    Ties are broken by insertion order.

    Usage::

        mgr = LifecycleManager()
        mgr.register(LifecycleHook.POST_APPLY, my_fn, priority=50)

        @mgr.decorator(LifecycleHook.PRE_APPLY, priority=10)
        def before_apply() -> None:
            ...
    """

    def __init__(self) -> None:
        self._hooks: Dict[LifecycleHook, List[Tuple[int, Handler]]] = {
            hook: [] for hook in LifecycleHook
        }

    def register(
        self,
        hook: LifecycleHook,
        handler: Handler,
        priority: int = 50,
    ) -> None:
        """Register *handler* for *hook* at the given *priority*."""
        self._hooks[hook].append((priority, handler))
        self._hooks[hook].sort(key=lambda item: item[0])
        logger.debug(
            "[Lifecycle] registered %s@%d: %s",
            hook.value,
            priority,
            getattr(handler, "__name__", repr(handler)),
        )

    def run(self, hook: LifecycleHook, *args: Any, **kwargs: Any) -> List[Any]:
        """
        Run all handlers for *hook* in priority order.

        *args* and *kwargs* are forwarded to each handler unchanged.
        Returns a list of return values (one per handler that did not raise).
        """
        results: List[Any] = []
        for _priority, handler in self._hooks[hook]:
            try:
                result = handler(*args, **kwargs)
                results.append(result)
            except Exception as exc:
                logger.error(
                    "[Lifecycle] %s/%s → error: %s",
                    hook.value,
                    getattr(handler, "__name__", repr(handler)),
                    exc,
                )
        return results

    def decorator(
        self,
        hook: LifecycleHook,
        priority: int = 50,
    ) -> Callable[[Handler], Handler]:
        """
        Decorator that registers a function as a lifecycle handler.

        The decorated function is returned unchanged so it remains callable
        directly (and Pyright no longer reports it as unused).

        Usage::

            @mgr.decorator(LifecycleHook.POST_APPLY, priority=100)
            def _on_done() -> None:
                logger.info("done")
        """
        def wrapper(fn: Handler) -> Handler:
            self.register(hook, fn, priority)
            return fn
        return wrapper


