"""Clean, Git-friendly `.bm.md` parser/serializer and `.ipynb` importer/exporter."""

from __future__ import annotations

import json
import re
from pathlib import Path

from bm_notebook.model import Cell, CellOutput, CellType, NotebookDocument, new_cell_id

_CODE_FENCE_OPEN_RE = re.compile(r"^```([\w+-]*)")
_ATTR_RE = re.compile(r'(\w+)=(?:"([^"]*)"|(\S+))')


def _extract_frontmatter(text: str) -> tuple[str, str] | None:
    if not text.startswith("---"):
        return None
    first_nl = text.find("\n")
    if first_nl == -1 or text[3:first_nl].strip():
        return None

    search_from = first_nl + 1
    while (close_idx := text.find("\n---", search_from)) != -1:
        after = close_idx + 4
        end_nl = text.find("\n", after)
        tail = text[after:] if end_nl == -1 else text[after:end_nl]
        if not tail.strip():
            body = "" if end_nl == -1 else text[end_nl + 1:]
            return text[first_nl + 1:close_idx], body
        search_from = after
    return None


def _extract_md_split_attrs(line: str) -> str | None:
    stripped = line.strip()
    if not (stripped.startswith("<!--") and stripped.endswith("-->")):
        return None
    inner = stripped[4:-3].strip()
    prefix = "bm:markdown"
    if inner == prefix:
        return ""
    if inner.startswith(prefix) and inner[len(prefix)].isspace():
        return inner[len(prefix):].strip()
    return None


def _parse_attrs(raw: str) -> dict[str, str]:
    attrs: dict[str, str] = {}
    for match in _ATTR_RE.finditer(raw):
        key = match.group(1)
        val = match.group(2) if match.group(2) is not None else match.group(3)
        attrs[key] = val
    return attrs


def _apply_frontmatter(doc: NotebookDocument, text: str) -> str:
    """Parse optional YAML-like frontmatter onto `doc` and return remaining body."""
    extracted = _extract_frontmatter(text)
    if extracted is None:
        return text
    header, body = extracted

    for line in header.splitlines():
        if ":" not in line:
            continue
        key, val = (part.strip() for part in line.split(":", 1))
        key_l = key.lower()
        if key_l == "title" and val:
            doc.title = val.strip("\"'")
        elif key_l == "kernel" and val:
            doc.kernel_name = val.strip("\"'")
        elif key_l == "reactive":
            doc.reactive_mode = val.lower() in {"true", "1", "yes", "on"}
    return body


def _consume_code_fence(lines: list[str], start_idx: int) -> tuple[Cell | None, int]:
    """Consume a fenced code block starting at `start_idx` if it represents a notebook cell."""
    line = lines[start_idx]
    fence_match = _CODE_FENCE_OPEN_RE.match(line)
    if not fence_match:
        return None, start_idx

    lang = (fence_match.group(1) or "").strip().lower()
    attrs = _parse_attrs(line[fence_match.end():].strip())
    if lang not in {"python", "py", "ipython", "code", ""} and "id" not in attrs:
        return None, start_idx

    code_lines: list[str] = []
    idx = start_idx + 1
    while idx < len(lines) and not lines[idx].startswith("```"):
        code_lines.append(lines[idx])
        idx += 1
    if idx < len(lines) and lines[idx].startswith("```"):
        idx += 1

    cell = Cell(
        id=attrs.get("id") or new_cell_id(),
        cell_type=CellType.CODE,
        source="\n".join(code_lines),
        collapsed=attrs.get("collapsed", "").lower() == "true",
    )
    return cell, idx


def _flush_markdown_buffer(
    doc: NotebookDocument,
    md_buffer: list[str],
    pending_attrs: dict[str, str],
) -> None:
    content = "\n".join(md_buffer).strip("\n")
    if content.strip():
        doc.cells.append(
            Cell(
                id=pending_attrs.get("id") or new_cell_id(),
                cell_type=CellType.MARKDOWN,
                source=content,
            )
        )
    md_buffer.clear()
    pending_attrs.clear()


def parse_bm_markdown(text: str, title_fallback: str = "Untitled") -> NotebookDocument:
    """Parse a clean `.bm.md` (or plain `.md`) string into a NotebookDocument."""
    doc = NotebookDocument(title=title_fallback)
    lines = _apply_frontmatter(doc, text).splitlines()
    idx = 0
    md_buffer: list[str] = []
    pending_md_attrs: dict[str, str] = {}

    while idx < len(lines):
        line = lines[idx]
        marker_attrs = _extract_md_split_attrs(line)
        if marker_attrs is not None:
            _flush_markdown_buffer(doc, md_buffer, pending_md_attrs)
            pending_md_attrs.update(_parse_attrs(marker_attrs))
            idx += 1
            continue

        code_cell, next_idx = _consume_code_fence(lines, idx)
        if code_cell is not None:
            _flush_markdown_buffer(doc, md_buffer, pending_md_attrs)
            doc.cells.append(code_cell)
            idx = next_idx
            continue

        md_buffer.append(line)
        idx += 1

    _flush_markdown_buffer(doc, md_buffer, pending_md_attrs)
    doc.ensure_non_empty()
    return doc


