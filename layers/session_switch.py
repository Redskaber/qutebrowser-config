"""
scripts/session_switch.py
==========================
Session Switch Userscript  (v11)

Switches the active qutebrowser session mode and reloads config.

Usage (via keybindings registered in SessionLayer):
  ,Sd   → day      session
  ,Se   → evening  session
  ,Sn   → night    session
  ,Sf   → focus    session
  ,Sc   → commute  session
  ,Sp   → present  session
  ,S0   → auto     (time-derived)

How it works:
  1. Reads the requested session from argv[1]
  2. Writes the session name to ~/.config/qutebrowser/.session
  3. Sends :config-source to trigger a config reload
  4. Shows a confirmation message in the browser

The session file is read by SessionLayer._resolve_active_session() at
load time.  SessionLayer (priority=55) overrides PerformanceLayer (p=50)
and is itself overridden by UserLayer (p=90).

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


def _session_file() -> str:
    config_dir = os.environ.get(
        "QUTE_CONFIG_DIR",
        os.path.expanduser("~/.config/qutebrowser"),
    )
    return os.path.join(config_dir, ".session")


VALID_SESSIONS = {"auto", "day", "evening", "night", "focus", "commute", "present"}

_SESSION_LABELS = {
    "auto":    "Auto (time-derived)",
    "day":     "Day — standard working hours",
    "evening": "Evening — reduced brightness, larger text",
    "night":   "Night — low-light, minimal chrome",
    "focus":   "Focus — deep work, no distractions",
    "commute": "Commute — bandwidth-constrained",
    "present": "Present — screen-share / demo",
}


def _warn(msg: str) -> None:
    _fifo_cmd(f"message-warning 'session_switch: {msg}'")


def _fatal(msg: str) -> None:
    _fifo_cmd(f"message-error 'session_switch: {msg}'")
    sys.exit(1)


def main() -> None:
    if len(sys.argv) < 2:
        _warn(f"no session given — valid: {sorted(VALID_SESSIONS)}")
        return

    requested = sys.argv[1].lower().strip()

    if requested not in VALID_SESSIONS:
        _warn(
            f"unknown session {requested!r} — "
            f"valid: {sorted(VALID_SESSIONS)}"
        )
        return

    # Persist the session choice
    try:
        with open(_session_file(), "w") as f:
            f.write(requested)
    except OSError as exc:
        _fatal(f"write failed: {exc}")
        return

    os.environ["QUTE_SESSION"] = requested

    label = _SESSION_LABELS.get(requested, requested)
    _fifo_cmd("config-source")
    _fifo_cmd(f"message-info 'Session → {label}'")


if __name__ == "__main__":
    try:
        main()
    except SystemExit:
        raise
    except Exception as exc:  # pragma: no cover
        _fatal(f"unexpected error: {exc}")
