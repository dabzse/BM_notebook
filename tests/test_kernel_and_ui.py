"""Integration tests for live Jupyter kernel execution and offscreen Qt6 MainWindow."""

from __future__ import annotations

import os
import sys
import time
from pathlib import Path

import pytest
from PySide6.QtWidgets import QApplication

from bm_notebook.kernel import KernelBridge
from bm_notebook.kernel.manager import ExecutionTask
from bm_notebook.model import CellState, CellType
from bm_notebook.settings import resolve_settings_path
from bm_notebook.ui.ansi import ansi_to_html, strip_ansi
from bm_notebook.ui.main_window import MainWindow

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ["QT_QPA_PLATFORMTHEME"] = ""


@pytest.fixture(scope="module")
def qt_app():
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


def _pump_events(qt_app: QApplication, condition, timeout: float = 15.0) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        qt_app.processEvents()
        if condition():
            return True
        time.sleep(0.02)
    return condition()


def test_ansi_converter():
    colored = "\x1b[31mError\x1b[0m: plain"
    assert strip_ansi(colored) == "Error: plain"
    html_out = ansi_to_html(colored, dark=True)
    assert "<span" in html_out
    assert "Error" in html_out


def test_kernel_bridge_reactive_execution_cleanup_and_completion(qt_app):
    bridge = KernelBridge()
    started = []
    finished = {}
    outputs = {}
    aborted = []
    completions = []
    variables = []

    bridge.kernel_started.connect(lambda k, lang: started.append((k, lang)))
    bridge.cell_finished.connect(lambda cid, ok, ec, _ms, err: finished.update({cid: (ok, ec, err)}))
    bridge.cell_output.connect(lambda cid, out: outputs.setdefault(cid, []).append(out))
    bridge.batch_aborted.connect(aborted.extend)
    bridge.completions_ready.connect(lambda cid, _pos, matches, _s, _e: completions.append((cid, matches)))
    bridge.variables_updated.connect(variables.append)

    try:
        bridge.start_kernel("python3", "python")
        assert _pump_events(qt_app, lambda: len(started) == 1, timeout=20.0)

        # 1. Execute two dependent tasks
        bridge.execute_batch(
            [
                ExecutionTask(cell_id="c1", code="base_val = 21\nghost_var = 999", removed_defs=[]),
                ExecutionTask(cell_id="c2", code="base_val * 2", removed_defs=[]),
            ]
        )
        assert _pump_events(qt_app, lambda: "c2" in finished, timeout=15.0)
        assert finished["c1"][0] is True
        assert finished["c2"][0] is True
        assert any(o.data.get("text/plain") == "42" for o in outputs.get("c2", []))

        # 2. Verify removed_defs cleans up ghost_var
        finished.clear()
        outputs.clear()
        bridge.execute_batch(
            [
                ExecutionTask(cell_id="c1", code="base_val = 10", removed_defs=["ghost_var"]),
                ExecutionTask(cell_id="c3", code="'ghost_var' in globals()", removed_defs=[]),
            ]
        )
        assert _pump_events(qt_app, lambda: "c3" in finished, timeout=15.0)
        assert any(o.data.get("text/plain") == "False" for o in outputs.get("c3", []))

        # 3. Verify error aborts downstream tasks
        finished.clear()
        aborted.clear()
        bridge.execute_batch(
            [
                ExecutionTask(cell_id="c_err", code="1 / 0", removed_defs=[]),
                ExecutionTask(cell_id="c_skip", code="x = 1", removed_defs=[]),
            ]
        )
        assert _pump_events(qt_app, lambda: "c_err" in finished and len(aborted) == 1, timeout=15.0)
        assert finished["c_err"][0] is False
        assert aborted == ["c_skip"]

        # 4. Verify tab completion
        bridge.request_completions("c1", "base_v", 6)
        assert _pump_events(qt_app, lambda: len(completions) == 1, timeout=10.0)
        assert "base_val" in completions[0][1]
    finally:
        bridge.shutdown()


def test_main_window_opens_demo_and_runs_reactive_cascade(qt_app, tmp_path: Path):
    demo_path = Path(__file__).resolve().parent.parent / "examples" / "reactive_demo.bm.md"
    win = MainWindow(initial_file=str(demo_path), settings_path=tmp_path / "settings.json")
    try:
        assert _pump_events(
            qt_app,
            lambda: "Kész" in win._status_kernel_lbl.text(),
            timeout=20.0,
        )
        expected_demo_cells = 5
        assert len(win._doc.cells) == expected_demo_cells

        # Run from params cell (index 1) -> should reactively run signal, table, and plot!
        params_cell = win._doc.cells[1]
        assert params_cell.id == "c-params"
        win.run_cell(params_cell.id)

        assert _pump_events(
            qt_app,
            lambda: all(
                c.state in {CellState.DONE, CellState.ERROR}
                for c in win._doc.cells
                if c.cell_type == CellType.CODE
            ),
            timeout=45.0,
        )
        failed_cells = [
            (c.id, c.error_message, [o.text or o.ename for o in c.outputs])
            for c in win._doc.cells
            if c.cell_type == CellType.CODE and c.state != CellState.DONE
        ]
        assert not failed_cells, f"Cells failed to execute: {failed_cells}"

        # Verify minimum window width and right-aligned toolbar controls
        assert win.minimumWidth() == 1726
        assert win._run_all_btn.shortcut().toString() == "F5"
        assert win._run_all_shortcut_alt.key().toString() == "Ctrl+R"
        win.show()
        win.resize(2000, 900)
        qt_app.processEvents()
        assert win._theme_btn.geometry().right() > 1950
        assert win._kernel_combo.x() > win._reactive_btn.geometry().right() + 200

        # Verify DataFrame HTML output and matplotlib PNG output rendered
        table_cell = win._doc.get_cell("c-table")
        plot_cell = win._doc.get_cell("c-plot")
        assert table_cell is not None
        assert any("text/html" in o.data for o in table_cell.outputs)
        assert plot_cell is not None
        assert any("image/png" in o.data for o in plot_cell.outputs)

        # Verify theme toggle & cell insert/delete work cleanly
        win._toggle_theme()
        assert win._palette.name == "light"
        expected_demo_cells = 5
        assert len(win._doc.cells) == expected_demo_cells
        inserted = win.insert_cell_near_active(CellType.CODE)
        assert len(win._doc.cells) == expected_demo_cells + 1
        win.delete_cell(inserted.id)
        assert len(win._doc.cells) == expected_demo_cells
    finally:
        win.close()


def test_portable_settings_persisted_and_restored(qt_app, tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    fake_exe_dir = tmp_path / "portable_bundle"
    fake_exe_dir.mkdir()
    monkeypatch.delenv("BM_NOTEBOOK_SETTINGS", raising=False)
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "executable", str(fake_exe_dir / "BM-Notebook"))
    assert resolve_settings_path() == fake_exe_dir / "settings.json"

    settings_file = fake_exe_dir / "settings.json"
    win1 = MainWindow(settings_path=settings_file)
    try:
        win1.show()
        win1.resize(1860, 1020)
        win1._toggle_theme()
        win1._inspector_btn.setChecked(False)
        qt_app.processEvents()
    finally:
        win1.close()

    assert settings_file.is_file()

    win2 = MainWindow(settings_path=settings_file)
    try:
        assert win2.width() == 1860
        assert win2.height() == 1020
        assert win2._palette.name == "light"
        assert win2._inspector_btn.isChecked() is False
        assert win2._inspector.isHidden() is True
    finally:
        win2.close()
