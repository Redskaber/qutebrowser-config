"""
tests/test_conf.py
=================
pytest configuration for the qutebrowser-config test suite.

Ensures the project root is on sys.path so that imports like
``from core.layer import ...`` resolve correctly regardless of
how pytest is invoked (from root, from tests/, or via IDE).
"""

from __future__ import annotations

import os
import sys

# Insert the project root (parent of this tests/ directory) at the front
# of sys.path so that `core`, `layers`, `strategies`, `policies`, `themes`,
# and `keybindings` sub-packages are importable without installation.
_tests_dir = os.path.dirname(os.path.abspath(__file__))
_project_root = os.path.dirname(_tests_dir)

if _project_root not in sys.path:
    sys.path.insert(0, _project_root)
