"""ANSI escape sequence to HTML converter for clean native traceback & stdout rendering."""

from __future__ import annotations

import html
import re

_ANSI_RE = re.compile(r"\x1b\[([\d;]*)m")

_DARK_COLORS = {
    30: "#4F5666",
    31: "#F26D78",
    32: "#3DD68C",
    33: "#F5B849",
    34: "#5B8AF5",
    35: "#C792EA",
    36: "#56D4DD",
    37: "#E6EAF2",
    90: "#737D94",
    91: "#FF8590",
    92: "#6AE8AB",
    93: "#FFD175",
    94: "#82AAFF",
    95: "#DFA8FF",
    96: "#7CE8F0",
    97: "#FFFFFF",
}

_LIGHT_COLORS = {
    30: "#1A202C",
    31: "#C92A3E",
    32: "#137A48",
    33: "#A16207",
    34: "#1D4ED8",
    35: "#7E22CE",
    36: "#0E7490",
    37: "#4A5568",
    90: "#64748B",
    91: "#DC2626",
    92: "#16A34A",
    93: "#CA8A04",
    94: "#2563EB",
    95: "#9333EA",
    96: "#0891B2",
    97: "#0F172A",
}


_SGR_RESET = 0
_SGR_BOLD = 1
_SGR_NORMAL_INTENSITY = 22
_SGR_EXTENDED_FG = 38
_SGR_DEFAULT_FG = 39
_SGR_EXT_256 = 5
_SGR_EXT_RGB = 2
_ANSI_16_LIMIT = 16
_ANSI_8_BASE = 8


def strip_ansi(text: str) -> str:
    return _ANSI_RE.sub("", text)


def _apply_extended_fg(
    codes: list[int],
    pos: int,
    cmap: dict[int, str],
    fg: str | None,
) -> tuple[str | None, int]:
    if pos + 1 >= len(codes):
        return fg, 1
    mode = codes[pos + 1]
    if mode == _SGR_EXT_256 and pos + 2 < len(codes):
        idx = codes[pos + 2]
        if idx < _ANSI_16_LIMIT:
            offset = 60 if idx >= _ANSI_8_BASE else 0
            fg = cmap.get(30 + (idx % _ANSI_8_BASE) + offset)
        return fg, 3
    if mode == _SGR_EXT_RGB and pos + 4 < len(codes):
        r, g, b = codes[pos + 2], codes[pos + 3], codes[pos + 4]
        return f"rgb({r},{g},{b})", 5
    return fg, 1


def _apply_sgr_codes(
    codes: list[int],
    cmap: dict[int, str],
    fg: str | None,
    bold: bool,
) -> tuple[str | None, bool]:
    i = 0
    while i < len(codes):
        c = codes[i]
        if c == _SGR_EXTENDED_FG:
            fg, step = _apply_extended_fg(codes, i, cmap, fg)
            i += step
            continue
        if c == _SGR_RESET:
            fg, bold = None, False
        elif c == _SGR_BOLD:
            bold = True
        elif c == _SGR_NORMAL_INTENSITY:
            bold = False
        elif c == _SGR_DEFAULT_FG:
            fg = None
        elif c in cmap:
            fg = cmap[c]
        i += 1
    return fg, bold


def _build_span_open(fg: str | None, bold: bool) -> str:
    styles: list[str] = []
    if fg:
        styles.append(f"color:{fg}")
    if bold:
        styles.append("font-weight:bold")
    return f'<span style="{";".join(styles)}">' if styles else ""


def ansi_to_html(text: str, dark: bool = True) -> str:
    """Convert ANSI SGR codes into styled `<span style=...>` HTML fragments."""
    cmap = _DARK_COLORS if dark else _LIGHT_COLORS
    out: list[str] = []
    pos = 0
    fg: str | None = None
    bold = False
    open_span = False

    for match in _ANSI_RE.finditer(text):
        if match.start() > pos:
            out.append(html.escape(text[pos:match.start()]))
        pos = match.end()

        codes_raw = match.group(1)
        codes = [int(c) for c in codes_raw.split(";") if c.isdigit()] if codes_raw else [0]
        fg, bold = _apply_sgr_codes(codes, cmap, fg, bold)

        if open_span:
            out.append("</span>")
        span_tag = _build_span_open(fg, bold)
        if span_tag:
            out.append(span_tag)
        open_span = bool(span_tag)

    if pos < len(text):
        out.append(html.escape(text[pos:]))
    if open_span:
        out.append("</span>")
    return "".join(out)
