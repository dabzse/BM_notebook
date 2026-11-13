"""Python AST analyzer for extracting top-level definitions and external references."""

from __future__ import annotations

import ast
import builtins
from dataclasses import dataclass, field

_BUILTIN_NAMES: frozenset[str] = frozenset(dir(builtins)) | frozenset(
    {
        "__name__",
        "__doc__",
        "__package__",
        "__loader__",
        "__spec__",
        "__build_class__",
        "__import__",
        "display",
        "get_ipython",
        "In",
        "Out",
        "_",
        "__",
        "___",
        "_ih",
        "_oh",
        "_dh",
        "exit",
        "quit",
    }
)


@dataclass
class CellAnalysis:
    """Static analysis result for a single Python code cell."""

    defs: set[str] = field(default_factory=set)
    refs: set[str] = field(default_factory=set)
    syntax_error: str | None = None


def _strip_ipython_magics(source: str) -> str:
    """Replace IPython line/cell magics and shell escapes with `pass` for AST parsing."""
    lines = source.splitlines(keepends=True)
    if not lines:
        return source
    first_stripped = lines[0].lstrip()
    if first_stripped.startswith("%%"):
        return "pass\n"
    cleaned: list[str] = []
    for line in lines:
        stripped = line.lstrip()
        if stripped.startswith(("%", "!", "?")):
            indent = line[: len(line) - len(stripped)]
            cleaned.append(f"{indent}pass\n")
        else:
            cleaned.append(line)
    return "".join(cleaned)


def _extract_target_names(node: ast.AST) -> set[str]:
    """Extract all variable names bound by an assignment/for/with/match target."""
    names: set[str] = set()
    if isinstance(node, ast.Name):
        names.add(node.id)
    elif isinstance(node, (ast.Tuple, ast.List, ast.Starred)):
        for child in ast.iter_child_nodes(node):
            names.update(_extract_target_names(child))
    return names


