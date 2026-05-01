#!/usr/bin/env python3
"""
scripts/password.py
===================
Userscript: Password Manager Integration

Integrates with pass (the standard unix password manager).
Finds the correct entry by hostname, fills login forms.

Usage (add to config.py BehaviorLayer or UserLayer):
    config.bind(",p",  "spawn --userscript password.py",         mode="normal")
    config.bind(",P",  "spawn --userscript password.py --otp",   mode="normal")

Requires: pass (passwordstore.org), xdotool or wl-clipboard (Wayland)

Protocol:
  1. Extract hostname from QUTE_URL
  2. Run: pass show {hostname}
  3. Parse username/password from pass output
  4. Send fill commands via QUTE_FIFO
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
from urllib.parse import urlparse


QUTE_URL  = os.environ.get("QUTE_URL", "")
QUTE_FIFO = os.environ.get("QUTE_FIFO", "")
PLATFORM  = os.environ.get("QUTE_QT_PLATFORM", "wayland")


def send(cmd: str) -> None:
    if QUTE_FIFO:
        with open(QUTE_FIFO, "w") as f:
            f.write(cmd + "\n")


def error(msg: str) -> None:
    send(f"message-error '[pass] {msg}'")
    sys.exit(1)


def run(cmd: list[str]) -> str:
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=10,
        )
        if result.returncode != 0:
            return ""
        return result.stdout.strip()
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return ""


def parse_pass_output(text: str) -> dict[str, str]:
    """
    Parse pass entry format:
      Line 1: password
      Remaining: key: value pairs
    """
    lines = text.splitlines()
    if not lines:
        return {}

    data: dict[str, str] = {"password": lines[0]}
    for line in lines[1:]:
        if ":" in line:
            k, _, v = line.partition(":")
            data[k.strip().lower()] = v.strip()
    return data


def find_entry(hostname: str) -> str:
    """Search pass store for best matching entry."""
    # Try exact hostname first, then domain without subdomain
    candidates = [hostname]
    parts = hostname.split(".")
    if len(parts) > 2:
        candidates.append(".".join(parts[-2:]))

    for candidate in candidates:
        # Use pass find to search
        result = run(["pass", "show", candidate])
        if result:
            return result

        # Try searching within pass store
        find_out = run(["pass", "find", candidate])
        if find_out:
            # Extract first match from find output
            for line in find_out.splitlines():
                line = line.strip().lstrip("└├─ ")
                if line and not line.startswith("Search"):
                    result = run(["pass", "show", line])
                    if result:
                        return result
    return ""


def to_clipboard(text: str) -> None:
    """Copy text to clipboard (Wayland or X11)."""
    if PLATFORM == "wayland":
        run(["wl-copy", text])
    else:
        proc = subprocess.Popen(
            ["xclip", "-selection", "clipboard"],
            stdin=subprocess.PIPE,
        )
        proc.communicate(text.encode())


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--otp", action="store_true", help="Get OTP code")
    parser.add_argument("--username", action="store_true", help="Fill username only")
    args = parser.parse_args()

    if not QUTE_URL:
        error("QUTE_URL not set")

    hostname = urlparse(QUTE_URL).hostname or ""
    if not hostname:
        error(f"Cannot parse hostname from: {QUTE_URL}")

    if args.otp:
        otp = run(["pass", "otp", hostname])
        if not otp:
            error(f"No OTP entry for {hostname}")
        to_clipboard(otp)
        send(f"message-info '[pass] OTP copied for {hostname}'")
        # Fill the focused input field
        send("fake-key --global <ctrl-a>")
        send(f"fake-key --global {otp}")
        return

    entry_text = find_entry(hostname)
    if not entry_text:
        error(f"No pass entry for {hostname}")

    data = parse_pass_output(entry_text)
    password = data.get("password", "")
    username = data.get("username", data.get("login", data.get("user", "")))

    if args.username and username:
        send(f"fake-key --global {username}")
        send(f"message-info '[pass] username filled for {hostname}'")
        return

    # Fill username → Tab → password → Enter
    if username:
        send(f"fake-key --global {username}")
        send("fake-key --global <Tab>")

    if password:
        send(f"fake-key --global {password}")

    send(f"message-info '[pass] credentials filled for {hostname}'")


if __name__ == "__main__":
    main()
