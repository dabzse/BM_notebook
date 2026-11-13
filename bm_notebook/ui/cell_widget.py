"""Individual notebook cell card widget (Code & Markdown, reactive badges, warnings, outputs)."""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QMouseEvent
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSizePolicy,
    QTextBrowser,
    QVBoxLayout,
    QWidget,
)

from bm_notebook.i18n import t
from bm_notebook.model import Cell, CellOutput, CellState, CellType

from .code_editor import CodeEditor
from .highlighter import MarkdownSyntaxHighlighter, PythonSyntaxHighlighter
from .output_widget import CellOutputContainer
from .theme import ThemePalette


class _MarkdownPreview(QTextBrowser):
    """Rendered native Markdown view; double-click switches to edit mode."""

    double_clicked = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setOpenExternalLinks(True)
        self.setFrameShape(QTextBrowser.Shape.NoFrame)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.document().contentsChanged.connect(self._adjust_height)

    def _adjust_height(self) -> None:
        self.document().setTextWidth(max(240, self.viewport().width()))
        h = int(self.document().size().height()) + 14
        self.setFixedHeight(max(36, h))

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self._adjust_height()

    def mouseDoubleClickEvent(self, event: QMouseEvent) -> None:
        self.double_clicked.emit()
        super().mouseDoubleClickEvent(event)


