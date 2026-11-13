"""Tests for `.bm.md` and `.ipynb` notebook serialization and parsing."""

from bm_notebook.format_bm import (
    load_ipynb,
    load_notebook,
    parse_bm_markdown,
    save_ipynb,
    save_notebook,
    serialize_bm_markdown,
)
from bm_notebook.model import Cell, CellOutput, CellType, NotebookDocument


def test_bm_markdown_roundtrip(tmp_path):
    doc = NotebookDocument(
        title="Test NB",
        kernel_name="python3",
        reactive_mode=True,
        cells=[
            Cell(id="m1", cell_type=CellType.MARKDOWN, source="# Hello\n\nSome prose."),
            Cell(id="m2", cell_type=CellType.MARKDOWN, source="Second markdown cell"),
            Cell(id="c1", cell_type=CellType.CODE, source="x = 1\ny = 2", collapsed=True),
            Cell(id="c2", cell_type=CellType.CODE, source="print(x + y)"),
        ],
    )
    text = serialize_bm_markdown(doc)
    # Must not contain JSON notebook boilerplate or outputs
    assert '"nbformat"' not in text
    assert "```python" in text

    p = tmp_path / "sample.bm.md"
    save_notebook(doc, p)
    loaded = load_notebook(p)

    assert loaded.title == "Test NB"
    assert loaded.kernel_name == "python3"
    assert loaded.reactive_mode is True
    assert len(loaded.cells) == 4
    assert [c.cell_type for c in loaded.cells] == [
        CellType.MARKDOWN,
        CellType.MARKDOWN,
        CellType.CODE,
        CellType.CODE,
    ]
    assert [loaded.cells[1].id, loaded.cells[2].id, loaded.cells[3].id] == ["m2", "c1", "c2"]
    assert loaded.cells[0].source == "# Hello\n\nSome prose."
    assert loaded.cells[1].source == "Second markdown cell"
    assert loaded.cells[2].collapsed is True
    assert loaded.cells[2].source == "x = 1\ny = 2"


def test_plain_markdown_parses_cleanly():
    raw = """# Plain Document

Intro text.

```python
a = 10
```
"""
    doc = parse_bm_markdown(raw, title_fallback="Plain")
    assert doc.title == "Plain"
    assert len(doc.cells) == 2
    assert doc.cells[0].cell_type == CellType.MARKDOWN
    assert doc.cells[1].cell_type == CellType.CODE
    assert doc.cells[1].source == "a = 10"


def test_ipynb_roundtrip(tmp_path):
    doc = NotebookDocument(
        title="Export Test",
        kernel_name="python3",
        cells=[
            Cell(id="m1", cell_type=CellType.MARKDOWN, source="## Section"),
            Cell(
                id="c1",
                cell_type=CellType.CODE,
                source="1 + 1",
                execution_count=1,
                outputs=[
                    CellOutput(output_type="execute_result", data={"text/plain": "2"}),
                    CellOutput(output_type="stream", name="stdout", text="hi\n"),
                ],
            ),
        ],
    )
    out_path = tmp_path / "export.ipynb"
    save_ipynb(doc, out_path)
    loaded = load_ipynb(out_path)
    assert len(loaded.cells) == 2
    assert loaded.cells[1].source == "1 + 1"
    assert loaded.cells[1].execution_count == 1
    assert len(loaded.cells[1].outputs) == 2
    assert loaded.cells[1].outputs[0].data["text/plain"] == "2"
