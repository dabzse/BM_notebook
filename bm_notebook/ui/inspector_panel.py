"""Native Reactive DAG Graph Visualizer and Live Kernel Variable Explorer."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from PySide6.QtCore import QPointF, QRectF, Qt, Signal
from PySide6.QtGui import QBrush, QColor, QFont, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import (
    QGraphicsPathItem,
    QGraphicsRectItem,
    QGraphicsScene,
    QGraphicsSceneMouseEvent,
    QGraphicsSimpleTextItem,
    QGraphicsView,
    QHeaderView,
    QLabel,
    QTableWidget,
    QTableWidgetItem,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from bm_notebook.i18n import t
from bm_notebook.model import Cell, CellState, CellType
from bm_notebook.reactive import DependencyGraph

from .theme import ThemePalette

_MAX_EDGE_SYMS = 2
_MAX_NODE_DEFS = 3


@dataclass(frozen=True)
class _DagNodeSpec:
    cell_id: str
    rect: QRectF
    title: str
    subtitle: str
    border_color: str


_MAX_EDGE_SYMS = 2
_MAX_NODE_DEFS = 3


@dataclass(frozen=True)
class _DagNodeSpec:
    cell_id: str
    rect: QRectF
    title: str
    subtitle: str
    border_color: str


class _DagNodeItem(QGraphicsRectItem):
    """Clickable node representing one code cell in the Reactive DAG."""

    def __init__(
        self,
        spec: _DagNodeSpec,
        palette: ThemePalette,
        on_click: Callable[[str], None],
    ) -> None:
        super().__init__(spec.rect)
        self._cell_id = spec.cell_id
        self._on_click = on_click
        self.setBrush(QBrush(QColor(palette.bg_card)))
        self.setPen(QPen(QColor(spec.border_color), 1.8))
        self.setCursor(Qt.CursorShape.PointingHandCursor)

        t_item = QGraphicsSimpleTextItem(spec.title, self)
        t_font = QFont()
        t_font.setPointSize(9)
        t_font.setBold(True)
        t_item.setFont(t_font)
        t_item.setBrush(QBrush(QColor(palette.text_primary)))
        t_item.setPos(spec.rect.x() + 10, spec.rect.y() + 6)

        s_item = QGraphicsSimpleTextItem(spec.subtitle, self)
        s_font = QFont()
        s_font.setPointSize(8)
        s_item.setFont(s_font)
        s_item.setBrush(QBrush(QColor(palette.text_muted)))
        s_item.setPos(spec.rect.x() + 10, spec.rect.y() + 24)

    def mousePressEvent(self, event: QGraphicsSceneMouseEvent) -> None:
        self._on_click(self._cell_id)
        super().mousePressEvent(event)


class DagView(QGraphicsView):
    """Interactive native QGraphicsView rendering the reactive cell DAG."""

    cell_clicked = Signal(str)

    def __init__(self, palette: ThemePalette, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._palette = palette
        self._scene = QGraphicsScene(self)
        self.setScene(self._scene)
        self.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        self.setDragMode(QGraphicsView.DragMode.ScrollHandDrag)
        self.apply_palette(palette)

    def apply_palette(self, palette: ThemePalette) -> None:
        self._palette = palette
        self._scene.setBackgroundBrush(QBrush(QColor(palette.bg_surface)))
        self.setStyleSheet(f"border: none; background-color: {palette.bg_surface};")

    @staticmethod
    def _compute_depths(code_cells: list[Cell], graph: DependencyGraph) -> dict[str, int]:
        depth: dict[str, int] = dict.fromkeys((c.id for c in code_cells), 0)
        for _ in range(len(code_cells)):
            changed = False
            for u, targets in graph.edges.items():
                for v in targets:
                    if (
                        v in depth
                        and u in depth
                        and v not in graph.cycle_cells
                        and depth[v] < depth[u] + 1
                    ):
                        depth[v] = depth[u] + 1
                        changed = True
            if not changed:
                break
        return depth

    @staticmethod
    def _layout_nodes(code_cells: list[Cell], depth: dict[str, int]) -> dict[str, QRectF]:
        columns: dict[int, list[Cell]] = {}
        for cell in code_cells:
            columns.setdefault(depth.get(cell.id, 0), []).append(cell)

        node_w, node_h = 178, 46
        x_gap, y_gap = 48, 20
        positions: dict[str, QRectF] = {}
        for col_idx, col_cells in sorted(columns.items()):
            x = 16 + col_idx * (node_w + x_gap)
            for row_idx, cell in enumerate(col_cells):
                y = 16 + row_idx * (node_h + y_gap)
                positions[cell.id] = QRectF(x, y, node_w, node_h)
        return positions

    def _draw_edges(self, positions: dict[str, QRectF], graph: DependencyGraph) -> None:
        p = self._palette
        for (u, v), syms in graph.edge_symbols.items():
            if u not in positions or v not in positions:
                continue
            r1, r2 = positions[u], positions[v]
            is_cycle = u in graph.cycle_cells and v in graph.cycle_cells
            edge_color = p.error if is_cycle else p.accent

            start = QPointF(r1.right(), r1.center().y())
            end = QPointF(r2.left(), r2.center().y())
            dx = max(28.0, abs(end.x() - start.x()) * 0.5)
            path = QPainterPath(start)
            path.cubicTo(
                QPointF(start.x() + dx, start.y()),
                QPointF(end.x() - dx, end.y()),
                end,
            )
            item = QGraphicsPathItem(path)
            item.setPen(QPen(QColor(edge_color), 1.5))
            self._scene.addItem(item)

            label_text = ", ".join(sorted(syms)[:_MAX_EDGE_SYMS])
            if len(syms) > _MAX_EDGE_SYMS:
                label_text += "…"
            lbl = QGraphicsSimpleTextItem(label_text)
            l_font = QFont()
            l_font.setPointSize(7)
            lbl.setFont(l_font)
            lbl.setBrush(QBrush(QColor(p.text_secondary)))
            mid = path.pointAtPercent(0.5)
            lbl.setPos(mid.x() - 14, mid.y() - 12)
            self._scene.addItem(lbl)

    def _border_color_for_state(self, state: CellState) -> str:
        p = self._palette
        mapping = {
            CellState.DONE: p.success,
            CellState.ERROR: p.error,
            CellState.CYCLE_ERROR: p.error,
            CellState.STALE: p.stale,
            CellState.RUNNING: p.running,
        }
        return mapping.get(state, p.border)

    def _draw_nodes(
        self,
        cells: list[Cell],
        code_cells: list[Cell],
        positions: dict[str, QRectF],
    ) -> None:
        cell_num_map = {c.id: idx + 1 for idx, c in enumerate(cells)}
        for cell in code_cells:
            defs_preview = ", ".join(sorted(cell.defs)[:_MAX_NODE_DEFS]) or "(no defs)"
            if len(cell.defs) > _MAX_NODE_DEFS:
                defs_preview += "…"
            node_idx = cell_num_map.get(cell.id, 0)
            node_title = f"{t('dag_node_title', index=node_idx)} [{cell.state.value.upper()}]"
            spec = _DagNodeSpec(
                cell_id=cell.id,
                rect=positions[cell.id],
                title=node_title,
                subtitle=defs_preview,
                border_color=self._border_color_for_state(cell.state),
            )
            self._scene.addItem(_DagNodeItem(spec, self._palette, self.cell_clicked.emit))

    def update_graph(self, cells: list[Cell], graph: DependencyGraph) -> None:
        self._scene.clear()
        code_cells = [c for c in cells if c.cell_type == CellType.CODE]
        if not code_cells:
            return
        depth = self._compute_depths(code_cells, graph)
        positions = self._layout_nodes(code_cells, depth)
        self._draw_edges(positions, graph)
        self._draw_nodes(cells, code_cells, positions)
        self._scene.setSceneRect(self._scene.itemsBoundingRect().adjusted(-16, -16, 16, 16))


class InspectorPanel(QWidget):
    """Right-hand inspector panel with Reactive DAG + Live Variable Explorer."""

    cell_selected = Signal(str)

    def __init__(self, palette: ThemePalette, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._palette = palette
        self._last_cells: list[Cell] | None = None
        self._last_graph: DependencyGraph | None = None
        self.setMinimumWidth(290)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(6, 6, 6, 6)
        layout.setSpacing(6)

        self._summary_lbl = QLabel(t("inspector_summary", code_count=0, edge_count=0, suffix=""))
        layout.addWidget(self._summary_lbl)

        self._tabs = QTabWidget(self)
        self._dag_view = DagView(palette, self)
        self._dag_view.cell_clicked.connect(self.cell_selected.emit)

        self._var_table = QTableWidget(0, 4, self)
        self._var_table.setHorizontalHeaderLabels([
            t("inspector_col_name"),
            t("inspector_col_type"),
            t("inspector_col_value"),
            t("inspector_col_cell"),
        ])
        self._var_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        self._var_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        self._var_table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        self._var_table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
        self._var_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self._var_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self._var_table.verticalHeader().setVisible(False)

        self._tabs.addTab(self._dag_view, t("inspector_tab_graph"))
        self._tabs.addTab(self._var_table, t("inspector_tab_vars"))
        layout.addWidget(self._tabs)

        self.apply_palette(palette)

    def retranslate_ui(self) -> None:
        self._tabs.setTabText(0, t("inspector_tab_graph"))
        self._tabs.setTabText(1, t("inspector_tab_vars"))
        self._var_table.setHorizontalHeaderLabels([
            t("inspector_col_name"),
            t("inspector_col_type"),
            t("inspector_col_value"),
            t("inspector_col_cell"),
        ])
        if self._last_cells is not None and self._last_graph is not None:
            self.refresh_graph(self._last_cells, self._last_graph)
        else:
            self._summary_lbl.setText(t("inspector_summary", code_count=0, edge_count=0, suffix=""))

    def apply_palette(self, palette: ThemePalette) -> None:
        self._palette = palette
        self._summary_lbl.setStyleSheet(
            f"color: {palette.text_secondary}; font-weight: 600; font-size: 12px; padding: 2px 4px;"
        )
        self._dag_view.apply_palette(palette)

    def refresh_graph(self, cells: list[Cell], graph: DependencyGraph) -> None:
        self._last_cells = cells
        self._last_graph = graph
        code_count = sum(1 for c in cells if c.cell_type == CellType.CODE)
        edge_count = sum(len(v) for v in graph.edges.values())
        warn_parts: list[str] = []
        if graph.conflicts:
            warn_parts.append(t("inspector_warn_conflict", count=len(graph.conflicts)))
        if graph.cycles:
            warn_parts.append(t("inspector_warn_cycle", count=len(graph.cycles)))
        suffix = f" • ⚠ {', '.join(warn_parts)}" if warn_parts else ""
        self._summary_lbl.setText(
            t("inspector_summary", code_count=code_count, edge_count=edge_count, suffix=suffix)
        )
        self._dag_view.update_graph(cells, graph)

    def update_variables(
        self,
        variables: list[dict[str, str]],
        cells: list[Cell],
        graph: DependencyGraph,
    ) -> None:
        cell_num_map = {c.id: idx + 1 for idx, c in enumerate(cells)}
        self._var_table.setRowCount(len(variables))
        for row, item in enumerate(variables):
            name = item.get("name", "")
            vtype = item.get("type", "")
            preview = item.get("preview", "")
            owners = graph.symbol_owners.get(name, [])
            owner_txt = ", ".join(f"#{cell_num_map[cid]}" for cid in owners if cid in cell_num_map) or "-"
            for col, txt in enumerate((name, vtype, preview, owner_txt)):
                cell_item = QTableWidgetItem(txt)
                self._var_table.setItem(row, col, cell_item)
