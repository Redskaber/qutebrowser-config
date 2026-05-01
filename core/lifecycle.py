"""
core/lifecycle.py
=================
Lifecycle Manager (extracted from state.py for SRP)
"""

from __future__ import annotations

import logging
from enum import Enum
from typing import Any, Callable, Dict, List, Tuple

logger = logging.getLogger("qute.lifecycle")


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
    Components register handlers; manager orchestrates execution order.
    """

    def __init__(self):
        self._hooks: Dict[LifecycleHook, List[Tuple[int, Callable]]] = {
            hook: [] for hook in LifecycleHook
        }

    def register(self, hook: LifecycleHook, handler: Callable, priority: int = 50) -> None:
        self._hooks[hook].append((priority, handler))
        self._hooks[hook].sort(key=lambda x: x[0])
        logger.debug("[Lifecycle] registered %s@%d: %s", hook.value, priority, handler.__name__)

    def run(self, hook: LifecycleHook, *args, **kwargs) -> List[Any]:
        results = []
        for priority, handler in self._hooks[hook]:
            try:
                result = handler(*args, **kwargs)
                results.append(result)
            except Exception as e:
                logger.error("[Lifecycle] %s/%s → error: %s", hook.value, handler.__name__, e)
        return results

    def decorator(self, hook: LifecycleHook, priority: int = 50):
        def wrapper(fn: Callable) -> Callable:
            self.register(hook, fn, priority)
            return fn
        return wrapper
