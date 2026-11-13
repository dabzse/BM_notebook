"""Fast native QSyntaxHighlighter for Python and Markdown cells."""

from __future__ import annotations

import builtins
import keyword
import re

from PySide6.QtGui import (
    QColor,
    QFont,
    QSyntaxHighlighter,
    QTextCharFormat,
    QTextDocument,
)

from .theme import ThemePalette


def _make_fmt(color: str, bold: bool = False, italic: bool = False) -> QTextCharFormat:
    fmt = QTextCharFormat()
    fmt.setForeground(QColor(color))
    if bold:
        fmt.setFontWeight(QFont.Weight.Bold)
    if italic:
        fmt.setFontItalic(True)
    return fmt


class PythonSyntaxHighlighter(QSyntaxHighlighter):
    """Lightweight regex-based Python syntax highlighter with multiline string state."""

    def __init__(self, document: QTextDocument, palette: ThemePalette) -> None:
        super().__init__(document)
        self._palette = palette
        self._rules: list[tuple[re.Pattern[str], int, QTextCharFormat]] = []
        self._build_rules()

    def set_palette(self, palette: ThemePalette) -> None:
        self._palette = palette
        self._build_rules()
        self.rehighlight()

    def _build_rules(self) -> None:
        p = self._palette
        kw_fmt = _make_fmt(p.syn_keyword, bold=True)
        bi_fmt = _make_fmt(p.syn_builtin)
        def_fmt = _make_fmt(p.syn_def, bold=True)
        dec_fmt = _make_fmt(p.syn_decorator)
        num_fmt = _make_fmt(p.syn_number)
        str_fmt = _make_fmt(p.syn_string)
        cmt_fmt = _make_fmt(p.syn_comment, italic=True)

        kw_words = "|".join(re.escape(w) for w in keyword.kwlist)
        bi_words = "|".join(
            re.escape(w) for w in sorted(set(dir(builtins)) - set(keyword.kwlist)) if w.isidentifier()
        )

        self._str_fmt = str_fmt
        self._cmt_fmt = cmt_fmt

        self._rules = [
            (re.compile(rf"\b({kw_words})\b"), 1, kw_fmt),
            (re.compile(rf"\b({bi_words})\b"), 1, bi_fmt),
            (re.compile(r"\b(?:def|class)\s+([A-Za-z_]\w*)"), 1, def_fmt),
            (re.compile(r"^(\s*@[A-Za-z_][\w.]*)"), 1, dec_fmt),
            (re.compile(r"\b(0[xXoObB][0-9a-fA-F_]+)\b"), 1, num_fmt),
            (re.compile(r"\b(\d+(?:\.\d+)?(?:[eE][+-]?\d+)?j?)\b"), 1, num_fmt),
            (re.compile(r"([fFrRbBuU]{0,2}'(?:\\.|[^'\\\n])*')"), 1, str_fmt),
            (re.compile(r'([fFrRbBuU]{0,2}"(?:\\.|[^"\\\n])*")'), 1, str_fmt),
            (re.compile(r"(#.*)"), 1, cmt_fmt),
        ]

    def highlightBlock(self, text: str) -> None:
        for pattern, group, fmt in self._rules:
            for match in pattern.finditer(text):
                start = match.start(group)
                self.setFormat(start, match.end(group) - start, fmt)
        self._highlight_multiline_strings(text)

    def _highlight_multiline_strings(self, text: str) -> None:
        self.setCurrentBlockState(0)
        for state, delim in ((1, "'''"), (2, '"""')):
            if self._apply_delimited_span(text, state, delim):
                return

    def _apply_delimited_span(self, text: str, state: int, delim: str) -> bool:
        in_state = self.previousBlockState() == state
        start = 0 if in_state else text.find(delim)
        while start >= 0:
            search_from = 0 if (start == 0 and in_state) else start + 3
            end = text.find(delim, search_from)
            if end == -1:
                self.setCurrentBlockState(state)
                self.setFormat(start, len(text) - start, self._str_fmt)
                return True
            length = end - start + 3
            self.setFormat(start, length, self._str_fmt)
            in_state = False
            start = text.find(delim, start + length)
        return False


class MarkdownSyntaxHighlighter(QSyntaxHighlighter):
    """Syntax highlighter for raw Markdown cell editing."""

    def __init__(self, document: QTextDocument, palette: ThemePalette) -> None:
        super().__init__(document)
        self._palette = palette
        self._build_rules()

    def set_palette(self, palette: ThemePalette) -> None:
        self._palette = palette
        self._build_rules()
        self.rehighlight()

    def _build_rules(self) -> None:
        p = self._palette
        self._rules: list[tuple[re.Pattern[str], QTextCharFormat]] = [
            (re.compile(r"^#{1,6}\s+.*"), _make_fmt(p.syn_keyword, bold=True)),
            (re.compile(r"\*\*[^*]+\*\*|__[^_]+__"), _make_fmt(p.syn_def, bold=True)),
            (re.compile(r"`[^`]+`"), _make_fmt(p.syn_string)),
            (re.compile(r"\[[^\]]+\]\([^)]+\)"), _make_fmt(p.syn_builtin)),
            (re.compile(r"^\s*>\s+.*"), _make_fmt(p.syn_comment, italic=True)),
        ]

    def highlightBlock(self, text: str) -> None:
        for pattern, fmt in self._rules:
            for match in pattern.finditer(text):
                self.setFormat(match.start(), match.end() - match.start(), fmt)
