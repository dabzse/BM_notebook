"""Native Qt code editor widget with line numbers, auto-resize, smart indent, and kernel autocomplete."""

from __future__ import annotations

from PySide6.QtCore import QRect, QSize, QStringListModel, Qt, Signal
from PySide6.QtGui import (
    QColor,
    QFontDatabase,
    QKeyEvent,
    QPainter,
    QPaintEvent,
    QResizeEvent,
    QTextCursor,
    QTextFormat,
)
from PySide6.QtWidgets import QCompleter, QPlainTextEdit, QTextEdit, QWidget

from .theme import ThemePalette


class _LineNumberArea(QWidget):
    def __init__(self, editor: CodeEditor) -> None:
        super().__init__(editor)
        self._editor = editor

    def sizeHint(self) -> QSize:
        return QSize(self._editor.line_number_area_width(), 0)

    def paintEvent(self, event: QPaintEvent) -> None:
        self._editor.paint_line_numbers(event)


class CodeEditor(QPlainTextEdit):
    """Auto-resizing code editor for notebook cells."""

    run_requested = Signal(bool, bool)  # advance, insert_below
    completion_requested = Signal(str, int)  # text, cursor_pos
    focused = Signal()
    focus_lost = Signal()
    escape_pressed = Signal()

    def __init__(self, palette: ThemePalette, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._palette = palette
        self._line_area = _LineNumberArea(self)
        self._completer_model = QStringListModel(self)
        self._completer = QCompleter(self._completer_model, self)
        self._completer.setWidget(self)
        self._completer.setCompletionMode(QCompleter.CompletionMode.PopupCompletion)
        self._completer.setCaseSensitivity(Qt.CaseSensitivity.CaseSensitive)
        self._completer.activated.connect(self._insert_completion)
        self._completion_span = (0, 0)
        self._min_lines = 2

        font = QFontDatabase.systemFont(QFontDatabase.SystemFont.FixedFont)
        font.setPointSize(11)
        self.setFont(font)
        self.setTabStopDistance(self.fontMetrics().horizontalAdvance(" ") * 4)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.setLineWrapMode(QPlainTextEdit.LineWrapMode.NoWrap)

        self.blockCountChanged.connect(self._on_block_count_changed)
        self.updateRequest.connect(self._update_line_number_area)
        self.cursorPositionChanged.connect(self._highlight_current_line)
        self.textChanged.connect(self._update_auto_height)

        self.apply_palette(palette)
        self._on_block_count_changed(1)
        self._update_auto_height()

    def apply_palette(self, palette: ThemePalette) -> None:
        self._palette = palette
        self.setStyleSheet(
            f"""
            QPlainTextEdit {{
                background-color: {palette.bg_editor};
                color: {palette.text_primary};
                border: 1px solid {palette.border};
                border-radius: 6px;
                padding: 4px 6px;
                selection-background-color: {palette.accent};
            }}
            """
        )
        self._line_area.update()
        self._highlight_current_line()

    def line_number_area_width(self) -> int:
        digits = max(2, len(str(max(1, self.blockCount()))))
        return 14 + self.fontMetrics().horizontalAdvance("9") * digits

    def _on_block_count_changed(self, _new_count: int) -> None:
        self.setViewportMargins(self.line_number_area_width(), 0, 0, 0)
        self._update_auto_height()

    def _update_line_number_area(self, rect: QRect, dy: int) -> None:
        if dy:
            self._line_area.scroll(0, dy)
        else:
            self._line_area.update(0, rect.y(), self._line_area.width(), rect.height())
        if rect.contains(self.viewport().rect()):
            self.setViewportMargins(self.line_number_area_width(), 0, 0, 0)

    def _update_auto_height(self) -> None:
        lines = max(self._min_lines, self.document().blockCount())
        line_h = self.fontMetrics().lineSpacing()
        h_scroll = 14 if self.horizontalScrollBar().isVisible() else 0
        target_h = int(lines * line_h + 18 + h_scroll)
        if self.height() != target_h:
            self.setFixedHeight(target_h)

    def resizeEvent(self, event: QResizeEvent) -> None:
        super().resizeEvent(event)
        cr = self.contentsRect()
        self._line_area.setGeometry(
            QRect(cr.left(), cr.top(), self.line_number_area_width(), cr.height())
        )

    def paint_line_numbers(self, event: QPaintEvent) -> None:
        painter = QPainter(self._line_area)
        painter.fillRect(event.rect(), QColor(self._palette.bg_gutter))

        block = self.firstVisibleBlock()
        block_num = block.blockNumber()
        top = round(self.blockBoundingGeometry(block).translated(self.contentOffset()).top())
        bottom = top + round(self.blockBoundingRect(block).height())
        active_block = self.textCursor().blockNumber()

        while block.isValid() and top <= event.rect().bottom():
            if block.isVisible() and bottom >= event.rect().top():
                number = str(block_num + 1)
                color = (
                    QColor(self._palette.text_primary)
                    if block_num == active_block
                    else QColor(self._palette.text_muted)
                )
                painter.setPen(color)
                painter.drawText(
                    0,
                    top,
                    self._line_area.width() - 6,
                    self.fontMetrics().height(),
                    Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter,
                    number,
                )
            block = block.next()
            top = bottom
            bottom = top + round(self.blockBoundingRect(block).height())
            block_num += 1

    def _highlight_current_line(self) -> None:
        selections: list[QTextEdit.ExtraSelection] = []
        if self.hasFocus() and not self.isReadOnly():
            sel = QTextEdit.ExtraSelection()
            line_color = QColor(self._palette.bg_card_active)
            line_color.setAlpha(140)
            sel.format.setBackground(line_color)
            sel.format.setProperty(QTextFormat.Property.FullWidthSelection, True)
            sel.cursor = self.textCursor()
            sel.cursor.clearSelection()
            selections.append(sel)
        self.setExtraSelections(selections)
        self._line_area.update()

    def focusInEvent(self, event) -> None:
        super().focusInEvent(event)
        self._highlight_current_line()
        self.focused.emit()

    def focusOutEvent(self, event) -> None:
        super().focusOutEvent(event)
        self._highlight_current_line()
        self.focus_lost.emit()

    def show_completions(self, matches: list[str], cursor_start: int, cursor_end: int) -> None:
        if not matches or not self.hasFocus():
            self._completer.popup().hide()
            return
        self._completion_span = (cursor_start, cursor_end)
        self._completer_model.setStringList(matches)
        self._completer.setCompletionPrefix("")
        popup = self._completer.popup()
        popup.setCurrentIndex(self._completer_model.index(0, 0))
        cr = self.cursorRect()
        cr.setWidth(
            popup.sizeHintForColumn(0) + popup.verticalScrollBar().sizeHint().width() + 24
        )
        self._completer.complete(cr)

    def _insert_completion(self, completion: str) -> None:
        cursor = self.textCursor()
        start, end = self._completion_span
        cursor.setPosition(start)
        cursor.setPosition(end, QTextCursor.MoveMode.KeepAnchor)
        cursor.insertText(completion)
        self.setTextCursor(cursor)

    def _handle_popup_key(self, event: QKeyEvent) -> bool:
        popup = self._completer.popup()
        if not popup.isVisible():
            return False
        if event.key() in (Qt.Key.Key_Enter, Qt.Key.Key_Return, Qt.Key.Key_Tab):
            event.ignore()
            return True
        if event.key() == Qt.Key.Key_Escape:
            popup.hide()
            return True
        return False

    def _handle_enter_key(self, event: QKeyEvent, mods: Qt.KeyboardModifier) -> None:
        if mods & Qt.KeyboardModifier.ShiftModifier:
            self.run_requested.emit(True, False)
            return
        if mods & Qt.KeyboardModifier.ControlModifier:
            self.run_requested.emit(False, False)
            return
        if mods & Qt.KeyboardModifier.AltModifier:
            self.run_requested.emit(False, True)
            return

        cursor = self.textCursor()
        line_text = cursor.block().text()[: cursor.positionInBlock()]
        indent = line_text[: len(line_text) - len(line_text.lstrip(" "))]
        if line_text.rstrip().endswith(":"):
            indent += "    "
        super().keyPressEvent(event)
        self.insertPlainText(indent)

    def _handle_tab_key(self) -> bool:
        cursor = self.textCursor()
        if cursor.hasSelection():
            return False
        pos_in_line = cursor.positionInBlock()
        before = cursor.block().text()[:pos_in_line]
        if before and (before[-1].isalnum() or before[-1] in {"_", "."}):
            self.completion_requested.emit(self.toPlainText(), cursor.position())
            return True
        cursor.insertText("    ")
        return True

    def keyPressEvent(self, event: QKeyEvent) -> None:
        if self._handle_popup_key(event):
            return

        mods = event.modifiers()
        key = event.key()

        if key in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            self._handle_enter_key(event, mods)
            return
        if key == Qt.Key.Key_Escape:
            self.escape_pressed.emit()
            return
        if key == Qt.Key.Key_Space and (mods & Qt.KeyboardModifier.ControlModifier):
            self.completion_requested.emit(self.toPlainText(), self.textCursor().position())
            return
        if key == Qt.Key.Key_Tab and not mods and self._handle_tab_key():
            return
        if key == Qt.Key.Key_Backtab or (
            key == Qt.Key.Key_Tab and (mods & Qt.KeyboardModifier.ShiftModifier)
        ):
            self._dedent_selection()
            return

        super().keyPressEvent(event)

    def _dedent_selection(self) -> None:
        cursor = self.textCursor()
        cursor.beginEditBlock()
        start = cursor.selectionStart()
        end = cursor.selectionEnd()
        cursor.setPosition(start)
        first_block = cursor.blockNumber()
        cursor.setPosition(end)
        last_block = cursor.blockNumber()

        doc = self.document()
        for bnum in range(first_block, last_block + 1):
            block = doc.findBlockByNumber(bnum)
            text = block.text()
            remove = 0
            for ch in text[:4]:
                if ch == " ":
                    remove += 1
                else:
                    break
            if remove:
                c = QTextCursor(block)
                c.movePosition(QTextCursor.MoveOperation.Right, QTextCursor.MoveMode.KeepAnchor, remove)
                c.removeSelectedText()
        cursor.endEditBlock()
