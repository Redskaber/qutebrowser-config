#!/usr/bin/env python3
"""
scripts/context_switch.py
==========================
Context Switch Userscript

Switches the active qutebrowser browsing context and reloads config.

Usage (via keybindings registered in ContextLayer):
  ,Cd   → dev      context
  ,Cw   → work     context
  ,Cr   → research context
  ,Cm   → media    context
  ,Cwt  → writing  context   (NEW v6)
  ,C0   → default  context

How it works:
  1. Reads the requested context from argv[1]
  2. Writes the context name to ~/.config/qutebrowser/.context
  3. Sends :config-source to trigger a config reload
  4. Shows a confirmation message in the browser

The context file is read by ContextLayer._resolve_active_mode() at load time
(priority 3 in the resolution chain, after the constructor param and env var).

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


VALID_CONTEXTS = {"default", "work", "research", "media", "dev", "writing", "gaming"}

_CONTEXT_LABELS = {
    "default":  "Default (base settings)",
    "work":     "Work — corporate tools & search",
    "research": "Research — arXiv, Scholar, Wikipedia",
    "media":    "Media — YouTube, Bilibili, autoplay ON",
    "dev":      "Dev — GitHub, MDN, crates, npm",
    "writing":  "Writing — focus, dict, thesaurus",
    "gaming":   "Gaming — Steam, Twitch, ProtonDB",
}


def _warn(msg: str) -> None:
    """User-facing warning — exits 0."""
    _fifo_cmd(f"message-warning 'context_switch: {msg}'")


def _fatal(msg: str) -> None:
    """Script/system error — exits 1."""
    _fifo_cmd(f"message-error 'context_switch: {msg}'")
    sys.exit(1)


def main() -> None:
    if len(sys.argv) < 2:
        _warn(f"no context given — valid: {sorted(VALID_CONTEXTS)}")
        return

    requested = sys.argv[1].lower().strip()

    if requested not in VALID_CONTEXTS:
        _warn(
            f"unknown context {requested!r} — "
            f"valid: {sorted(VALID_CONTEXTS)}"
        )
        return

    # Persist the context choice
    try:
        with open(_context_file(), "w") as f:
            f.write(requested)
    except OSError as exc:
        _fatal(f"write failed: {exc}")
        return

    # Set env var for the CURRENT session (read on next :config-source)
    os.environ["QUTE_CONTEXT"] = requested

    # Reload config and show confirmation
    label = _CONTEXT_LABELS.get(requested, requested)
    _fifo_cmd("config-source")
    _fifo_cmd(f"message-info 'Context → {label}'")


if __name__ == "__main__":
    try:
        main()
    except SystemExit:
        raise
    except Exception as exc:  # pragma: no cover
        _fatal(f"unexpected error: {exc}")
