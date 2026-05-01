#!/usr/bin/env python3
"""
scripts/open_with.py
====================
Userscript: Open With External Application

Opens the current URL (or hinted link URL) with an external program.
Supports auto-detection of the best program based on URL MIME type / scheme,
or explicit program selection via command-line argument.

Usage (add to config.py USER_EXTRA_BINDINGS or BehaviorLayer):
    (",o",  "spawn --userscript open_with.py",                  "normal")
    (",O",  "spawn --userscript open_with.py --app mpv",        "normal")
    (",m",  "spawn --userscript open_with.py --app mpv",        "normal")
    (";m",  "hint links spawn --userscript open_with.py --app mpv", "normal")

Environment (injected by qutebrowser):
    QUTE_URL       — current page URL
    QUTE_FIFO      — path to qutebrowser FIFO for commands

Supported apps (auto-detected by URL pattern):
    mpv            — video/audio streams (youtube, twitch, direct media)
    zathura        — PDFs
    feh / imv      — images
    xdg-open       — fallback

Requires: the respective applications to be on PATH.
"""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
from urllib.parse import urlparse

QUTE_URL  = os.environ.get("QUTE_URL", "")
QUTE_FIFO = os.environ.get("QUTE_FIFO", "")


# ─────────────────────────────────────────────
# Communication
# ─────────────────────────────────────────────
def send(cmd: str) -> None:
    """Send a command to qutebrowser via the FIFO."""
    if QUTE_FIFO:
        with open(QUTE_FIFO, "w") as f:
            f.write(cmd + "\n")


def info(msg: str) -> None:
    send(f"message-info '[open-with] {msg}'")


def error(msg: str) -> None:
    send(f"message-error '[open-with] {msg}'")
    sys.exit(1)


# ─────────────────────────────────────────────
# URL Classification
# ─────────────────────────────────────────────
_VIDEO_HOSTS = frozenset({
    "www.youtube.com", "youtu.be", "youtube.com",
    "www.twitch.tv",   "twitch.tv",
    "www.bilibili.com","bilibili.com",
    "vimeo.com",       "www.vimeo.com",
    "rumble.com",
    "odysee.com",
})

_VIDEO_EXTS = frozenset({
    ".mp4", ".mkv", ".webm", ".avi", ".mov",
    ".flv", ".m4v", ".ts",  ".m3u8", ".mpd",
})

_AUDIO_EXTS = frozenset({
    ".mp3", ".flac", ".ogg", ".opus", ".m4a", ".wav", ".aac",
})

_IMAGE_EXTS = frozenset({
    ".jpg", ".jpeg", ".png", ".gif", ".webp", ".svg", ".bmp", ".avif",
})

_PDF_EXT = ".pdf"


def classify_url(url: str) -> str:
    """Return a content category: video | audio | image | pdf | web."""
    parsed = urlparse(url)
    host   = parsed.netloc.lower().lstrip("www.")
    path   = parsed.path.lower()
    ext    = os.path.splitext(path)[1]

    if "www." + host in _VIDEO_HOSTS or host in _VIDEO_HOSTS:
        return "video"
    if ext in _VIDEO_EXTS:
        return "video"
    if ext in _AUDIO_EXTS:
        return "audio"
    if ext in _IMAGE_EXTS:
        return "image"
    if ext == _PDF_EXT:
        return "pdf"
    return "web"


# ─────────────────────────────────────────────
# App Selection
# ─────────────────────────────────────────────
def _has(cmd: str) -> bool:
    return shutil.which(cmd) is not None


def select_app(category: str) -> list[str]:
    """Return the command list for the best available app for the category."""
    if category == "video":
        for app in ("mpv", "vlc", "celluloid"):
            if _has(app):
                return [app]
        return ["xdg-open"]

    if category == "audio":
        for app in ("mpv", "vlc", "rhythmbox"):
            if _has(app):
                return [app]
        return ["xdg-open"]

    if category == "image":
        for app in ("imv", "feh", "eog", "eom"):
            if _has(app):
                if app == "feh":
                    return ["feh", "--auto-zoom", "--scale-down"]
                return [app]
        return ["xdg-open"]

    if category == "pdf":
        for app in ("zathura", "evince", "okular", "mupdf"):
            if _has(app):
                return [app]
        return ["xdg-open"]

    return ["xdg-open"]


# ─────────────────────────────────────────────
# Main
# ─────────────────────────────────────────────
def main() -> None:
    parser = argparse.ArgumentParser(
        description="Open current URL with an external application."
    )
    parser.add_argument(
        "--app", metavar="APP",
        help="Force a specific application (e.g. mpv, zathura, feh)"
    )
    parser.add_argument(
        "--url", metavar="URL",
        help="Override URL (default: $QUTE_URL)"
    )
    args = parser.parse_args()

    url = args.url or QUTE_URL
    if not url:
        error("No URL available (QUTE_URL not set)")
        return

    if args.app:
        if not _has(args.app):
            error(f"Application not found on PATH: {args.app}")
            return
        cmd = [args.app, url]
        app_name = args.app
    else:
        category = classify_url(url)
        app_cmd  = select_app(category)
        cmd      = app_cmd + [url]
        app_name = app_cmd[0]

    # Launch detached so qutebrowser doesn't wait for it
    try:
        subprocess.Popen(
            cmd,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
        )
        # Abbreviate long URLs for the status message
        display_url = url if len(url) <= 60 else url[:57] + "…"
        info(f"opened with {app_name}: {display_url}")
    except FileNotFoundError:
        error(f"Cannot execute: {cmd[0]}")
    except Exception as exc:
        error(f"Launch failed: {exc}")


if __name__ == "__main__":
    main()


