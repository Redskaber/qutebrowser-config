"""
core/types.py
=============
Zero-dependency primitive type definitions.

This module sits at the very bottom of the dependency graph.
It MUST NOT import from any other project module.

Rationale
---------
Solution: lift the two shared primitive types here.  Both ``core.layer``
and ``keybindings.catalog`` (and any other module that needs them) import
from this single, zero-dependency module.

Dependency graph (no cycles):

    core/types.py          (this file — no project imports)
         ↑          ↑
  core/layer.py   keybindings/catalog.py ...
         ↑
  core/__init__.py   …

"""

from __future__ import annotations

from typing import Any, Dict, Tuple

# ---------------------------------------------------------------------------
# ConfigDict
# ---------------------------------------------------------------------------
# The canonical type for a configuration data bag that flows through the
# layer pipeline.  Intentionally broad (str→Any) — concrete layers narrow
# the types internally.
ConfigDict = Dict[str, Any]

# ---------------------------------------------------------------------------
# Keybind
# ---------------------------------------------------------------------------
# A single keybinding triple: (key_sequence, qutebrowser_command, mode).
# Example: ("<ctrl-d>", "scroll-page 0 0.5", "normal")
Keybind = Tuple[str, str, str]

__all__ = ["ConfigDict", "Keybind"]