class _ScopeCollector(ast.NodeVisitor):
    """Collects free-variable references inside a nested scope (function, class, comprehension, lambda)."""

    def __init__(self, initial_locals: set[str] | None = None) -> None:
        self.locals: set[str] = set(initial_locals or ())
        self.globals_declared: set[str] = set()
        self.refs: set[str] = set()
        self.global_defs: set[str] = set()

    def _record_ref(self, name: str) -> None:
        if name not in self.locals and name not in _BUILTIN_NAMES:
            self.refs.add(name)

    def visit_Name(self, node: ast.Name) -> None:
        if isinstance(node.ctx, ast.Load):
            self._record_ref(node.id)
        elif isinstance(node.ctx, (ast.Store, ast.Del)):
            if node.id in self.globals_declared:
                self.global_defs.add(node.id)
            else:
                self.locals.add(node.id)

    def visit_Global(self, node: ast.Global) -> None:
        self.globals_declared.update(node.names)

    def _visit_func_like(self, node: ast.FunctionDef | ast.AsyncFunctionDef) -> None:
        for dec in node.decorator_list:
            self.visit(dec)
        for default in node.args.defaults:
            self.visit(default)
        for kw_default in node.args.kw_defaults:
            if kw_default is not None:
                self.visit(kw_default)
        for arg in (
            *node.args.posonlyargs,
            *node.args.args,
            *node.args.kwonlyargs,
            *([node.args.vararg] if node.args.vararg else []),
            *([node.args.kwarg] if node.args.kwarg else []),
        ):
            if arg.annotation is not None:
                self.visit(arg.annotation)
        if node.returns is not None:
            self.visit(node.returns)

        self.locals.add(node.name)
        inner = _ScopeCollector(_collect_arg_names(node.args))
        for stmt in node.body:
            inner.visit(stmt)
        for ref in inner.refs:
            self._record_ref(ref)
        self.global_defs.update(inner.global_defs)

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        self._visit_func_like(node)

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
        self._visit_func_like(node)

    def visit_ClassDef(self, node: ast.ClassDef) -> None:
        for dec in node.decorator_list:
            self.visit(dec)
        for base in node.bases:
            self.visit(base)
        for kw in node.keywords:
            self.visit(kw.value)
        self.locals.add(node.name)
        inner = _ScopeCollector()
        for stmt in node.body:
            inner.visit(stmt)
        for ref in inner.refs:
            self._record_ref(ref)
        self.global_defs.update(inner.global_defs)

    def visit_Lambda(self, node: ast.Lambda) -> None:
        for default in node.args.defaults:
            self.visit(default)
        for kw_default in node.args.kw_defaults:
            if kw_default is not None:
                self.visit(kw_default)
        inner = _ScopeCollector(_collect_arg_names(node.args))
        inner.visit(node.body)
        for ref in inner.refs:
            self._record_ref(ref)

    def visit_ListComp(self, node: ast.ListComp) -> None:
        self._visit_comprehension(node.generators, [node.elt])

    def visit_SetComp(self, node: ast.SetComp) -> None:
        self._visit_comprehension(node.generators, [node.elt])

    def visit_GeneratorExp(self, node: ast.GeneratorExp) -> None:
        self._visit_comprehension(node.generators, [node.elt])

    def visit_DictComp(self, node: ast.DictComp) -> None:
        self._visit_comprehension(node.generators, [node.key, node.value])

    def _visit_comprehension(
        self, generators: list[ast.comprehension], elts: list[ast.expr]
    ) -> None:
        comp_locals: set[str] = set()
        for idx, gen in enumerate(generators):
            if idx == 0:
                self.visit(gen.iter)
            else:
                sub = _ScopeCollector(comp_locals)
                sub.visit(gen.iter)
                for ref in sub.refs:
                    self._record_ref(ref)
            comp_locals.update(_extract_target_names(gen.target))
            for if_expr in gen.ifs:
                sub = _ScopeCollector(comp_locals)
                sub.visit(if_expr)
                for ref in sub.refs:
                    self._record_ref(ref)
        sub = _ScopeCollector(comp_locals)
        for elt in elts:
            sub.visit(elt)
        for ref in sub.refs:
            self._record_ref(ref)

    def visit_Import(self, node: ast.Import) -> None:
        for alias in node.names:
            bound = alias.asname if alias.asname else alias.name.split(".")[0]
            self.locals.add(bound)

    def visit_ImportFrom(self, node: ast.ImportFrom) -> None:
        for alias in node.names:
            if alias.name == "*":
                continue
            bound = alias.asname if alias.asname else alias.name
            self.locals.add(bound)

    def visit_ExceptHandler(self, node: ast.ExceptHandler) -> None:
        if node.type is not None:
            self.visit(node.type)
        if node.name:
            self.locals.add(node.name)
        for stmt in node.body:
            self.visit(stmt)


def _collect_arg_names(args: ast.arguments) -> set[str]:
    names: set[str] = set()
    for arg in (*args.posonlyargs, *args.args, *args.kwonlyargs):
        names.add(arg.arg)
    if args.vararg:
        names.add(args.vararg.arg)
    if args.kwarg:
        names.add(args.kwarg.arg)
    return names


