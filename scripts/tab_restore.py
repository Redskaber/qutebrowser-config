#!/usr/bin/env python3
"""
scripts/tab_restore.py
======================
Userscript: Named Session Save / Restore

Save all open tabs to a named session file, or restore a saved session.
Sessions are plain-text files (one URL per line) stored in
~/.local/share/qutebrowser/sessions/named/.

Usage (add to USER_EXTRA_BINDINGS):
    (",Ss", "spawn --userscript tab_restore.py --save work",    "normal")
    (",Sr", "spawn --userscript tab_restore.py --restore work", "normal")
    (",Sl", "spawn --userscript tab_restore.py --list",         "normal")

Alternatively, use qutebrowser's native session commands:
    :session-save <name>
    :session-load <name>

This script is a lightweight alternative that stores sessions as plain
URL lists — easier to edit, version, and share.

Environment (injected by qutebrowser):
    QUTE_URL        — current tab URL
    QUTE_FIFO       — FIFO for commands
    QUTE_DATA_DIR   — qutebrowser data directory

Note: To save ALL open tabs (not just current), qutebrowser must be
invoked with `:session-save` or the script must iterate via the
:jseval API — not available in userscripts.
This script saves/restores the URLs listed in QUTE_URLS (space-separated)
if injected via a custom binding, or the current tab as a fallback.
"""

from __future__ import annotations

import argparse
import os
import sys
from datetime import datetime
from pathlib import Path

QUTE_FIFO     = os.environ.get("QUTE_FIFO", "")
QUTE_URL      = os.environ.get("QUTE_URL", "")
QUTE_DATA_DIR = os.environ.get("QUTE_DATA_DIR",
                               os.path.expanduser("~/.local/share/qutebrowser"))
QUTE_URLS     = os.environ.get("QUTE_URLS", "")  # space-sep list (custom injection)


def send(cmd: str) -> None:
    if QUTE_FIFO:
        with open(QUTE_FIFO, "w") as f:
            f.write(cmd + "\n")


def info(msg: str) -> None:
    send(f"message-info '[tab-restore] {msg}'")


def warn(msg: str) -> None:
    """User-facing warning — exits 0."""
    send(f"message-warning '[tab-restore] {msg}'")


def fatal(msg: str) -> None:
    """Script/system error — exits 1."""
    send(f"message-error '[tab-restore] {msg}'")
    sys.exit(1)


# Backward-compatible alias
error = warn  # tab-restore errors are mostly "not found" — user feedback, not crashes


def session_dir() -> Path:
    d = Path(QUTE_DATA_DIR) / "sessions" / "named"
    d.mkdir(parents=True, exist_ok=True)
    return d


def session_path(name: str) -> Path:
    safe = "".join(c if c.isalnum() or c in "-_" else "_" for c in name)
    return session_dir() / f"{safe}.session"


def do_save(name: str) -> None:
    urls: list[str] = []

    if QUTE_URLS:
        urls = [u for u in QUTE_URLS.split() if u.startswith("http")]
    elif QUTE_URL:
        urls = [QUTE_URL]

    if not urls:
        error("No URLs to save")
        return

    path = session_path(name)
    try:
        with open(path, "w") as f:
            f.write(f"# tab-restore session: {name}\n")
            f.write(f"# saved: {datetime.now().isoformat(timespec='seconds')}\n")
            for url in urls:
                f.write(url + "\n")
    except OSError as exc:
        fatal(f"write failed: {exc}")
        return

    info(f"saved {len(urls)} tab(s) → {name}")


def do_restore(name: str) -> None:
    path = session_path(name)
    if not path.exists():
        error(f"Session not found: {name}")
        return

    urls: list[str] = []
    with open(path) as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#"):
                urls.append(line)

    if not urls:
        error(f"Session {name} is empty")
        return

    for url in urls:
        send(f"open -t {url}")

    info(f"restored {len(urls)} tab(s) from {name}")


def do_list() -> None:
    d = session_dir()
    sessions = sorted(d.glob("*.session"))
    if not sessions:
        info("No saved sessions")
        return

    names = ", ".join(p.stem for p in sessions)
    info(f"sessions: {names}")


def do_delete(name: str) -> None:
    path = session_path(name)
    if not path.exists():
        error(f"Session not found: {name}")
        return
    path.unlink()
    info(f"deleted session: {name}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Named tab session manager.")
    group  = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--save",    metavar="NAME", help="Save current tabs")
    group.add_argument("--restore", metavar="NAME", help="Restore tabs from session")
    group.add_argument("--delete",  metavar="NAME", help="Delete a saved session")
    group.add_argument("--list",    action="store_true", help="List saved sessions")
    args = parser.parse_args()

    if args.save:
        do_save(args.save)
    elif args.restore:
        do_restore(args.restore)
    elif args.delete:
        do_delete(args.delete)
    elif args.list:
        do_list()


if __name__ == "__main__":
    try:
        main()
    except SystemExit:
        raise
    except Exception as exc:  # pragma: no cover
        fatal(f"unexpected error: {exc}")


