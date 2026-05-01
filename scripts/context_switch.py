#!/usr/bin/env python3
"""
scripts/context_switch.py
==========================
Context Switch Userscript

Switches the active qutebrowser browsing context and reloads config.

Usage (via keybindings in config.py):
  ,Cd  → dev context
  ,Cw  → work context
  ,Cr  → research context
  ,Cm  → media context
  ,C0  → default context

How it works:
  1. Reads the requested context from argv[1]
  2. Writes QUTE_CONTEXT=<context> to a persistent file (~/.config/qutebrowser/.context)
  3. Sends :config-source to reload config (which reads the file)
  4. Shows a message with the new context

The context file is read by ContextLayer._resolve_active_mode() at load time.

qutebrowser userscript interface:
  QUTE_FIFO       — write commands here
  QUTE_CONFIG_DIR — path to config directory
"""

from __future__ import annotations

import os
import sys


def _fifo_cmd(cmd: str) -> None:
    """Write a command to the qutebrowser FIFO."""
    fifo = os.environ.get("QUTE_FIFO")
    if fifo:
        with open(fifo, "w") as f:
            f.write(cmd + "\n")


def _context_file() -> str:
    config_dir = os.environ.get(
        "QUTE_CONFIG_DIR",
        os.path.expanduser("~/.config/qutebrowser"),
    )
    return os.path.join(config_dir, ".context")


VALID_CONTEXTS = {"default", "work", "research", "media", "dev"}


def main() -> None:
    if len(sys.argv) < 2:
        _fifo_cmd("message-error 'context_switch: no context given'")
        sys.exit(1)

    requested = sys.argv[1].lower().strip()

    if requested not in VALID_CONTEXTS:
        _fifo_cmd(
            f"message-error 'context_switch: unknown context {requested!r}  "
            f"valid: {sorted(VALID_CONTEXTS)}'"
        )
        sys.exit(1)

    # Persist the context choice
    try:
        with open(_context_file(), "w") as f:
            f.write(requested)
    except OSError as exc:
        _fifo_cmd(f"message-error 'context_switch: write failed: {exc}'")
        sys.exit(1)

    # Set env var for the CURRENT session (takes effect on next :config-source)
    os.environ["QUTE_CONTEXT"] = requested

    # Reload config and show confirmation
    _fifo_cmd("config-source")
    _fifo_cmd(f"message-info 'Context switched to: {requested}'")


if __name__ == "__main__":
    main()
