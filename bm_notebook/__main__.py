"""Allow running via `python -m bm_notebook`."""

from bm_notebook.app import main

if __name__ == "__main__":
    raise SystemExit(main())
