"""Main window orchestrating the native notebook canvas, reactive DAG engine, and Jupyter kernel."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import (
    QAction,
    QCloseEvent,
    QGuiApplication,
    QKeySequence,
    QMoveEvent,
    QResizeEvent,
    QShortcut,
)
from PySide6.QtWidgets import (
    QComboBox,
    QFileDialog,
    QLabel,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QSplitter,
    QStatusBar,
    QToolBar,
    QVBoxLayout,
    QWidget,
)

from bm_notebook.format_bm import load_notebook, save_ipynb, save_notebook
from bm_notebook.kernel import KernelBridge, KernelSpecInfo, discover_kernelspecs
from bm_notebook.kernel.manager import ExecutionTask
from bm_notebook.model import Cell, CellOutput, CellState, CellType, NotebookDocument
from bm_notebook.reactive import DependencyGraph
from bm_notebook.settings import (
    DEFAULT_WINDOW_HEIGHT,
    AppSettings,
    load_settings,
    resolve_settings_path,
    save_settings,
)

from .cell_widget import CellWidget
from .inspector_panel import InspectorPanel
from .theme import DARK_THEME, LIGHT_THEME, ThemePalette, build_stylesheet

_REACTIVE_ON_LABEL = "⚡ Reaktív: BE"
_REACTIVE_OFF_LABEL = "⚡ Reaktív: KI"
_EXT_IPYNB = ".ipynb"
_EXT_BM_MD = ".bm.md"
_EXT_MD = ".md"
_MIN_WINDOW_WIDTH = 1726
_MIN_WINDOW_HEIGHT = 720
_DEFAULT_WINDOW_HEIGHT = DEFAULT_WINDOW_HEIGHT
_SETTINGS_SAVE_DEBOUNCE_MS = 350
_SCREEN_ANCHOR_OFFSET = 40
_SPLITTER_PANE_COUNT = 2


class MainWindow(QMainWindow):
    """BM Notebook native Qt6 IDE main window."""

    def __init__(
        self,
        initial_file: str | None = None,
        settings_path: str | Path | None = None,
    ) -> None:
        super().__init__()
        self._settings_path: Path = resolve_settings_path(settings_path)
        self._settings: AppSettings = load_settings(self._settings_path)
        self._restoring_settings = True
        self._palette: ThemePalette = LIGHT_THEME if self._settings.theme == "light" else DARK_THEME
        self._save_settings_timer = QTimer(self)
        self._save_settings_timer.setSingleShot(True)
        self._save_settings_timer.setInterval(_SETTINGS_SAVE_DEBOUNCE_MS)
        self._save_settings_timer.timeout.connect(self._save_settings)
        self._doc = NotebookDocument(title="Untitled", kernel_name="python3", reactive_mode=True)
        self._doc.ensure_non_empty()
        self._graph = DependencyGraph()
        self._cell_widgets: dict[str, CellWidget] = {}
        self._active_cell_id: str | None = None
        self._modified = False
        self._kernelspecs: list[KernelSpecInfo] = discover_kernelspecs()
        self._last_vars: list[dict[str, str]] = []

        self._kernel = KernelBridge(self)
        self._kernel.kernel_started.connect(self._on_kernel_started)
        self._kernel.kernel_status.connect(self._on_kernel_status)
        self._kernel.kernel_error.connect(self._on_kernel_error)
        self._kernel.cell_started.connect(self._on_cell_started)
        self._kernel.cell_output.connect(self._on_cell_output)
        self._kernel.cell_finished.connect(self._on_cell_finished)
        self._kernel.batch_aborted.connect(self._on_batch_aborted)
        self._kernel.completions_ready.connect(self._on_completions_ready)
        self._kernel.variables_updated.connect(self._on_variables_updated)

        self._build_ui()
        self._apply_theme(self._palette)

        if initial_file:
            self.open_file(initial_file)
        else:
            self._rebuild_cells_ui()
            self._reanalyze_graph(mark_downstream_stale=False)
            self._start_selected_kernel()
        self._restoring_settings = False

    def _build_ui(self) -> None:
        self.setMinimumSize(_MIN_WINDOW_WIDTH, _MIN_WINDOW_HEIGHT)
        self._build_toolbar()
        self._build_central_splitter()
        self._build_statusbar()
        self._apply_saved_window_settings()
        self._update_window_title()

    def _build_toolbar(self) -> None:
        tb = QToolBar("Fő eszköztár", self)
        tb.setMovable(False)
        self.addToolBar(tb)

        self._new_act = QAction("Új", self)
        self._new_act.setShortcut(QKeySequence.StandardKey.New)
        self._new_act.triggered.connect(self.new_notebook)
        tb.addAction(self._new_act)

        self._open_act = QAction("Megnyitás", self)
        self._open_act.setShortcut(QKeySequence.StandardKey.Open)
        self._open_act.triggered.connect(self.open_dialog)
        tb.addAction(self._open_act)

        self._save_act = QAction("Mentés", self)
        self._save_act.setShortcut(QKeySequence.StandardKey.Save)
        self._save_act.triggered.connect(self.save_current)
        tb.addAction(self._save_act)

        self._export_act = QAction("Export .ipynb", self)
        self._export_act.triggered.connect(self.export_ipynb_dialog)
        tb.addAction(self._export_act)

        tb.addSeparator()

        add_py_btn = QPushButton("+ Python", self)
        add_py_btn.clicked.connect(lambda: self.insert_cell_near_active(CellType.CODE))
        tb.addWidget(add_py_btn)

        add_md_btn = QPushButton("+ Markdown", self)
        add_md_btn.clicked.connect(lambda: self.insert_cell_near_active(CellType.MARKDOWN))
        tb.addWidget(add_md_btn)

        tb.addSeparator()
        self._add_execution_toolbar_controls(tb)
        tb.addSeparator()
        self._add_view_toolbar_controls(tb)

    def _add_execution_toolbar_controls(self, tb: QToolBar) -> None:
        self._run_stale_btn = QPushButton("▶ Elavultak", self)
        self._run_stale_btn.setToolTip("Függőben lévő (STALE / IDLE) cellák futtatása topologikus sorrendben")
        self._run_stale_btn.clicked.connect(self.run_stale_cells)
        tb.addWidget(self._run_stale_btn)

        self._run_all_btn = QPushButton("▶▶ Mind futtatása", self)
        self._run_all_btn.setObjectName("PrimaryBtn")
        self._run_all_btn.setShortcut(QKeySequence("F5"))
        self._run_all_btn.setToolTip("Teljes notebook futtatása topologikus sorrendben (F5 / Ctrl+R)")
        self._run_all_btn.clicked.connect(self.run_all_cells)
        self._run_all_shortcut_alt = QShortcut(QKeySequence("Ctrl+R"), self)
        self._run_all_shortcut_alt.activated.connect(self.run_all_cells)
        tb.addWidget(self._run_all_btn)

        self._interrupt_btn = QPushButton("■ Megszakítás", self)
        self._interrupt_btn.setShortcut(QKeySequence("Ctrl+I"))
        self._interrupt_btn.clicked.connect(self._kernel.interrupt_kernel)
        tb.addWidget(self._interrupt_btn)

        self._restart_btn = QPushButton("↻ Újraindítás", self)
        self._restart_btn.clicked.connect(self.restart_and_run_prompt)
        tb.addWidget(self._restart_btn)

    def _add_view_toolbar_controls(self, tb: QToolBar) -> None:
        self._reactive_btn = QPushButton(_REACTIVE_ON_LABEL, self)
        self._reactive_btn.setCheckable(True)
        self._reactive_btn.setChecked(True)
        self._reactive_btn.setToolTip("Automatikus függőségi kaszkád cella futtatáskor")
        self._reactive_btn.toggled.connect(self._on_reactive_toggled)
        tb.addWidget(self._reactive_btn)

        self._toolbar_spacer = QWidget(self)
        self._toolbar_spacer.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        tb.addWidget(self._toolbar_spacer)

        tb.addWidget(QLabel("Kernel: ", self))
        self._kernel_combo = QComboBox(self)
        for spec in self._kernelspecs:
            self._kernel_combo.addItem(f"{spec.display_name} ({spec.name})", spec)
        self._kernel_combo.currentIndexChanged.connect(self._on_kernel_combo_changed)
        tb.addWidget(self._kernel_combo)

        self._inspector_btn = QPushButton("Gráf / Változók", self)
        self._inspector_btn.setCheckable(True)
        self._inspector_btn.setChecked(True)
        self._inspector_btn.setShortcut(QKeySequence("Ctrl+B"))
        self._inspector_btn.toggled.connect(self._toggle_inspector)
        tb.addWidget(self._inspector_btn)

        self._theme_btn = QPushButton("☀/🌙 Téma", self)
        self._theme_btn.clicked.connect(self._toggle_theme)
        tb.addWidget(self._theme_btn)

    def _build_central_splitter(self) -> None:
        self._splitter = QSplitter(Qt.Orientation.Horizontal, self)
        self.setCentralWidget(self._splitter)

        self._scroll = QScrollArea(self)
        self._scroll.setWidgetResizable(True)
        self._scroll.setFrameShape(QScrollArea.Shape.NoFrame)

        self._canvas = QWidget(self)
        self._canvas.setObjectName("MainCanvas")
        self._cells_layout = QVBoxLayout(self._canvas)
        self._cells_layout.setContentsMargins(24, 18, 24, 48)
        self._cells_layout.setSpacing(12)
        self._cells_layout.addStretch(1)

        self._scroll.setWidget(self._canvas)
        self._splitter.addWidget(self._scroll)

        self._inspector = InspectorPanel(self._palette, self)
        self._inspector.cell_selected.connect(self._focus_cell_from_inspector)
        self._splitter.addWidget(self._inspector)
        self._splitter.setSizes(self._settings.splitter_sizes)
        self._splitter.splitterMoved.connect(self._on_splitter_moved)

    def _build_statusbar(self) -> None:
        sb = QStatusBar(self)
        self.setStatusBar(sb)
        self._status_kernel_lbl = QLabel("Kernel: indítás…", self)
        self._status_info_lbl = QLabel("", self)
        sb.addWidget(self._status_kernel_lbl)
        sb.addPermanentWidget(self._status_info_lbl)

    def _is_position_on_screen(self, x: int, y: int) -> bool:
        screens = QGuiApplication.screens()
        if not screens:
            return False
        return any(
            screen.availableGeometry().contains(x + _SCREEN_ANCHOR_OFFSET, y + _SCREEN_ANCHOR_OFFSET)
            for screen in screens
        )

    def _apply_saved_window_settings(self) -> None:
        width = max(self._settings.window_width, _MIN_WINDOW_WIDTH)
        height = max(self._settings.window_height, _MIN_WINDOW_HEIGHT)
        self.resize(width, height)
        if (
            self._settings.window_x is not None
            and self._settings.window_y is not None
            and self._is_position_on_screen(self._settings.window_x, self._settings.window_y)
        ):
            self.move(self._settings.window_x, self._settings.window_y)
        if self._settings.window_maximized:
            self.setWindowState(self.windowState() | Qt.WindowState.WindowMaximized)

        visible = self._settings.inspector_visible
        self._inspector_btn.setChecked(visible)
        self._inspector.setVisible(visible)

    def _capture_settings(self) -> None:
        maximized = self.isMaximized()
        self._settings.window_maximized = maximized
        if maximized:
            normal_rect = self.normalGeometry()
            if normal_rect.width() >= _MIN_WINDOW_WIDTH and normal_rect.height() >= _MIN_WINDOW_HEIGHT:
                self._settings.window_width = normal_rect.width()
                self._settings.window_height = normal_rect.height()
                self._settings.window_x = normal_rect.x()
                self._settings.window_y = normal_rect.y()
        else:
            self._settings.window_width = max(self.width(), _MIN_WINDOW_WIDTH)
            self._settings.window_height = max(self.height(), _MIN_WINDOW_HEIGHT)
            self._settings.window_x = self.x()
            self._settings.window_y = self.y()

        sizes = self._splitter.sizes()
        if len(sizes) == _SPLITTER_PANE_COUNT and all(s > 0 for s in sizes):
            self._settings.splitter_sizes = sizes
        self._settings.inspector_visible = self._inspector_btn.isChecked()
        self._settings.theme = self._palette.name

    def _schedule_settings_save(self) -> None:
        if not self._restoring_settings:
            self._save_settings_timer.start()

    def _save_settings(self) -> None:
        self._capture_settings()
        save_settings(self._settings, self._settings_path)

    def _on_splitter_moved(self, _pos: int, _index: int) -> None:
        self._schedule_settings_save()

    def resizeEvent(self, event: QResizeEvent) -> None:
        super().resizeEvent(event)
        self._schedule_settings_save()

    def moveEvent(self, event: QMoveEvent) -> None:
        super().moveEvent(event)
        self._schedule_settings_save()

    def _apply_theme(self, palette: ThemePalette) -> None:
        self._palette = palette
        self.setStyleSheet(build_stylesheet(palette))
        self._inspector.apply_palette(palette)
        for cw in self._cell_widgets.values():
            cw.apply_palette(palette)

    def _toggle_theme(self) -> None:
        new_theme = LIGHT_THEME if self._palette.name == "dark" else DARK_THEME
        self._apply_theme(new_theme)
        self._schedule_settings_save()

    def _toggle_inspector(self, visible: bool) -> None:
        self._inspector.setVisible(visible)
        self._schedule_settings_save()

    def _update_window_title(self) -> None:
        name = Path(self._doc.file_path).name if self._doc.file_path else self._doc.title
        star = " *" if self._modified else ""
        self.setWindowTitle(f"{name}{star} — BM::Notebook")

    def _select_kernel_in_combo(self, kernel_name: str) -> None:
        self._kernel_combo.blockSignals(True)
        for idx in range(self._kernel_combo.count()):
            spec: KernelSpecInfo = self._kernel_combo.itemData(idx)
            if spec and spec.name == kernel_name:
                self._kernel_combo.setCurrentIndex(idx)
                break
        self._kernel_combo.blockSignals(False)

    def _current_kernelspec(self) -> KernelSpecInfo:
        spec = self._kernel_combo.currentData()
        if isinstance(spec, KernelSpecInfo):
            return spec
        return KernelSpecInfo(name="python3", display_name="Python 3", language="python")

    def _start_selected_kernel(self) -> None:
        spec = self._current_kernelspec()
        self._doc.kernel_name = spec.name
        self._kernel.start_kernel(spec.name, spec.language)

    def _on_kernel_combo_changed(self, _idx: int) -> None:
        spec = self._current_kernelspec()
        if spec.name != self._kernel.kernel_name:
            self._doc.kernel_name = spec.name
            self._kernel.start_kernel(spec.name, spec.language)

    def _on_reactive_toggled(self, checked: bool) -> None:
        self._doc.reactive_mode = checked
        self._reactive_btn.setText(_REACTIVE_ON_LABEL if checked else _REACTIVE_OFF_LABEL)
        self._modified = True
        self._update_window_title()
        self._update_status_summary()

    def _rebuild_cells_ui(self) -> None:
        # Clear existing widgets (keep trailing stretch at index count-1)
        for cw in self._cell_widgets.values():
            self._cells_layout.removeWidget(cw)
            cw.deleteLater()
        self._cell_widgets.clear()

        for idx, cell in enumerate(self._doc.cells):
            cw = self._create_cell_widget(cell, idx)
            self._cells_layout.insertWidget(idx, cw)

        if self._doc.cells:
            self._set_active_cell(self._doc.cells[0].id)

    def _create_cell_widget(self, cell: Cell, index: int) -> CellWidget:
        cw = CellWidget(cell, index, self._palette, self._canvas)
        cw.selected.connect(self._set_active_cell)
        cw.source_changed.connect(self._on_cell_source_changed)
        cw.run_requested.connect(self.run_cell)
        cw.delete_requested.connect(self.delete_cell)
        cw.move_requested.connect(self.move_cell)
        cw.type_toggle_requested.connect(self.toggle_cell_type)
        cw.completion_requested.connect(self._kernel.request_completions)
        self._cell_widgets[cell.id] = cw
        return cw

    def _set_active_cell(self, cell_id: str) -> None:
        self._active_cell_id = cell_id
        for cid, cw in self._cell_widgets.items():
            cw.set_active(cid == cell_id)

    def _focus_cell_from_inspector(self, cell_id: str) -> None:
        self._set_active_cell(cell_id)
        cw = self._cell_widgets.get(cell_id)
        if cw is not None:
            self._scroll.ensureWidgetVisible(cw, 20, 40)
            cw.editor.setFocus()

    def _reanalyze_graph(
        self,
        edited_cell_id: str | None = None,
        mark_downstream_stale: bool = True,
    ) -> None:
        is_python = self._current_kernelspec().language.lower() == "python"
        self._graph = DependencyGraph.build(self._doc.cells, analyze=is_python)

        downstream: set[str] = set()
        if edited_cell_id and mark_downstream_stale and is_python:
            downstream = self._graph.downstream_cells([edited_cell_id])

        for idx, cell in enumerate(self._doc.cells):
            if cell.cell_type == CellType.CODE:
                if cell.id in self._graph.cycle_cells:
                    cell.state = CellState.CYCLE_ERROR
                elif (cell.id == edited_cell_id or cell.id in downstream) and cell.state == CellState.DONE:
                    cell.state = CellState.STALE
                elif cell.state == CellState.CYCLE_ERROR and cell.id not in self._graph.cycle_cells:
                    cell.state = CellState.IDLE

            cw = self._cell_widgets.get(cell.id)
            if cw is not None:
                cw.sync_from_model(cell, idx)

        self._inspector.refresh_graph(self._doc.cells, self._graph)
        self._inspector.update_variables(self._last_vars, self._doc.cells, self._graph)
        self._update_status_summary()

    def _update_status_summary(self) -> None:
        total = len(self._doc.cells)
        code_n = sum(1 for c in self._doc.cells if c.cell_type == CellType.CODE)
        stale_n = sum(1 for c in self._doc.cells if c.state == CellState.STALE)
        mode = "Reaktív DAG" if self._doc.reactive_mode else "Manuális"
        extras: list[str] = []
        if stale_n:
            extras.append(f"{stale_n} elavult")
        if self._graph.conflicts:
            extras.append(f"{len(self._graph.conflicts)} névütközés")
        if self._graph.cycles:
            extras.append(f"{len(self._graph.cycles)} ciklus")
        ext_txt = f" | ⚠ {', '.join(extras)}" if extras else ""
        self._status_info_lbl.setText(f"{mode} • {code_n}/{total} kód cella{ext_txt}")

    def _on_cell_source_changed(self, cell_id: str, _new_source: str) -> None:
        self._modified = True
        self._update_window_title()
        self._reanalyze_graph(edited_cell_id=cell_id, mark_downstream_stale=True)

    def insert_cell_near_active(self, cell_type: CellType) -> Cell:
        idx = self._doc.index_of(self._active_cell_id) if self._active_cell_id else -1
        insert_at = idx + 1 if idx >= 0 else len(self._doc.cells)
        cell = self._doc.insert_cell(insert_at, cell_type=cell_type, source="")
        cw = self._create_cell_widget(cell, insert_at)
        self._cells_layout.insertWidget(insert_at, cw)
        self._modified = True
        self._update_window_title()
        self._reanalyze_graph(mark_downstream_stale=False)
        self._set_active_cell(cell.id)
        cw.editor.setFocus()
        QTimer.singleShot(20, lambda: self._scroll.ensureWidgetVisible(cw, 20, 40))
        return cell

    def delete_cell(self, cell_id: str) -> None:
        cell = self._doc.get_cell(cell_id)
        if cell is None:
            return
        if len(self._doc.cells) == 1:
            cell.source = ""
            cell.outputs.clear()
            cell.state = CellState.IDLE
            cell.execution_count = None
            self._reanalyze_graph(mark_downstream_stale=False)
            return

        idx = self._doc.index_of(cell_id)
        self._doc.remove_cell(cell_id)
        cw = self._cell_widgets.pop(cell_id, None)
        if cw is not None:
            self._cells_layout.removeWidget(cw)
            cw.deleteLater()
        self._modified = True
        self._update_window_title()
        self._reanalyze_graph(mark_downstream_stale=False)
        next_idx = min(idx, len(self._doc.cells) - 1)
        if next_idx >= 0:
            self._set_active_cell(self._doc.cells[next_idx].id)

    def move_cell(self, cell_id: str, delta: int) -> None:
        if not self._doc.move_cell(cell_id, delta):
            return
        cw = self._cell_widgets.get(cell_id)
        new_idx = self._doc.index_of(cell_id)
        if cw is not None and new_idx >= 0:
            self._cells_layout.removeWidget(cw)
            self._cells_layout.insertWidget(new_idx, cw)
        self._modified = True
        self._update_window_title()
        self._reanalyze_graph(mark_downstream_stale=False)

    def toggle_cell_type(self, cell_id: str) -> None:
        cell = self._doc.get_cell(cell_id)
        if cell is None:
            return
        if cell.cell_type == CellType.CODE:
            cell.cell_type = CellType.MARKDOWN
            cell.outputs.clear()
            cell.defs.clear()
            cell.refs.clear()
            cell.syntax_error = None
            cell.state = CellState.IDLE
        else:
            cell.cell_type = CellType.CODE
            cell.state = CellState.IDLE
        self._modified = True
        self._update_window_title()
        self._reanalyze_graph(mark_downstream_stale=False)

    def _enqueue_plan(self, cell_ids: list[str]) -> None:
        tasks: list[ExecutionTask] = []
        for cid in cell_ids:
            cell = self._doc.get_cell(cid)
            if cell is None or cell.cell_type != CellType.CODE:
                continue
            cell.state = CellState.QUEUED
            cell.outputs.clear()
            cw = self._cell_widgets.get(cid)
            if cw is not None:
                cw.clear_outputs()
                cw.sync_from_model(cell, self._doc.index_of(cid))
            removed = sorted(cell.last_executed_defs - cell.defs)
            tasks.append(ExecutionTask(cell_id=cid, code=cell.source, removed_defs=removed))
        if tasks:
            self._kernel.execute_batch(tasks)

    def run_cell(self, cell_id: str, advance: bool = False, insert_below: bool = False) -> None:
        self._reanalyze_graph(mark_downstream_stale=False)
        is_python = self._current_kernelspec().language.lower() == "python"
        cascade = self._doc.reactive_mode and is_python
        plan = self._graph.execution_plan([cell_id], cascade=cascade)

        if plan.blocked_by_cycle and cell_id in plan.blocked_by_cycle:
            QMessageBox.warning(
                self,
                "Függőségi ciklus",
                "A cella kölcsönös (ciklikus) változó-függőségben van más cellákkal. "
                "Szüntesd meg a ciklust a reaktív futtatáshoz.",
            )
            return

        self._enqueue_plan(plan.order)

        if insert_below:
            idx = self._doc.index_of(cell_id)
            new_c = self._doc.insert_cell(idx + 1, cell_type=CellType.CODE, source="")
            cw = self._create_cell_widget(new_c, idx + 1)
            self._cells_layout.insertWidget(idx + 1, cw)
            self._reanalyze_graph(mark_downstream_stale=False)
            self._set_active_cell(new_c.id)
            cw.editor.setFocus()
        elif advance:
            idx = self._doc.index_of(cell_id)
            if idx + 1 < len(self._doc.cells):
                nxt = self._doc.cells[idx + 1]
                self._set_active_cell(nxt.id)
                nxt_w = self._cell_widgets.get(nxt.id)
                if nxt_w is not None:
                    self._scroll.ensureWidgetVisible(nxt_w, 20, 40)
                    if nxt.cell_type == CellType.CODE:
                        nxt_w.editor.setFocus()

    def run_stale_cells(self) -> None:
        self._reanalyze_graph(mark_downstream_stale=False)
        stale_roots = [
            c.id
            for c in self._doc.cells
            if c.cell_type == CellType.CODE and c.state in {CellState.STALE, CellState.IDLE}
        ]
        if not stale_roots:
            return
        plan = self._graph.execution_plan(stale_roots, cascade=True)
        self._enqueue_plan(plan.order)

    def run_all_cells(self) -> None:
        self._reanalyze_graph(mark_downstream_stale=False)
        plan = self._graph.run_all_plan()
        if plan.blocked_by_cycle:
            QMessageBox.warning(
                self,
                "Függőségi ciklus észlelve",
                "Néhány cella függőségi ciklusban van, ezek kihagyásra kerülnek.",
            )
        self._enqueue_plan(plan.order)

    def restart_and_run_prompt(self) -> None:
        for cell in self._doc.cells:
            if cell.cell_type == CellType.CODE:
                cell.state = CellState.IDLE
                cell.execution_count = None
                cell.last_executed_defs.clear()
        self._last_vars = []
        self._reanalyze_graph(mark_downstream_stale=False)
        self._kernel.restart_kernel()

    # --- Kernel signal handlers ---

    def _on_kernel_started(self, kname: str, _lang: str) -> None:
        self._status_kernel_lbl.setText(f"Kernel: {kname} • Kész")

    def _on_kernel_status(self, status: str) -> None:
        labels = {
            "starting": "Indítás…",
            "idle": "Kész (Idle)",
            "busy": "Fut (Busy)",
            "dead": "Leállt",
        }
        self._status_kernel_lbl.setText(f"Kernel: {self._kernel.kernel_name} • {labels.get(status, status)}")

    def _on_kernel_error(self, message: str) -> None:
        self._status_kernel_lbl.setText(f"Kernel hiba: {message}")

    def _on_cell_started(self, cell_id: str) -> None:
        cell = self._doc.get_cell(cell_id)
        if cell is None:
            return
        cell.state = CellState.RUNNING
        cw = self._cell_widgets.get(cell_id)
        if cw is not None:
            cw.sync_from_model(cell, self._doc.index_of(cell_id))
        self._inspector.refresh_graph(self._doc.cells, self._graph)

    def _on_cell_output(self, cell_id: str, output: CellOutput) -> None:
        cw = self._cell_widgets.get(cell_id)
        if cw is not None:
            cw.append_output(output)
        else:
            cell = self._doc.get_cell(cell_id)
            if cell is not None:
                cell.outputs.append(output)

    def _on_cell_finished(
        self,
        cell_id: str,
        ok: bool,
        exec_count: object,
        duration_ms: float,
        error_msg: object,
    ) -> None:
        cell = self._doc.get_cell(cell_id)
        if cell is None:
            return
        cell.state = CellState.DONE if ok else CellState.ERROR
        cell.duration_ms = duration_ms
        if isinstance(exec_count, int):
            cell.execution_count = exec_count
        cell.error_message = str(error_msg) if error_msg else None
        if ok:
            cell.last_executed_defs = set(cell.defs)

        cw = self._cell_widgets.get(cell_id)
        if cw is not None:
            cw.sync_from_model(cell, self._doc.index_of(cell_id))
        self._inspector.refresh_graph(self._doc.cells, self._graph)
        self._update_status_summary()

    def _on_batch_aborted(self, remaining_ids: list[str]) -> None:
        for cid in remaining_ids:
            cell = self._doc.get_cell(cid)
            if cell is not None and cell.state == CellState.QUEUED:
                cell.state = CellState.STALE
                cw = self._cell_widgets.get(cid)
                if cw is not None:
                    cw.sync_from_model(cell, self._doc.index_of(cid))
        self._inspector.refresh_graph(self._doc.cells, self._graph)
        self._update_status_summary()

    def _on_completions_ready(
        self,
        cell_id: str,
        _req_pos: int,
        matches: list[str],
        cstart: int,
        cend: int,
    ) -> None:
        cw = self._cell_widgets.get(cell_id)
        if cw is not None:
            cw.editor.show_completions(matches, cstart, cend)

    def _on_variables_updated(self, variables: list[dict[str, str]]) -> None:
        self._last_vars = variables
        self._inspector.update_variables(variables, self._doc.cells, self._graph)

    # --- File operations ---

    def new_notebook(self) -> None:
        self._doc = NotebookDocument(
            title="Untitled",
            kernel_name=self._current_kernelspec().name,
            reactive_mode=self._reactive_btn.isChecked(),
        )
        self._doc.ensure_non_empty()
        self._modified = False
        self._last_vars = []
        self._rebuild_cells_ui()
        self._reanalyze_graph(mark_downstream_stale=False)
        self._update_window_title()
        self._kernel.restart_kernel()

    def open_dialog(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Notebook megnyitása",
            str(Path.cwd()),
            "BM & Jupyter Notebooks (*.bm.md *.md *.ipynb);;Minden fájl (*)",
        )
        if path:
            self.open_file(path)

    def open_file(self, path: str) -> None:
        try:
            doc = load_notebook(path)
        except Exception as exc:
            QMessageBox.critical(self, "Megnyitási hiba", f"Nem sikerült megnyitni:\n{exc}")
            return

        self._doc = doc
        self._modified = False
        self._last_vars = []
        self._reactive_btn.blockSignals(True)
        self._reactive_btn.setChecked(doc.reactive_mode)
        self._reactive_btn.setText(_REACTIVE_ON_LABEL if doc.reactive_mode else _REACTIVE_OFF_LABEL)
        self._reactive_btn.blockSignals(False)

        self._select_kernel_in_combo(doc.kernel_name)
        self._rebuild_cells_ui()
        self._reanalyze_graph(mark_downstream_stale=False)
        self._update_window_title()
        self._start_selected_kernel()

    def save_current(self) -> None:
        if not self._doc.file_path:
            self.save_as_dialog()
            return
        try:
            save_notebook(self._doc, self._doc.file_path)
            self._modified = False
            self._update_window_title()
        except Exception as exc:
            QMessageBox.critical(self, "Mentési hiba", f"Nem sikerült menteni:\n{exc}")

    def save_as_dialog(self) -> None:
        default_name = f"{self._doc.title}{_EXT_BM_MD}"
        path, _ = QFileDialog.getSaveFileName(
            self,
            "Notebook mentése",
            str(Path.cwd() / default_name),
            f"BM Markdown Notebook (*{_EXT_BM_MD});;Jupyter Notebook (*{_EXT_IPYNB})",
        )
        if not path:
            return
        if not path.endswith((_EXT_BM_MD, _EXT_MD, _EXT_IPYNB)):
            path += _EXT_BM_MD
        try:
            save_notebook(self._doc, path)
            self._modified = False
            self._update_window_title()
        except Exception as exc:
            QMessageBox.critical(self, "Mentési hiba", f"Nem sikerült menteni:\n{exc}")

    def export_ipynb_dialog(self) -> None:
        stem = Path(self._doc.file_path).stem.removesuffix(".bm") if self._doc.file_path else self._doc.title
        path, _ = QFileDialog.getSaveFileName(
            self,
            f"Exportálás Jupyter ({_EXT_IPYNB}) formátumba",
            str(Path.cwd() / f"{stem}{_EXT_IPYNB}"),
            f"Jupyter Notebook (*{_EXT_IPYNB})",
        )
        if not path:
            return
        if not path.endswith(_EXT_IPYNB):
            path += _EXT_IPYNB
        try:
            save_ipynb(self._doc, path)
        except Exception as exc:
            QMessageBox.critical(self, "Export hiba", f"Nem sikerült exportálni:\n{exc}")

    def closeEvent(self, event: QCloseEvent) -> None:
        self._save_settings_timer.stop()
        self._save_settings()
        self._kernel.shutdown()
        super().closeEvent(event)
