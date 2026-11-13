"""Portable application settings stored inside the application folder."""

from __future__ import annotations

import json
import logging
import os
import sys
from dataclasses import asdict, dataclass, field
from pathlib import Path

_logger = logging.getLogger(__name__)

SETTINGS_FILENAME = "settings.json"
DEFAULT_WINDOW_WIDTH = 1726
DEFAULT_WINDOW_HEIGHT = 900
DEFAULT_SPLITTER_SIZES = [1228, 420]
_SPLITTER_PANE_COUNT = 2
_DARWIN_BUNDLE_PARENTS = 3


def _is_writable_dir(directory: Path) -> bool:
    try:
        directory.mkdir(parents=True, exist_ok=True)
        probe = directory / ".bm_settings_probe"
        probe.write_text("ok", encoding="utf-8")
        probe.unlink()
    except OSError:
        return False
    return True


def portable_app_dir() -> Path:
    """Return the portable directory next to the executable (or project root when unfrozen)."""
    if getattr(sys, "frozen", False):
        exe_dir = Path(sys.executable).resolve().parent
        if (
            sys.platform == "darwin"
            and exe_dir.name == "MacOS"
            and exe_dir.parent.name == "Contents"
            and len(exe_dir.parents) >= _DARWIN_BUNDLE_PARENTS
        ):
            return exe_dir.parents[_DARWIN_BUNDLE_PARENTS - 1]
        return exe_dir
    return Path(__file__).resolve().parent.parent


def resolve_settings_path(settings_path: str | Path | None = None) -> Path:
    """Resolve the portable `settings.json` path inside the application directory."""
    if settings_path is not None:
        return Path(settings_path)
    env_override = os.environ.get("BM_NOTEBOOK_SETTINGS")
    if env_override:
        return Path(env_override)

    app_dir = portable_app_dir()
    if _is_writable_dir(app_dir):
        return app_dir / SETTINGS_FILENAME
    return Path.home() / ".config" / "bm_notebook" / SETTINGS_FILENAME


def _opt_int(raw: object) -> int | None:
    return raw if isinstance(raw, int) and not isinstance(raw, bool) else None


def _pos_int(raw: object, minimum: int, fallback: int) -> int:
    val = _opt_int(raw)
    return max(val, minimum) if val is not None else fallback


def _coerce_splitter_sizes(raw: object) -> list[int]:
    if (
        isinstance(raw, list)
        and len(raw) == _SPLITTER_PANE_COUNT
        and all(isinstance(v, int) and not isinstance(v, bool) and v > 0 for v in raw)
    ):
        return [raw[0], raw[1]]
    return list(DEFAULT_SPLITTER_SIZES)


@dataclass
class AppSettings:
    """Persisted portable IDE UI settings."""

    window_width: int = DEFAULT_WINDOW_WIDTH
    window_height: int = DEFAULT_WINDOW_HEIGHT
    window_x: int | None = None
    window_y: int | None = None
    window_maximized: bool = False
    splitter_sizes: list[int] = field(default_factory=lambda: list(DEFAULT_SPLITTER_SIZES))
    inspector_visible: bool = True
    theme: str = "dark"


def load_settings(path: Path) -> AppSettings:
    """Load portable settings from `path`, falling back cleanly on missing or invalid JSON."""
    if not path.is_file():
        return AppSettings()
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        _logger.debug("Failed to read settings %s: %s", path, exc)
        return AppSettings()

    if not isinstance(raw, dict):
        return AppSettings()

    theme_raw = raw.get("theme")
    theme = theme_raw if theme_raw in {"dark", "light"} else "dark"
    return AppSettings(
        window_width=_pos_int(raw.get("window_width"), DEFAULT_WINDOW_WIDTH, DEFAULT_WINDOW_WIDTH),
        window_height=_pos_int(raw.get("window_height"), 1, DEFAULT_WINDOW_HEIGHT),
        window_x=_opt_int(raw.get("window_x")),
        window_y=_opt_int(raw.get("window_y")),
        window_maximized=bool(raw.get("window_maximized", False)),
        splitter_sizes=_coerce_splitter_sizes(raw.get("splitter_sizes")),
        inspector_visible=bool(raw.get("inspector_visible", True)),
        theme=theme,
    )


def save_settings(settings: AppSettings, path: Path) -> None:
    """Persist portable settings cleanly as UTF-8 JSON."""
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(asdict(settings), indent=2) + "\n", encoding="utf-8")
    except OSError as exc:
        _logger.debug("Failed to save settings %s: %s", path, exc)
