"""Reactive dependency graph (DAG) builder, cycle detector, and topological planner."""

from __future__ import annotations

import heapq
from collections import defaultdict, deque
from dataclasses import dataclass, field

from bm_notebook.model import Cell, CellType

from .analyzer import analyze_cell_ast


@dataclass
class ExecutionPlan:
    """Ordered execution plan for a reactive cascade or full notebook run."""

    order: list[str] = field(default_factory=list)
    blocked_by_cycle: set[str] = field(default_factory=set)
    conflicts: dict[str, list[str]] = field(default_factory=dict)


class DependencyGraph:
    """Directed dependency graph across code cells in a NotebookDocument."""

    def __init__(self) -> None:
        self.cell_order: list[str] = []
        self.cell_index: dict[str, int] = {}
        self.symbol_owners: dict[str, list[str]] = {}
        self.conflicts: dict[str, list[str]] = {}
        self.edges: dict[str, set[str]] = defaultdict(set)
        self.reverse_edges: dict[str, set[str]] = defaultdict(set)
        self.edge_symbols: dict[tuple[str, str], set[str]] = defaultdict(set)
        self.cycles: list[list[str]] = []
        self.cycle_cells: set[str] = set()

    @classmethod
    def build(cls, cells: list[Cell], analyze: bool = True) -> DependencyGraph:
        """Analyze code cells (when analyze=True) and build the full dependency graph."""
        graph = cls()
        code_cells = [c for c in cells if c.cell_type == CellType.CODE]
        graph._analyze_cells(code_cells, analyze=analyze)
        graph._index_symbols_and_conflicts(code_cells)
        graph._build_edges(code_cells)
        graph._detect_cycles()
        graph._annotate_cycles(code_cells)
        return graph

    def _analyze_cells(self, code_cells: list[Cell], analyze: bool) -> None:
        for idx, cell in enumerate(code_cells):
            self.cell_order.append(cell.id)
            self.cell_index[cell.id] = idx
            cell.conflict_symbols = []
            cell.cycle_info = None
            if analyze:
                analysis = analyze_cell_ast(cell.source)
                cell.defs = analysis.defs
                cell.refs = analysis.refs
                cell.syntax_error = analysis.syntax_error

    def _index_symbols_and_conflicts(self, code_cells: list[Cell]) -> None:
        owners: dict[str, list[str]] = defaultdict(list)
        for cell in code_cells:
            for sym in sorted(cell.defs):
                owners[sym].append(cell.id)
        self.symbol_owners = dict(owners)

        cell_by_id = {c.id: c for c in code_cells}
        for sym, owner_ids in self.symbol_owners.items():
            if len(owner_ids) > 1:
                self.conflicts[sym] = list(owner_ids)
                for cid in owner_ids:
                    cell_by_id[cid].conflict_symbols.append(sym)

    def _build_edges(self, code_cells: list[Cell]) -> None:
        for cell in code_cells:
            for ref in cell.refs:
                for owner_id in self.symbol_owners.get(ref, ()):
                    if owner_id != cell.id:
                        self.edges[owner_id].add(cell.id)
                        self.reverse_edges[cell.id].add(owner_id)
                        self.edge_symbols[(owner_id, cell.id)].add(ref)

    def _annotate_cycles(self, code_cells: list[Cell]) -> None:
        for cell in code_cells:
            if cell.id not in self.cycle_cells:
                continue
            matching = [cyc for cyc in self.cycles if cell.id in cyc]
            if matching:
                labels = [f"#{self.cell_index[cid] + 1}" for cid in matching[0]]
                cell.cycle_info = "Dependency cycle: " + " -> ".join(labels)

    def _pop_scc(self, node: str, stack: list[str], on_stack: set[str]) -> None:
        scc: list[str] = []
        while stack:
            w = stack.pop()
            on_stack.remove(w)
            scc.append(w)
            if w == node:
                break
        if len(scc) > 1:
            scc_sorted = sorted(scc, key=lambda cid: self.cell_index[cid])
            self.cycles.append([*scc_sorted, scc_sorted[0]])
            self.cycle_cells.update(scc_sorted)

    def _detect_cycles(self) -> None:
        """Find strongly connected components of size >= 2 using Tarjan's algorithm."""
        index_counter = 0
        indices: dict[str, int] = {}
        lowlink: dict[str, int] = {}
        stack: list[str] = []
        on_stack: set[str] = set()

        def strongconnect(node: str) -> None:
            nonlocal index_counter
            indices[node] = lowlink[node] = index_counter
            index_counter += 1
            stack.append(node)
            on_stack.add(node)

            for neighbor in sorted(self.edges.get(node, ()), key=lambda cid: self.cell_index[cid]):
                if neighbor not in indices:
                    strongconnect(neighbor)
                    lowlink[node] = min(lowlink[node], lowlink[neighbor])
                elif neighbor in on_stack:
                    lowlink[node] = min(lowlink[node], indices[neighbor])

            if lowlink[node] == indices[node]:
                self._pop_scc(node, stack, on_stack)

        for cid in self.cell_order:
            if cid not in indices:
                strongconnect(cid)

    def downstream_cells(self, root_cell_ids: list[str]) -> set[str]:
        """Return all transitive downstream cells reachable from root_cell_ids (excluding roots)."""
        visited: set[str] = set()
        queue: deque[str] = deque()
        root_set = set(root_cell_ids)
        for rid in root_cell_ids:
            if rid in self.cell_index:
                queue.append(rid)

        while queue:
            cur = queue.popleft()
            for nxt in self.edges.get(cur, ()):
                if nxt not in visited:
                    visited.add(nxt)
                    queue.append(nxt)

        return visited - root_set

    def _compute_in_degrees(self, executable: set[str]) -> dict[str, int]:
        in_degree: dict[str, int] = dict.fromkeys(executable, 0)
        for u in executable:
            for v in self.edges.get(u, ()):
                if v in executable:
                    in_degree[v] += 1
        return in_degree

    def _topological_order(self, executable: set[str]) -> list[str]:
        in_degree = self._compute_in_degrees(executable)
        heap: list[tuple[int, str]] = [
            (self.cell_index[cid], cid) for cid, deg in in_degree.items() if deg == 0
        ]
        heapq.heapify(heap)

        order: list[str] = []
        while heap:
            _, u = heapq.heappop(heap)
            order.append(u)
            for v in self.edges.get(u, ()):
                if v in in_degree:
                    in_degree[v] -= 1
                    if in_degree[v] == 0:
                        heapq.heappush(heap, (self.cell_index[v], v))
        return order

    def execution_plan(
        self,
        root_cell_ids: list[str],
        cascade: bool = True,
    ) -> ExecutionPlan:
        """Compute topological execution order for root_cell_ids and optional downstream cascade."""
        target_set: set[str] = {cid for cid in root_cell_ids if cid in self.cell_index}
        if cascade:
            target_set |= self.downstream_cells(list(target_set))

        blocked = target_set & self.cycle_cells
        executable = target_set - blocked
        order = self._topological_order(executable)

        return ExecutionPlan(
            order=order,
            blocked_by_cycle=blocked,
            conflicts=dict(self.conflicts),
        )

    def run_all_plan(self) -> ExecutionPlan:
        """Compute full topological execution order for all code cells."""
        return self.execution_plan(list(self.cell_order), cascade=True)
