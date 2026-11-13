"""Core data models for BM Notebook."""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from enum import Enum


class CellType(str, Enum):
    CODE = "code"
    MARKDOWN = "markdown"


class CellState(str, Enum):
    IDLE = "idle"
    QUEUED = "queued"
    RUNNING = "running"
    DONE = "done"
    STALE = "stale"
    ERROR = "error"
    CYCLE_ERROR = "cycle_error"


@dataclass
class CellOutput:
    """Represents a single output item produced by a Jupyter kernel."""

    output_type: str  # "stream", "execute_result", "display_data", "error"
    data: dict[str, str] = field(default_factory=dict)  # mime_type -> content
    text: str = ""  # used for stream stdout/stderr
    name: str = "stdout"  # stdout | stderr
    ename: str = ""
    evalue: str = ""
    traceback: list[str] = field(default_factory=list)


def new_cell_id() -> str:
    return f"c-{uuid.uuid4().hex[:8]}"


@dataclass
class Cell:
    """A single notebook cell (code or markdown)."""

    id: str = field(default_factory=new_cell_id)
    cell_type: CellType = CellType.CODE
    source: str = ""
    outputs: list[CellOutput] = field(default_factory=list)
    execution_count: int | None = None
    state: CellState = CellState.IDLE
    defs: set[str] = field(default_factory=set)
    refs: set[str] = field(default_factory=set)
    last_executed_defs: set[str] = field(default_factory=set)
    syntax_error: str | None = None
    conflict_symbols: list[str] = field(default_factory=list)
    cycle_info: str | None = None
    duration_ms: float | None = None
    collapsed: bool = False
    dirty: bool = False


@dataclass
class NotebookDocument:
    """In-memory representation of a BM Notebook document."""

    title: str = "Untitled"
    kernel_name: str = "python3"
    reactive_mode: bool = True
    cells: list[Cell] = field(default_factory=list)
    file_path: str | None = None
    metadata: dict[str, object] = field(default_factory=dict)

    def get_cell(self, cell_id: str) -> Cell | None:
        for cell in self.cells:
            if cell.id == cell_id:
                return cell
        return None

    def index_of(self, cell_id: str) -> int:
        for idx, cell in enumerate(self.cells):
            if cell.id == cell_id:
                return idx
        return -1

    def insert_cell(
        self,
        index: int,
        cell_type: CellType = CellType.CODE,
        source: str = "",
        cell_id: str | None = None,
    ) -> Cell:
        cell = Cell(
            id=cell_id or new_cell_id(),
            cell_type=cell_type,
            source=source,
        )
        index = max(0, min(index, len(self.cells)))
        self.cells.insert(index, cell)
        return cell

    def remove_cell(self, cell_id: str) -> bool:
        idx = self.index_of(cell_id)
        if idx < 0:
            return False
        self.cells.pop(idx)
        return True

    def move_cell(self, cell_id: str, delta: int) -> bool:
        idx = self.index_of(cell_id)
        if idx < 0:
            return False
        new_idx = idx + delta
        if new_idx < 0 or new_idx >= len(self.cells):
            return False
        cell = self.cells.pop(idx)
        self.cells.insert(new_idx, cell)
        return True

    def ensure_non_empty(self) -> None:
        if not self.cells:
            self.cells.append(Cell(cell_type=CellType.CODE, source=""))
