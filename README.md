# BM::Notebook

[![License: AGPL-3.0-or-later](assets/license_AGPLv3.svg)](https://www.gnu.org/licenses/agpl-3.0.html)
[![Dual-License: AGPLv3+ / Commercial](assets/license_AGPLv3+_commercial.svg)](LICENSE)

> [Magyar dokumentáció (README_hu.md)](README_hu.md)

Native desktop, reactive, **completely JS- and browser-free** Jupyter-compatible notebook IDE built on **Python + Qt6 (PySide6)**.

## Why BM::Notebook?

1. **Zero JS / Zero Electron / Zero WebEngine**: Every surface (code editor, syntax highlighting, Markdown preview, tables, charts, reactive DAG graph) renders with native C++/Qt6 widgets.
2. **Reactive DAG Execution (No Hidden State)**:
   - Uses Python AST analysis to map each cell's definitions (`defs`) and references (`refs`).
   - Editing a cell immediately marks downstream dependents as `STALE`, and execution automatically re-runs the affected chain in **topological order**.
   - Removing a variable from a cell also cleans it up from the live kernel namespace (`globals().pop(...)`), preventing ghost state.
   - Automatically detects **multi-cell definition conflicts** and **dependency cycles**.
3. **Git-Friendly `.bm.md` Format + `.ipynb` Compatibility**:
   - The default `.bm.md` format uses clean Markdown + ```python``` fenced blocks without noisy binary output blobs — easy to read and diff in Git.
   - Standard `.ipynb` (Jupyter nbformat 4) notebooks can be opened directly and exported back to `.ipynb`.
4. **Full Jupyter Kernel Compatibility**:
   - Threaded `jupyter_client` ZMQ communication so the UI never freezes.
   - Switch between any installed Jupyter kernel (`ipykernel`, etc.); standalone release builds also include an embedded Python kernel fallback.
   - Kernel-backed `Tab` / `Ctrl+Space` code completion, interrupt (`Ctrl+I`), restart, and live variable inspector.
5. **Portable Settings**:
   - Window size, position, maximized state, splitter layout, inspector visibility, and theme (`dark`/`light`) are saved to a portable `settings.json` directly inside the application folder (next to the executable or project root).

## Running from Source

```bash
python3 -m bm_notebook examples/reactive_demo.bm.md
```

Or install in editable mode:

```bash
pip install -e . --no-build-isolation
bm-notebook examples/reactive_demo.bm.md
```

## Prebuilt Releases (Linux, Windows, macOS)

GitHub Actions automatically tests and builds standalone bundles for **Linux (`linux-x86_64`)**, **Windows (`windows-x86_64`)**, and **macOS (`macos-arm64`)** and publishes them under **GitHub Releases**.

## Keyboard Shortcuts

- `Shift+Enter`: Run cell + downstream dependents (reactive cascade) and advance to the next cell
- `Ctrl+Enter`: Run cell + downstream dependents in place
- `Alt+Enter`: Run cell and insert a new code cell below
- `Tab` / `Ctrl+Space`: Kernel-backed code completion
- `F5` / `Ctrl+R`: Run entire notebook in topological order
- `Ctrl+I`: Interrupt running kernel
- `Ctrl+B`: Toggle the right-hand Reactive Graph / Variable Inspector panel
- `Ctrl+S` / `Ctrl+O` / `Ctrl+N`: Save / Open / New notebook