def serialize_bm_markdown(doc: NotebookDocument) -> str:
    """Serialize a NotebookDocument into clean, diff-friendly `.bm.md` text."""
    parts: list[str] = [
        "---",
        f"title: {doc.title}",
        f"kernel: {doc.kernel_name}",
        f"reactive: {'true' if doc.reactive_mode else 'false'}",
        "---",
        "",
    ]

    prev_type: CellType | None = None
    for idx, cell in enumerate(doc.cells):
        if cell.cell_type == CellType.MARKDOWN:
            if prev_type == CellType.MARKDOWN:
                parts.append(f'<!-- bm:markdown id="{cell.id}" -->')
            parts.extend([cell.source.rstrip("\n"), ""])
        else:
            attrs = [f'id="{cell.id}"']
            if cell.collapsed:
                attrs.append("collapsed=true")
            info = " ".join(attrs)
            parts.extend([f"```python {info}", cell.source.rstrip("\n"), "```"])
            if idx < len(doc.cells) - 1:
                parts.append("")
        prev_type = cell.cell_type

    return "\n".join(parts).rstrip() + "\n"


def _join_ipynb_source(src: str | list[str]) -> str:
    if isinstance(src, list):
        return "".join(src)
    return str(src)


def _split_ipynb_source(src: str) -> list[str]:
    if not src:
        return []
    return src.splitlines(keepends=True)


def load_ipynb(path: str | Path) -> NotebookDocument:
    """Import a standard Jupyter `.ipynb` (nbformat 4) file into a NotebookDocument."""
    p = Path(path)
    raw = json.loads(p.read_text(encoding="utf-8"))
    meta = raw.get("metadata", {})
    kernelspec = meta.get("kernelspec", {})
    kernel_name = kernelspec.get("name", "python3")

    doc = NotebookDocument(
        title=p.stem,
        kernel_name=kernel_name,
        reactive_mode=True,
        file_path=str(p),
        metadata=meta,
    )

    for raw_cell in raw.get("cells", []):
        ctype_str = raw_cell.get("cell_type", "code")
        if ctype_str not in {"code", "markdown"}:
            ctype_str = "markdown"
        ctype = CellType(ctype_str)
        source = _join_ipynb_source(raw_cell.get("source", ""))
        cell_id = raw_cell.get("id") or new_cell_id()

        outputs: list[CellOutput] = []
        for out in raw_cell.get("outputs", []):
            otype = out.get("output_type", "stream")
            if otype == "stream":
                outputs.append(
                    CellOutput(
                        output_type="stream",
                        name=out.get("name", "stdout"),
                        text=_join_ipynb_source(out.get("text", "")),
                    )
                )
            elif otype in {"execute_result", "display_data"}:
                raw_data = out.get("data", {})
                norm_data = {k: _join_ipynb_source(v) for k, v in raw_data.items()}
                outputs.append(CellOutput(output_type=otype, data=norm_data))
            elif otype == "error":
                outputs.append(
                    CellOutput(
                        output_type="error",
                        ename=out.get("ename", "Error"),
                        evalue=out.get("evalue", ""),
                        traceback=list(out.get("traceback", [])),
                    )
                )

        doc.cells.append(
            Cell(
                id=cell_id,
                cell_type=ctype,
                source=source,
                outputs=outputs,
                execution_count=raw_cell.get("execution_count"),
            )
        )

    doc.ensure_non_empty()
    return doc


def _serialize_ipynb_output(
    out: CellOutput,
    execution_count: int | None,
) -> dict[str, object] | None:
    if out.output_type == "stream":
        return {
            "output_type": "stream",
            "name": out.name,
            "text": _split_ipynb_source(out.text),
        }
    if out.output_type in {"execute_result", "display_data"}:
        item: dict[str, object] = {
            "output_type": out.output_type,
            "data": dict(out.data),
            "metadata": {},
        }
        if out.output_type == "execute_result":
            item["execution_count"] = execution_count
        return item
    if out.output_type == "error":
        return {
            "output_type": "error",
            "ename": out.ename,
            "evalue": out.evalue,
            "traceback": list(out.traceback),
        }
    return None


def _serialize_ipynb_cell(cell: Cell) -> dict[str, object]:
    if cell.cell_type == CellType.MARKDOWN:
        return {
            "id": cell.id,
            "cell_type": "markdown",
            "metadata": {},
            "source": _split_ipynb_source(cell.source),
        }
    nb_outputs = [
        item
        for out in cell.outputs
        if (item := _serialize_ipynb_output(out, cell.execution_count)) is not None
    ]
    return {
        "id": cell.id,
        "cell_type": "code",
        "execution_count": cell.execution_count,
        "metadata": {},
        "outputs": nb_outputs,
        "source": _split_ipynb_source(cell.source),
    }


def save_ipynb(doc: NotebookDocument, path: str | Path) -> None:
    """Export a NotebookDocument to standard Jupyter `.ipynb` (nbformat 4.5)."""
    nb_cells = [_serialize_ipynb_cell(cell) for cell in doc.cells]
    payload = {
        "nbformat": 4,
        "nbformat_minor": 5,
        "metadata": {
            "kernelspec": {
                "name": doc.kernel_name,
                "display_name": doc.kernel_name,
                "language": "python",
            },
            "language_info": {"name": "python"},
        },
        "cells": nb_cells,
    }
    Path(path).write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def load_notebook(path: str | Path) -> NotebookDocument:
    """Load either `.bm.md`/`.md` or `.ipynb` based on file extension."""
    p = Path(path)
    if p.suffix.lower() == ".ipynb":
        return load_ipynb(p)
    doc = parse_bm_markdown(p.read_text(encoding="utf-8"), title_fallback=p.stem.removesuffix(".bm"))
    doc.file_path = str(p)
    return doc


def save_notebook(doc: NotebookDocument, path: str | Path) -> None:
    """Save either `.bm.md`/`.md` or `.ipynb` based on file extension."""
    p = Path(path)
    if p.suffix.lower() == ".ipynb":
        save_ipynb(doc, p)
    else:
        p.write_text(serialize_bm_markdown(doc), encoding="utf-8")
    doc.file_path = str(p)