class CellWidget(QFrame):
    """Native Qt card representing one Code or Markdown cell."""

    selected = Signal(str)
    source_changed = Signal(str, str)  # cell_id, new_source
    run_requested = Signal(str, bool, bool)  # cell_id, advance, insert_below
    delete_requested = Signal(str)
    move_requested = Signal(str, int)  # cell_id, delta (-1 / +1)
    type_toggle_requested = Signal(str)
    completion_requested = Signal(str, str, int)  # cell_id, code, cursor_pos

    def __init__(
        self,
        cell: Cell,
        index: int,
        palette: ThemePalette,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.cell_id = cell.id
        self._cell = cell
        self._index = index
        self._palette = palette
        self._is_active = False
        self._md_editing = cell.cell_type == CellType.MARKDOWN and not cell.source.strip()
        self._suppress_text_signal = False

        self.setObjectName("CellCard")
        self.setFrameShape(QFrame.Shape.StyledPanel)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum)

        root = QVBoxLayout(self)
        root.setContentsMargins(10, 8, 10, 8)
        root.setSpacing(6)
        root.addLayout(self._build_header(cell, index))
        self._build_body_widgets(root, cell, palette)

        self.sync_from_model(cell, index)
        self.apply_palette(palette)

    def _build_header(self, cell: Cell, index: int) -> QHBoxLayout:
        header = QHBoxLayout()
        header.setSpacing(6)

        self._index_lbl = QLabel(f"#{index + 1}")
        self._type_btn = QPushButton("PY" if cell.cell_type == CellType.CODE else "MD")
        self._type_btn.setFixedHeight(22)
        self._type_btn.setToolTip(t("tooltip_cell_type"))
        self._type_btn.clicked.connect(lambda: self.type_toggle_requested.emit(self.cell_id))

        self._exec_lbl = QLabel("[ ]")
        self._state_pill = QLabel("IDLE")
        self._deps_lbl = QLabel("")
        self._deps_lbl.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)

        self._run_btn = QPushButton("▶")
        self._run_btn.setFixedSize(26, 22)
        self._run_btn.setToolTip(t("tooltip_cell_run"))
        self._run_btn.clicked.connect(lambda: self.run_requested.emit(self.cell_id, False, False))

        self._up_btn = QPushButton("▲")
        self._up_btn.setFixedSize(24, 22)
        self._up_btn.setToolTip(t("tooltip_cell_up"))
        self._up_btn.clicked.connect(lambda: self.move_requested.emit(self.cell_id, -1))

        self._down_btn = QPushButton("▼")
        self._down_btn.setFixedSize(24, 22)
        self._down_btn.setToolTip(t("tooltip_cell_down"))
        self._down_btn.clicked.connect(lambda: self.move_requested.emit(self.cell_id, 1))

        self._collapse_btn = QPushButton("▾")
        self._collapse_btn.setFixedSize(24, 22)
        self._collapse_btn.setToolTip(t("tooltip_cell_collapse"))
        self._collapse_btn.clicked.connect(self._toggle_collapse)

        self._del_btn = QPushButton("✕")
        self._del_btn.setFixedSize(24, 22)
        self._del_btn.setToolTip(t("tooltip_cell_delete"))
        self._del_btn.clicked.connect(lambda: self.delete_requested.emit(self.cell_id))

        for w in (
            self._index_lbl,
            self._type_btn,
            self._exec_lbl,
            self._state_pill,
            self._deps_lbl,
            self._run_btn,
            self._up_btn,
            self._down_btn,
            self._collapse_btn,
            self._del_btn,
        ):
            header.addWidget(w)
        return header

    def _build_body_widgets(
        self,
        root: QVBoxLayout,
        cell: Cell,
        palette: ThemePalette,
    ) -> None:
        self._warning_lbl = QLabel("")
        self._warning_lbl.setWordWrap(True)
        self._warning_lbl.setVisible(False)
        root.addWidget(self._warning_lbl)

        self.editor = CodeEditor(palette, self)
        self._suppress_text_signal = True
        self.editor.setPlainText(cell.source)
        self._suppress_text_signal = False
        self.editor.textChanged.connect(self._on_editor_text_changed)
        self.editor.focused.connect(lambda: self.selected.emit(self.cell_id))
        self.editor.focus_lost.connect(self._on_editor_focus_lost)
        self.editor.escape_pressed.connect(self._on_escape)
        self.editor.run_requested.connect(self._on_editor_run)
        self.editor.completion_requested.connect(
            lambda code, pos: self.completion_requested.emit(self.cell_id, code, pos)
        )
        self._py_highlighter = PythonSyntaxHighlighter(self.editor.document(), palette)
        self._md_highlighter = MarkdownSyntaxHighlighter(self.editor.document(), palette)
        self._md_highlighter.setDocument(None)
        root.addWidget(self.editor)

        self._md_preview = _MarkdownPreview(self)
        self._md_preview.double_clicked.connect(self._enter_md_edit)
        root.addWidget(self._md_preview)

        self._output_box = CellOutputContainer(palette, self)
        self._output_box.set_outputs(cell.outputs)
        root.addWidget(self._output_box)

    def mousePressEvent(self, event: QMouseEvent) -> None:
        self.selected.emit(self.cell_id)
        super().mousePressEvent(event)

    def _on_editor_text_changed(self) -> None:
        if self._suppress_text_signal:
            return
        text = self.editor.toPlainText()
        if text == self._cell.source:
            return
        self._cell.source = text
        self.source_changed.emit(self.cell_id, text)

    def _on_editor_run(self, advance: bool, insert_below: bool) -> None:
        if self._cell.cell_type == CellType.MARKDOWN:
            self._md_editing = False
            self._sync_markdown_mode()
            if advance:
                self.run_requested.emit(self.cell_id, True, insert_below)
            return
        self.run_requested.emit(self.cell_id, advance, insert_below)

    def _on_editor_focus_lost(self) -> None:
        if self._cell.cell_type == CellType.MARKDOWN and self._cell.source.strip():
            self._md_editing = False
            self._sync_markdown_mode()

    def _on_escape(self) -> None:
        if self._cell.cell_type == CellType.MARKDOWN and self._cell.source.strip():
            self._md_editing = False
            self._sync_markdown_mode()
        self.editor.clearFocus()

    def _enter_md_edit(self) -> None:
        self._md_editing = True
        self._sync_markdown_mode()
        self.editor.setFocus()
        self.selected.emit(self.cell_id)

    def _toggle_collapse(self) -> None:
        self._cell.collapsed = not self._cell.collapsed
        self._collapse_btn.setText("▸" if self._cell.collapsed else "▾")
        self._output_box.setVisible(not self._cell.collapsed and bool(self._cell.outputs))

    def set_active(self, active: bool) -> None:
        if self._is_active != active:
            self._is_active = active
            self._update_card_border()

    def _sync_markdown_mode(self) -> None:
        is_md = self._cell.cell_type == CellType.MARKDOWN
        doc = self.editor.document()
        prev_suppress = self._suppress_text_signal
        self._suppress_text_signal = True
        try:
            if is_md:
                if self._py_highlighter.document() is not None:
                    self._py_highlighter.setDocument(None)
                if self._md_highlighter.document() is not doc:
                    self._md_highlighter.setDocument(doc)
                self._run_btn.setVisible(False)
                self._collapse_btn.setVisible(False)
                self._exec_lbl.setVisible(False)
                self._state_pill.setVisible(False)
                self._output_box.setVisible(False)
                show_editor = self._md_editing or not self._cell.source.strip()
                self.editor.setVisible(show_editor)
                self._md_preview.setVisible(not show_editor)
                if not show_editor:
                    self._md_preview.setMarkdown(self._cell.source)
            else:
                if self._md_highlighter.document() is not None:
                    self._md_highlighter.setDocument(None)
                if self._py_highlighter.document() is not doc:
                    self._py_highlighter.setDocument(doc)
                self._run_btn.setVisible(True)
                self._collapse_btn.setVisible(True)
                self._exec_lbl.setVisible(True)
                self._state_pill.setVisible(True)
                self.editor.setVisible(True)
                self._md_preview.setVisible(False)
                self._output_box.setVisible(not self._cell.collapsed and bool(self._cell.outputs))
        finally:
            self._suppress_text_signal = prev_suppress

    def sync_from_model(self, cell: Cell, index: int) -> None:
        self._cell = cell
        self._index = index
        self._index_lbl.setText(f"#{index + 1}")
        self._type_btn.setText("PY" if cell.cell_type == CellType.CODE else "MD")

        if self.editor.toPlainText() != cell.source:
            self._suppress_text_signal = True
            self.editor.setPlainText(cell.source)
            self._suppress_text_signal = False

        if cell.cell_type == CellType.CODE:
            if cell.state == CellState.RUNNING:
                self._exec_lbl.setText("[*]")
            elif cell.execution_count is not None:
                self._exec_lbl.setText(f"[{cell.execution_count}]")
            else:
                self._exec_lbl.setText("[ ]")

            self._update_state_pill()
            self._update_dep_chips()
            self._update_warnings()
        else:
            self._deps_lbl.setText("")
            self._warning_lbl.setVisible(False)

        self._collapse_btn.setText("▸" if cell.collapsed else "▾")
        self._sync_markdown_mode()
        self._update_card_border()

    def clear_outputs(self) -> None:
        self._cell.outputs.clear()
        self._output_box.clear()

    def append_output(self, out: CellOutput) -> None:
        self._cell.outputs.append(out)
        if not self._cell.collapsed:
            self._output_box.append_output(out)

    def _update_state_pill(self) -> None:
        p = self._palette
        st = self._cell.state
        if st == CellState.DONE:
            ms = f" • {self._cell.duration_ms:.0f}ms" if self._cell.duration_ms is not None else ""
            text, color = f"DONE{ms}", p.success
        elif st == CellState.RUNNING:
            text, color = "RUNNING", p.running
        elif st == CellState.QUEUED:
            text, color = "QUEUED", p.accent
        elif st == CellState.STALE:
            text, color = "STALE", p.stale
        elif st == CellState.ERROR:
            text, color = "ERROR", p.error
        elif st == CellState.CYCLE_ERROR:
            text, color = "CYCLE", p.error
        else:
            text, color = "IDLE", p.text_muted

        self._state_pill.setText(text)
        self._state_pill.setStyleSheet(
            f"color: {color}; border: 1px solid {color}; border-radius: 4px; "
            f"padding: 1px 6px; font-size: 11px; font-weight: 600;"
        )

    _MAX_CHIP_SYMBOLS = 5

    def _update_dep_chips(self) -> None:
        limit = self._MAX_CHIP_SYMBOLS
        parts: list[str] = []
        if self._cell.defs:
            defs_s = ", ".join(sorted(self._cell.defs)[:limit])
            if len(self._cell.defs) > limit:
                defs_s += f" (+{len(self._cell.defs) - limit})"
            parts.append(f"defs: {defs_s}")
        if self._cell.refs:
            refs_s = ", ".join(sorted(self._cell.refs)[:limit])
            if len(self._cell.refs) > limit:
                refs_s += f" (+{len(self._cell.refs) - limit})"
            parts.append(f"← {refs_s}")
        self._deps_lbl.setText("   |   ".join(parts))

    def retranslate_ui(self) -> None:
        self._type_btn.setToolTip(t("tooltip_cell_type"))
        self._run_btn.setToolTip(t("tooltip_cell_run"))
        self._up_btn.setToolTip(t("tooltip_cell_up"))
        self._down_btn.setToolTip(t("tooltip_cell_down"))
        self._collapse_btn.setToolTip(t("tooltip_cell_collapse"))
        self._del_btn.setToolTip(t("tooltip_cell_delete"))
        self._update_warnings()

    def _update_warnings(self) -> None:
        msgs: list[str] = []
        if self._cell.syntax_error:
            msgs.append(f"⚠ {self._cell.syntax_error}")
        if self._cell.cycle_info:
            msgs.append(f"⟲ {self._cell.cycle_info}")
        if self._cell.conflict_symbols:
            syms = ", ".join(sorted(self._cell.conflict_symbols))
            msgs.append(t("cell_conflict_warning", syms=syms))
        if msgs:
            self._warning_lbl.setText("\n".join(msgs))
            self._warning_lbl.setVisible(True)
        else:
            self._warning_lbl.setVisible(False)

    def _update_card_border(self) -> None:
        p = self._palette
        if self._cell.state in {CellState.ERROR, CellState.CYCLE_ERROR}:
            border_color = p.error
        elif self._cell.state == CellState.RUNNING:
            border_color = p.running
        elif self._is_active:
            border_color = p.border_active
        elif self._cell.state == CellState.STALE:
            border_color = p.stale
        else:
            border_color = p.border

        bg = p.bg_card_active if self._is_active else p.bg_card
        self.setStyleSheet(
            f"""
            QFrame#CellCard {{
                background-color: {bg};
                border: 1.5px solid {border_color};
                border-radius: 8px;
            }}
            """
        )

    def apply_palette(self, palette: ThemePalette) -> None:
        self._palette = palette
        prev_suppress = self._suppress_text_signal
        self._suppress_text_signal = True
        try:
            self.editor.apply_palette(palette)
            self._py_highlighter.set_palette(palette)
            self._md_highlighter.set_palette(palette)
        finally:
            self._suppress_text_signal = prev_suppress
        self._output_box.apply_palette(palette)

        self._index_lbl.setStyleSheet(
            f"color: {palette.text_muted}; font-weight: 700; font-size: 12px;"
        )
        self._exec_lbl.setStyleSheet(
            f"color: {palette.text_secondary}; font-family: monospace; font-size: 12px;"
        )
        self._deps_lbl.setStyleSheet(
            f"color: {palette.text_muted}; font-family: monospace; font-size: 11px;"
        )
        self._warning_lbl.setStyleSheet(
            f"background-color: {palette.bg_output}; color: {palette.warning}; "
            f"border: 1px solid {palette.warning}; border-radius: 5px; padding: 4px 8px; font-size: 12px;"
        )
        self._md_preview.setStyleSheet(
            f"background: transparent; color: {palette.text_primary}; font-size: 14px; padding: 4px;"
        )
        action_buttons = (
            self._type_btn,
            self._run_btn,
            self._up_btn,
            self._down_btn,
            self._collapse_btn,
            self._del_btn,
        )
        for btn in action_buttons:
            btn.setStyleSheet(
                f"""
                QPushButton {{
                    background-color: {palette.bg_surface};
                    color: {palette.text_secondary};
                    border: 1px solid {palette.border};
                    border-radius: 4px;
                    font-size: 11px;
                    padding: 1px 6px;
                }}
                QPushButton:hover {{
                    border-color: {palette.accent};
                    color: {palette.text_primary};
                }}
                """
            )
        self._update_state_pill()
        self._update_card_border()
