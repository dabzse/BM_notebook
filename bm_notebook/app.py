"""Application entry point for BM Notebook."""

from __future__ import annotations

import argparse
import sys

from ipykernel import kernelapp
from PySide6.QtWidgets import QApplication

from bm_notebook.ui.main_window import MainWindow


def _maybe_run_embedded_ipykernel() -> int | None:
    """Allow a frozen binary to act as the embedded Python ipykernel host."""
    if sys.argv[1:2] == ["--bm-ipykernel"]:
        sys.argv = [sys.argv[0], *sys.argv[2:]]
        kernelapp.launch_new_instance()
        return 0
    if sys.argv[1:3] == ["-m", "ipykernel_launcher"]:
        sys.argv = [sys.argv[0], *sys.argv[3:]]
        kernelapp.launch_new_instance()
        return 0
    return None


def main(argv: list[str] | None = None) -> int:
    embedded_rc = _maybe_run_embedded_ipykernel()
    if embedded_rc is not None:
        return embedded_rc

    parser = argparse.ArgumentParser(
        prog="bm-notebook",
        description="Native, reactive, JS-free Jupyter-compatible notebook IDE.",
    )
    parser.add_argument(
        "file",
        nargs="?",
        default=None,
        help="Optional .bm.md or .ipynb notebook file to open on startup.",
    )
    args = parser.parse_args(argv)

    app = QApplication(sys.argv[:1])
    app.setApplicationName("BM Notebook")
    app.setOrganizationName("BM")

    win = MainWindow(initial_file=args.file)
    win.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
