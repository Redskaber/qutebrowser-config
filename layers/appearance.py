"""
layers/appearance.py
====================
Appearance Layer — Themes, Fonts, Colors

Priority: 30

Architecture:
  ColorScheme (data) → AppearanceLayer (renderer) → qutebrowser settings

The theme is a pure immutable data structure (``ColorScheme``).
The layer renders it into qutebrowser's config key-space.
Swapping themes requires only changing the ``theme`` constructor argument;
keybindings and behavior are never touched.

Pattern: Strategy (theme as data) + Template Method (build orchestrates
  _color_settings, _font_settings, _hints_settings, _misc_settings)

Fix applied vs original:
  ``colors.downloads.system.fg/bg`` were set to the string ``"rgb"``
  which is not a valid qutebrowser color value; those keys are removed.
  The ``"system"`` color type is a *qutebrowser internal enum* that means
  "use the system gradient" and is not user-configurable via config.set().

v9 changes:
  - ``_font_settings`` now reads ``ColorScheme.font_size_web`` to set
    ``fonts.web.size.default`` instead of the hard-coded ``16``.
  - Added ``parse_px(s)`` helper to convert ``"16px"`` / ``"16"`` strings
    to the integer pixel value qutebrowser expects for web font sizes.
  - ``fonts.default_family`` and ``fonts.default_size`` now explicitly set
    from ``ColorScheme.font_mono`` / ``font_size_ui`` so that UserLayer
    font overrides (priority=90) correctly replace them.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List

from core.types import ConfigDict
from core.layer import BaseConfigLayer


# ─────────────────────────────────────────────
# Color Scheme Data Type
# ─────────────────────────────────────────────

@dataclass(frozen=True)
class ColorScheme:
    """
    Immutable color scheme.
    All color values are CSS hex colors or Qt color names.
    """
    # ── Base palette ───────────────────────────────────────────────────
    bg:         str = "#1e1e2e"   # base background
    bg_alt:     str = "#181825"   # secondary background
    bg_surface: str = "#313244"   # surface (tabs, statusbar backgrounds)
    fg:         str = "#cdd6f4"   # primary foreground text
    fg_dim:     str = "#6c7086"   # dimmed / muted text
    fg_strong:  str = "#ffffff"   # emphasis text

    # ── Semantic / accent ──────────────────────────────────────────────
    accent:     str = "#89b4fa"   # primary accent (blue)
    accent2:    str = "#cba6f7"   # secondary accent (mauve/purple)
    success:    str = "#a6e3a1"   # green
    warning:    str = "#f9e2af"   # yellow
    error:      str = "#f38ba8"   # red
    info:       str = "#89dceb"   # teal / cyan

    # ── Hint overlay ───────────────────────────────────────────────────
    hint_bg:     str = "#1e1e2e"
    hint_fg:     str = "#f38ba8"
    hint_border: str = "#89b4fa"

    # ── Selection ──────────────────────────────────────────────────────
    select_bg:   str = "#45475a"
    select_fg:   str = "#cdd6f4"

    # ── Typography ─────────────────────────────────────────────────────
    font_mono:     str = "JetBrainsMono Nerd Font"
    font_sans:     str = "Noto Sans"
    font_size_ui:  str = "10pt"
    font_size_web: str = "16px"


# ─────────────────────────────────────────────
# Built-in Themes
# ─────────────────────────────────────────────

THEMES: Dict[str, ColorScheme] = {
    "catppuccin-mocha": ColorScheme(
        bg="#1e1e2e", bg_alt="#181825", bg_surface="#313244",
        fg="#cdd6f4", fg_dim="#6c7086", fg_strong="#ffffff",
        accent="#89b4fa", accent2="#cba6f7",
        success="#a6e3a1", warning="#f9e2af", error="#f38ba8", info="#89dceb",
        hint_bg="#1e1e2e", hint_fg="#f38ba8", hint_border="#89b4fa",
        select_bg="#45475a", select_fg="#cdd6f4",
        font_mono="JetBrainsMono Nerd Font", font_sans="Noto Sans",
    ),
    "catppuccin-latte": ColorScheme(
        bg="#eff1f5", bg_alt="#e6e9ef", bg_surface="#ccd0da",
        fg="#4c4f69", fg_dim="#9ca0b0", fg_strong="#1e1e2e",
        accent="#1e66f5", accent2="#8839ef",
        success="#40a02b", warning="#df8e1d", error="#d20f39", info="#04a5e5",
        hint_bg="#eff1f5", hint_fg="#d20f39", hint_border="#1e66f5",
        select_bg="#ccd0da", select_fg="#4c4f69",
        font_mono="JetBrainsMono Nerd Font", font_sans="Noto Sans",
    ),
    "gruvbox-dark": ColorScheme(
        bg="#282828", bg_alt="#1d2021", bg_surface="#3c3836",
        fg="#ebdbb2", fg_dim="#928374", fg_strong="#fbf1c7",
        accent="#83a598", accent2="#d3869b",
        success="#b8bb26", warning="#fabd2f", error="#fb4934", info="#8ec07c",
        hint_bg="#282828", hint_fg="#fb4934", hint_border="#fabd2f",
        select_bg="#504945", select_fg="#ebdbb2",
        font_mono="JetBrainsMono Nerd Font", font_sans="Noto Sans",
    ),
    "tokyo-night": ColorScheme(
        bg="#1a1b26", bg_alt="#16161e", bg_surface="#24283b",
        fg="#c0caf5", fg_dim="#565f89", fg_strong="#ffffff",
        accent="#7aa2f7", accent2="#bb9af7",
        success="#9ece6a", warning="#e0af68", error="#f7768e", info="#2ac3de",
        hint_bg="#1a1b26", hint_fg="#f7768e", hint_border="#7aa2f7",
        select_bg="#283457", select_fg="#c0caf5",
        font_mono="JetBrainsMono Nerd Font", font_sans="Noto Sans",
    ),
    "rose-pine": ColorScheme(
        bg="#191724", bg_alt="#1f1d2e", bg_surface="#26233a",
        fg="#e0def4", fg_dim="#6e6a86", fg_strong="#ffffff",
        accent="#31748f", accent2="#c4a7e7",
        success="#9ccfd8", warning="#f6c177", error="#eb6f92", info="#31748f",
        hint_bg="#191724", hint_fg="#eb6f92", hint_border="#31748f",
        select_bg="#403d52", select_fg="#e0def4",
        font_mono="JetBrainsMono Nerd Font", font_sans="Noto Sans",
    ),
}


# ─────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────

def parse_px(size_str: str) -> int:
    """
    Parse a CSS-like pixel size string to an integer.

    Handles:
      "16px" → 16
      "16"   → 16
      " 18 " → 18

    qutebrowser's ``fonts.web.size.*`` keys expect a plain int (pixels).
    ColorScheme stores ``font_size_web`` as ``"16px"`` for readability;
    this helper bridges the two representations.

    Raises ValueError if the string cannot be parsed.
    """
    s = size_str.strip()
    if s.endswith("px"):
        s = s[:-2].strip()
    try:
        return int(s)
    except ValueError:
        raise ValueError(
            f"Cannot parse pixel size {size_str!r} — "
            "expected a string like '16px' or '16'"
        )


# ─────────────────────────────────────────────
# Appearance Layer
# ─────────────────────────────────────────────

class AppearanceLayer(BaseConfigLayer):
    """
    Renders a ``ColorScheme`` into qutebrowser appearance settings.

    Args:
        theme: Name of a built-in theme (see ``THEMES``).

    Raises:
        ValueError: If ``theme`` is not a key in ``THEMES``.
    """

    name        = "appearance"
    priority    = 30
    description = "Theme, fonts, and visual appearance"

    def __init__(self, theme: str = "catppuccin-mocha") -> None:
        if theme not in THEMES:
            raise ValueError(
                f"Unknown theme: {theme!r}.  "
                f"Available: {list(THEMES.keys())}"
            )
        self._theme_name = theme
        self._c = THEMES[theme]

    def _settings(self) -> ConfigDict:
        c = self._c
        return {
            **self._color_settings(c),
            **self._font_settings(c),
            **self._hints_settings(c),
            **self._misc_settings(c),
        }

    # ── Color sub-renderers ────────────────────────────────────────────

    def _color_settings(self, c: ColorScheme) -> ConfigDict:
        return {
            # ── Completion ────────────────────────────────────
            "colors.completion.fg":                          [c.fg, c.fg, c.fg],
            "colors.completion.odd.bg":                      c.bg,
            "colors.completion.even.bg":                     c.bg_alt,
            "colors.completion.category.fg":                 c.accent,
            "colors.completion.category.bg":                 c.bg_surface,
            "colors.completion.category.border.top":         c.bg_surface,
            "colors.completion.category.border.bottom":      c.bg_surface,
            "colors.completion.item.selected.fg":            c.fg_strong,
            "colors.completion.item.selected.bg":            c.select_bg,
            "colors.completion.item.selected.border.top":    c.accent,
            "colors.completion.item.selected.border.bottom": c.accent,
            "colors.completion.item.selected.match.fg":      c.accent2,
            "colors.completion.match.fg":                    c.accent,
            "colors.completion.scrollbar.fg":                c.fg_dim,
            "colors.completion.scrollbar.bg":                c.bg_surface,

            # ── Downloads ─────────────────────────────────────
            # NOTE: colors.downloads.system.{fg,bg} are NOT user-configurable;
            # they are qutebrowser-internal gradient descriptors.  Setting them
            # to an arbitrary string caused "Error while loading config.py".
            "colors.downloads.bar.bg":    c.bg_surface,
            "colors.downloads.error.fg":  c.error,
            "colors.downloads.error.bg":  c.bg,
            "colors.downloads.start.fg":  c.fg,
            "colors.downloads.start.bg":  c.accent,
            "colors.downloads.stop.fg":   c.fg,
            "colors.downloads.stop.bg":   c.success,

            # ── Hints ─────────────────────────────────────────
            "colors.hints.bg":            c.hint_bg,
            "colors.hints.fg":            c.hint_fg,
            "colors.hints.match.fg":      c.accent,

            # ── Keyhint ───────────────────────────────────────
            "colors.keyhint.bg":          c.bg_surface,
            "colors.keyhint.fg":          c.fg,
            "colors.keyhint.suffix.fg":   c.accent,

            # ── Messages ──────────────────────────────────────
            "colors.messages.error.bg":      c.error,
            "colors.messages.error.border":  c.error,
            "colors.messages.error.fg":      c.bg,
            "colors.messages.info.bg":       c.info,
            "colors.messages.info.border":   c.info,
            "colors.messages.info.fg":       c.bg,
            "colors.messages.warning.bg":    c.warning,
            "colors.messages.warning.border":c.warning,
            "colors.messages.warning.fg":    c.bg,

            # ── Prompt ────────────────────────────────────────
            "colors.prompts.bg":          c.bg_surface,
            "colors.prompts.border":      f"1px solid {c.accent}",
            "colors.prompts.fg":          c.fg,
            "colors.prompts.selected.bg": c.select_bg,
            "colors.prompts.selected.fg": c.fg_strong,

            # ── Statusbar ─────────────────────────────────────
            "colors.statusbar.normal.bg":           c.bg_surface,
            "colors.statusbar.normal.fg":           c.fg,
            "colors.statusbar.insert.bg":           c.success,
            "colors.statusbar.insert.fg":           c.bg,
            "colors.statusbar.passthrough.bg":      c.accent2,
            "colors.statusbar.passthrough.fg":      c.bg,
            "colors.statusbar.private.bg":          c.bg_alt,
            "colors.statusbar.private.fg":          c.fg_dim,
            "colors.statusbar.command.bg":          c.bg_surface,
            "colors.statusbar.command.fg":          c.fg,
            "colors.statusbar.command.private.bg":  c.bg_alt,
            "colors.statusbar.command.private.fg":  c.fg_dim,
            "colors.statusbar.caret.bg":            c.accent2,
            "colors.statusbar.caret.fg":            c.bg,
            "colors.statusbar.caret.selection.bg":  c.accent,
            "colors.statusbar.caret.selection.fg":  c.bg,
            "colors.statusbar.progress.bg":         c.accent,
            "colors.statusbar.url.fg":              c.fg,
            "colors.statusbar.url.error.fg":        c.error,
            "colors.statusbar.url.hover.fg":        c.info,
            "colors.statusbar.url.success.http.fg": c.warning,
            "colors.statusbar.url.success.https.fg":c.success,
            "colors.statusbar.url.warn.fg":         c.warning,

            # ── Tabs ──────────────────────────────────────────
            "colors.tabs.bar.bg":                     c.bg_alt,
            "colors.tabs.odd.bg":                     c.bg_alt,
            "colors.tabs.odd.fg":                     c.fg_dim,
            "colors.tabs.even.bg":                    c.bg_alt,
            "colors.tabs.even.fg":                    c.fg_dim,
            "colors.tabs.selected.odd.bg":            c.bg_surface,
            "colors.tabs.selected.odd.fg":            c.fg,
            "colors.tabs.selected.even.bg":           c.bg_surface,
            "colors.tabs.selected.even.fg":           c.fg,
            "colors.tabs.pinned.odd.bg":              c.bg_alt,
            "colors.tabs.pinned.odd.fg":              c.accent,
            "colors.tabs.pinned.even.bg":             c.bg_alt,
            "colors.tabs.pinned.even.fg":             c.accent,
            "colors.tabs.pinned.selected.odd.bg":     c.bg_surface,
            "colors.tabs.pinned.selected.odd.fg":     c.accent,
            "colors.tabs.pinned.selected.even.bg":    c.bg_surface,
            "colors.tabs.pinned.selected.even.fg":    c.accent,
            "colors.tabs.indicator.start":            c.accent,
            "colors.tabs.indicator.stop":             c.success,
            "colors.tabs.indicator.error":            c.error,

            # ── Webpage ───────────────────────────────────────
            "colors.webpage.bg":                           c.bg,
            "colors.webpage.darkmode.enabled":             True,
            "colors.webpage.darkmode.algorithm":           "lightness-cielab",
            "colors.webpage.darkmode.threshold.foreground": 150,
            "colors.webpage.darkmode.threshold.background": 205,
            "colors.webpage.preferred_color_scheme":       "dark",
        }

    def _font_settings(self, c: ColorScheme) -> ConfigDict:
        # Use ColorScheme.font_size_ui for UI chrome fonts (e.g. "10pt")
        size = c.font_size_ui  # e.g. "10pt", "11pt"
        mono = f"{size} '{c.font_mono}'"
        sans = f"{size} '{c.font_sans}'"
        return {
            # ── UI chrome fonts ────────────────────────────────
            # Set fonts.default_family / fonts.default_size explicitly so
            # UserLayer (priority=90) font_family/font_size overrides apply cleanly.
            "fonts.default_family":         c.font_mono,
            "fonts.default_size":           c.font_size_ui,
            "fonts.completion.entry":       mono,
            "fonts.completion.category":    f"bold {mono}",
            "fonts.debug_console":          mono,
            "fonts.downloads":              mono,
            "fonts.hints":                  f"bold {mono}",
            "fonts.keyhint":                mono,
            "fonts.messages.error":         mono,
            "fonts.messages.info":          mono,
            "fonts.messages.warning":       mono,
            "fonts.prompts":                sans,
            "fonts.statusbar":              mono,
            "fonts.tabs.selected":          mono,
            "fonts.tabs.unselected":        mono,
            "fonts.tooltip":                mono,
            # ── Web content fonts ──────────────────────────────
            "fonts.web.family.cursive":     c.font_sans,
            "fonts.web.family.fantasy":     c.font_sans,
            "fonts.web.family.fixed":       c.font_mono,
            "fonts.web.family.sans_serif":  c.font_sans,
            "fonts.web.family.serif":       "Georgia",
            "fonts.web.family.standard":    c.font_sans,
            # fonts.web.size.default expects an int (pixels)
            # ColorScheme.font_size_web is "16px" — parse to int
            "fonts.web.size.default":       parse_px(c.font_size_web),
            "fonts.web.size.default_fixed": 13,
            "fonts.web.size.minimum":       0,
        }

    def _hints_settings(self, c: ColorScheme) -> ConfigDict:
        return {
            "hints.border": f"1px solid {c.hint_border}",
            "hints.radius": 3,
        }

    def _misc_settings(self, c: ColorScheme) -> ConfigDict:
        return {
            "content.user_stylesheets": [],
        }

    # ── Introspection ──────────────────────────────────────────────────

    @property
    def theme_name(self) -> str:
        return self._theme_name

    @classmethod
    def available_themes(cls) -> List[str]:
        return list(THEMES.keys())


