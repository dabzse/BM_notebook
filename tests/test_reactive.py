"""Tests for Python AST cell analysis and reactive DAG planning."""

from bm_notebook.model import Cell, CellType
from bm_notebook.reactive import DependencyGraph, analyze_cell_ast


def test_ast_basic_defs_and_refs():
    src = """
import numpy as np
from math import sqrt as s
a = 10
b = a * 2 + ext_var
"""
    res = analyze_cell_ast(src)
    assert res.syntax_error is None
    assert res.defs == {"np", "s", "a", "b"}
    assert res.refs == {"ext_var"}


def test_ast_scoped_functions_and_comprehensions():
    src = """
def transform(x, scale=factor):
    local_tmp = [i * scale for i in x if i > min_val]
    return local_tmp

class Holder(BaseClass):
    cls_attr = 42
    def method(self):
        return self.cls_attr + global_bias
"""
    res = analyze_cell_ast(src)
    assert res.syntax_error is None
    assert res.defs == {"transform", "Holder"}
    assert res.refs == {"factor", "min_val", "BaseClass", "global_bias"}


def test_ast_self_increment_counts_as_ref_and_def():
    res = analyze_cell_ast("counter += 1")
    assert res.syntax_error is None
    assert "counter" in res.defs
    assert "counter" in res.refs


def test_ast_ignores_ipython_magics():
    src = """%matplotlib inline
!echo hello
x = 123
"""
    res = analyze_cell_ast(src)
    assert res.syntax_error is None
    assert res.defs == {"x"}
    assert res.refs == set()


def test_ast_syntax_error_reported_cleanly():
    res = analyze_cell_ast("def broken(:\n  pass")
    assert res.syntax_error is not None
    assert "SyntaxError" in res.syntax_error


def test_dag_topological_order_even_when_out_of_order():
    # Cell c3 uses y from c2, c2 uses x from c1, even though c3 appears FIRST in notebook
    c3 = Cell(id="c3", cell_type=CellType.CODE, source="z = y + 1")
    c1 = Cell(id="c1", cell_type=CellType.CODE, source="x = 5")
    c2 = Cell(id="c2", cell_type=CellType.CODE, source="y = x * 2")
    md = Cell(id="m1", cell_type=CellType.MARKDOWN, source="# Notes")

    graph = DependencyGraph.build([c3, md, c1, c2])
    assert not graph.cycles
    assert not graph.conflicts

    plan = graph.execution_plan(["c1"], cascade=True)
    assert plan.order == ["c1", "c2", "c3"]

    full_plan = graph.run_all_plan()
    assert full_plan.order == ["c1", "c2", "c3"]


def test_dag_conflict_and_cycle_detection():
    c1 = Cell(id="c1", cell_type=CellType.CODE, source="a = b + 1")
    c2 = Cell(id="c2", cell_type=CellType.CODE, source="b = a + 1")
    c3 = Cell(id="c3", cell_type=CellType.CODE, source="a = 99")

    graph = DependencyGraph.build([c1, c2, c3])
    assert "a" in graph.conflicts
    assert set(graph.conflicts["a"]) == {"c1", "c3"}
    assert graph.cycles
    assert {"c1", "c2"}.issubset(graph.cycle_cells)

    plan = graph.execution_plan(["c1"], cascade=True)
    assert "c1" in plan.blocked_by_cycle
    assert "c2" in plan.blocked_by_cycle
    assert "c1" not in plan.order