class _ModuleCellAnalyzer:
    """Walks top-level statements in a cell in execution order."""

    def __init__(self) -> None:
        self.defs: set[str] = set()
        self.refs: set[str] = set()

    def _add_ref(self, name: str) -> None:
        if name not in self.defs and name not in _BUILTIN_NAMES:
            self.refs.add(name)

    def _visit_expr_loads(self, node: ast.AST) -> None:
        collector = _ScopeCollector(initial_locals=set(self.defs))
        collector.visit(node)
        self.refs.update(collector.refs)
        self.defs.update(collector.global_defs)

    def _visit_target_subscripts(self, target: ast.AST) -> None:
        """If target is `arr[i] = val` or `obj.attr = val`, `arr`/`i`/`obj` are refs!"""
        if isinstance(target, ast.Subscript):
            self._visit_expr_loads(target.value)
            self._visit_expr_loads(target.slice)
        elif isinstance(target, ast.Attribute):
            self._visit_expr_loads(target.value)
        elif isinstance(target, (ast.Tuple, ast.List, ast.Starred)):
            for child in ast.iter_child_nodes(target):
                self._visit_target_subscripts(child)

    def visit_stmt(self, stmt: ast.stmt) -> None:
        method_name = _STMT_HANDLER_NAMES.get(type(stmt))
        if method_name is not None:
            getattr(self, method_name)(stmt)
        else:
            self._visit_expr_loads(stmt)

    def _visit_stmts(self, stmts: list[ast.stmt]) -> None:
        for s in stmts:
            self.visit_stmt(s)

    def _visit_assign(self, stmt: ast.Assign) -> None:
        self._visit_expr_loads(stmt.value)
        for target in stmt.targets:
            self._visit_target_subscripts(target)
            self.defs.update(_extract_target_names(target))

    def _visit_aug_assign(self, stmt: ast.AugAssign) -> None:
        self._visit_expr_loads(stmt.target)
        self._visit_expr_loads(stmt.value)
        self._visit_target_subscripts(stmt.target)
        if isinstance(stmt.target, ast.Name):
            self._add_ref(stmt.target.id)
            self.defs.add(stmt.target.id)

    def _visit_ann_assign(self, stmt: ast.AnnAssign) -> None:
        if stmt.annotation is not None:
            self._visit_expr_loads(stmt.annotation)
        if stmt.value is not None:
            self._visit_expr_loads(stmt.value)
            self._visit_target_subscripts(stmt.target)
            self.defs.update(_extract_target_names(stmt.target))

    def _visit_func_def(self, stmt: ast.FunctionDef | ast.AsyncFunctionDef) -> None:
        for dec in stmt.decorator_list:
            self._visit_expr_loads(dec)
        for default in stmt.args.defaults:
            self._visit_expr_loads(default)
        for kw_default in stmt.args.kw_defaults:
            if kw_default is not None:
                self._visit_expr_loads(kw_default)
        for arg in (
            *stmt.args.posonlyargs,
            *stmt.args.args,
            *stmt.args.kwonlyargs,
            *([stmt.args.vararg] if stmt.args.vararg else []),
            *([stmt.args.kwarg] if stmt.args.kwarg else []),
        ):
            if arg.annotation is not None:
                self._visit_expr_loads(arg.annotation)
        if stmt.returns is not None:
            self._visit_expr_loads(stmt.returns)

        self.defs.add(stmt.name)
        inner = _ScopeCollector(_collect_arg_names(stmt.args) | self.defs)
        for body_stmt in stmt.body:
            inner.visit(body_stmt)
        for ref in inner.refs:
            self._add_ref(ref)
        self.defs.update(inner.global_defs)

    def _visit_class_def(self, stmt: ast.ClassDef) -> None:
        for dec in stmt.decorator_list:
            self._visit_expr_loads(dec)
        for base in stmt.bases:
            self._visit_expr_loads(base)
        for kw in stmt.keywords:
            self._visit_expr_loads(kw.value)
        self.defs.add(stmt.name)
        inner = _ScopeCollector(set(self.defs))
        for body_stmt in stmt.body:
            inner.visit(body_stmt)
        for ref in inner.refs:
            self._add_ref(ref)
        self.defs.update(inner.global_defs)

    def _visit_import(self, stmt: ast.Import) -> None:
        for alias in stmt.names:
            self.defs.add(alias.asname or alias.name.split(".")[0])

    def _visit_import_from(self, stmt: ast.ImportFrom) -> None:
        for alias in stmt.names:
            if alias.name != "*":
                self.defs.add(alias.asname or alias.name)

    def _visit_for(self, stmt: ast.For | ast.AsyncFor) -> None:
        self._visit_expr_loads(stmt.iter)
        self._visit_target_subscripts(stmt.target)
        self.defs.update(_extract_target_names(stmt.target))
        self._visit_stmts(stmt.body)
        self._visit_stmts(stmt.orelse)

    def _visit_with(self, stmt: ast.With | ast.AsyncWith) -> None:
        for item in stmt.items:
            self._visit_expr_loads(item.context_expr)
            if item.optional_vars is not None:
                self._visit_target_subscripts(item.optional_vars)
                self.defs.update(_extract_target_names(item.optional_vars))
        self._visit_stmts(stmt.body)

    def _visit_if_or_while(self, stmt: ast.If | ast.While) -> None:
        self._visit_expr_loads(stmt.test)
        self._visit_stmts(stmt.body)
        self._visit_stmts(stmt.orelse)

    def _visit_try(self, stmt: ast.Try) -> None:
        self._visit_stmts(stmt.body)
        for handler in stmt.handlers:
            if handler.type is not None:
                self._visit_expr_loads(handler.type)
            if handler.name:
                self.defs.add(handler.name)
            self._visit_stmts(handler.body)
        self._visit_stmts(stmt.orelse)
        self._visit_stmts(stmt.finalbody)

    def _visit_delete(self, stmt: ast.Delete) -> None:
        for target in stmt.targets:
            if isinstance(target, ast.Name):
                self._add_ref(target.id)
                self.defs.discard(target.id)
            else:
                self._visit_expr_loads(target)

    def _visit_match(self, stmt: ast.Match) -> None:
        self._visit_expr_loads(stmt.subject)
        for case in stmt.cases:
            if case.guard is not None:
                self._visit_expr_loads(case.guard)
            for pat in ast.walk(case.pattern):
                if (
                    (isinstance(pat, ast.MatchAs) and pat.name)
                    or (isinstance(pat, ast.MatchStar) and pat.name)
                ):
                    self.defs.add(pat.name)
                elif isinstance(pat, ast.MatchMapping) and pat.rest:
                    self.defs.add(pat.rest)
            self._visit_stmts(case.body)


