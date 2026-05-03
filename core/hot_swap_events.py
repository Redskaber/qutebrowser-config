"""
core/hot_swap_events.py
=======================
Events for the Hot-Swap Engine  (v13)

Kept in a separate file to avoid circular imports between
``hot_swap.py`` (which imports ``core.layer``) and ``protocol.py``
(which is imported by ``core.layer`` transitively).

Imports ``Event`` from ``core.protocol`` which is always available.
"""

from __future__ import annotations

from dataclasses import dataclass

from core.protocol import Event


@dataclass(frozen=True)
class LayerSwappedEvent(Event):
    """
    Emitted after a successful hot-swap operation.

    Fields
    ------
    operation  : "swap" | "remove" | "insert"
    layer_name : name of the affected layer
    changes    : number of settings keys changed in the diff
    errors     : number of apply errors (0 = clean swap)
    """
    operation:  str = ""
    layer_name: str = ""
    changes:    int = 0
    errors:     int = 0