_STMT_HANDLER_NAMES: dict[type[ast.stmt], str] = {
    ast.Assign: "_visit_assign",
    ast.AugAssign: "_visit_aug_assign",
    ast.AnnAssign: "_visit_ann_assign",
    ast.FunctionDef: "_visit_func_def",
    ast.AsyncFunctionDef: "_visit_func_def",
    ast.ClassDef: "_visit_class_def",
    ast.Import: "_visit_import",
    ast.ImportFrom: "_visit_import_from",
    ast.For: "_visit_for",
    ast.AsyncFor: "_visit_for",
    ast.With: "_visit_with",
    ast.AsyncWith: "_visit_with",
    ast.If: "_visit_if_or_while",
    ast.While: "_visit_if_or_while",
    ast.Try: "_visit_try",
    ast.Delete: "_visit_delete",
}
if hasattr(ast, "Match"):
    _STMT_HANDLER_NAMES[ast.Match] = "_visit_match"


def analyze_cell_ast(source: str) -> CellAnalysis:
    """Analyze a Python code cell and return top-level defs, external refs, and syntax errors."""
    if not source.strip():
        return CellAnalysis()

    cleaned = _strip_ipython_magics(source)
    try:
        tree = ast.parse(cleaned, mode="exec")
    except SyntaxError as exc:
        msg = f"SyntaxError (line {exc.lineno}): {exc.msg}"
        return CellAnalysis(syntax_error=msg)

    analyzer = _ModuleCellAnalyzer()
    for stmt in tree.body:
        analyzer.visit_stmt(stmt)

    # Do not treat private-only helper conventions differently, keep all top-level defs
    return CellAnalysis(defs=analyzer.defs, refs=analyzer.refs, syntax_error=None)
