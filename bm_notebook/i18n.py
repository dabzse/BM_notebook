"""Internationalization (i18n) translation catalog and language manager for BM::Notebook."""

from __future__ import annotations

from typing import Any

SUPPORTED_LANGUAGES = ("hu", "en")
DEFAULT_LANGUAGE = "hu"


class _LanguageState:
    current: str = DEFAULT_LANGUAGE


_state = _LanguageState()

TRANSLATIONS: dict[str, dict[str, str]] = {
    # Toolbar actions & buttons
    "toolbar_title": {
        "hu": "Fő eszköztár",
        "en": "Main Toolbar",
    },
    "action_new": {
        "hu": "Új",
        "en": "New",
    },
    "action_open": {
        "hu": "Megnyitás",
        "en": "Open",
    },
    "action_save": {
        "hu": "Mentés",
        "en": "Save",
    },
    "action_export": {
        "hu": "Export .ipynb",
        "en": "Export .ipynb",
    },
    "btn_add_python": {
        "hu": "+ Python",
        "en": "+ Python",
    },
    "btn_add_markdown": {
        "hu": "+ Markdown",
        "en": "+ Markdown",
    },
    "btn_run_stale": {
        "hu": "▶ Elavultak",
        "en": "▶ Stale",
    },
    "tooltip_run_stale": {
        "hu": "Függőben lévő (STALE / IDLE) cellák futtatása topologikus sorrendben",
        "en": "Run pending (STALE / IDLE) cells in topological order",
    },
    "btn_run_all": {
        "hu": "▶▶ Mind futtatása",
        "en": "▶▶ Run All",
    },
    "tooltip_run_all": {
        "hu": "Teljes notebook futtatása topologikus sorrendben (F5 / Ctrl+R)",
        "en": "Run entire notebook in topological order (F5 / Ctrl+R)",
    },
    "btn_interrupt": {
        "hu": "■ Megszakítás",
        "en": "■ Interrupt",
    },
    "btn_restart": {
        "hu": "↻ Újraindítás",
        "en": "↻ Restart",
    },
    "reactive_on": {
        "hu": "⚡ Reaktív: BE",
        "en": "⚡ Reactive: ON",
    },
    "reactive_off": {
        "hu": "⚡ Reaktív: KI",
        "en": "⚡ Reactive: OFF",
    },
    "tooltip_reactive": {
        "hu": "Automatikus függőségi kaszkád cella futtatáskor",
        "en": "Automatic dependency cascade on cell execution",
    },
    "lbl_kernel": {
        "hu": "Kernel: ",
        "en": "Kernel: ",
    },
    "btn_inspector": {
        "hu": "Gráf / Változók",
        "en": "Graph / Variables",
    },
    "tooltip_inspector": {
        "hu": "Reaktív gráf és változó-vizsgáló panel ki/be (Ctrl+B)",
        "en": "Toggle Reactive Graph & Variable Inspector panel (Ctrl+B)",
    },
    "btn_theme": {
        "hu": "☀/🌙 Téma",
        "en": "☀/🌙 Theme",
    },
    "btn_lang": {
        "hu": "🌐 HU",
        "en": "🌐 EN",
    },
    "tooltip_lang": {
        "hu": "Nyelv váltása (Magyar / English)",
        "en": "Switch language (Magyar / English)",
    },

    # Kernel & Status bar
    "kernel_starting": {
        "hu": "Indítás…",
        "en": "Starting…",
    },
    "kernel_status_starting": {
        "hu": "Indítás…",
        "en": "Starting…",
    },
    "kernel_status_idle": {
        "hu": "Kész (Idle)",
        "en": "Ready (Idle)",
    },
    "kernel_status_busy": {
        "hu": "Fut (Busy)",
        "en": "Busy",
    },
    "kernel_status_dead": {
        "hu": "Leállt",
        "en": "Stopped",
    },
    "kernel_ready": {
        "hu": "Kész",
        "en": "Ready",
    },
    "kernel_error_prefix": {
        "hu": "Kernel hiba: {message}",
        "en": "Kernel error: {message}",
    },
    "status_mode_reactive": {
        "hu": "Reaktív",
        "en": "Reactive",
    },
    "status_mode_manual": {
        "hu": "Manuális",
        "en": "Manual",
    },
    "status_code_cells": {
        "hu": "{mode} • {code_count}/{total_count} kód cella{extra}",
        "en": "{mode} • {code_count}/{total_count} code cells{extra}",
    },
    "status_extra_stale": {
        "hu": ", {count} elavult",
        "en": ", {count} stale",
    },
    "status_extra_conflicts": {
        "hu": ", {count} ütközés",
        "en": ", {count} conflict(s)",
    },
    "status_extra_cycles": {
        "hu": ", {count} ciklus",
        "en": ", {count} cycle(s)",
    },

    # Cell widget
    "tooltip_cell_type": {
        "hu": "Váltás Python / Markdown cella között",
        "en": "Switch between Python / Markdown cell",
    },
    "tooltip_cell_run": {
        "hu": "Futtatás + reaktív kaszkád (Shift+Enter)",
        "en": "Run + reactive cascade (Shift+Enter)",
    },
    "tooltip_cell_up": {
        "hu": "Cella feljebb",
        "en": "Move cell up",
    },
    "tooltip_cell_down": {
        "hu": "Cella lejjebb",
        "en": "Move cell down",
    },
    "tooltip_cell_collapse": {
        "hu": "Kimenet összecsukása / kinyitása",
        "en": "Collapse / expand output",
    },
    "tooltip_cell_delete": {
        "hu": "Cella törlése",
        "en": "Delete cell",
    },
    "cell_conflict_warning": {
        "hu": "⚠ Több cellában definiált szimbólum(ok): {syms}",
        "en": "⚠ Symbol(s) defined in multiple cells: {syms}",
    },

    # Inspector panel
    "inspector_tab_graph": {
        "hu": "Reaktív Gráf",
        "en": "Reactive Graph",
    },
    "inspector_tab_vars": {
        "hu": "Változók",
        "en": "Variables",
    },
    "inspector_summary": {
        "hu": "Reaktív DAG • {code_count} kód cella • {edge_count} él{suffix}",
        "en": "Reactive DAG • {code_count} code cells • {edge_count} edges{suffix}",
    },
    "inspector_warn_conflict": {
        "hu": "{count} ütközés",
        "en": "{count} conflict(s)",
    },
    "inspector_warn_cycle": {
        "hu": "{count} ciklus",
        "en": "{count} cycle(s)",
    },
    "inspector_col_name": {
        "hu": "Név",
        "en": "Name",
    },
    "inspector_col_type": {
        "hu": "Típus",
        "en": "Type",
    },
    "inspector_col_value": {
        "hu": "Érték / Méret",
        "en": "Value / Size",
    },
    "inspector_col_cell": {
        "hu": "Cella",
        "en": "Cell",
    },
    "dag_node_title": {
        "hu": "#{index} Cella",
        "en": "Cell #{index}",
    },

    # Dialogs & Messages
    "dialog_open_title": {
        "hu": "Notebook megnyitása",
        "en": "Open Notebook",
    },
    "dialog_open_filter": {
        "hu": "BM & Jupyter Notebooks (*.bm.md *.md *.ipynb);;Minden fájl (*)",
        "en": "BM & Jupyter Notebooks (*.bm.md *.md *.ipynb);;All Files (*)",
    },
    "error_open_title": {
        "hu": "Megnyitási hiba",
        "en": "Open Error",
    },
    "error_open_msg": {
        "hu": "Nem sikerült megnyitni:\n{error}",
        "en": "Failed to open:\n{error}",
    },
    "dialog_save_title": {
        "hu": "Notebook mentése",
        "en": "Save Notebook",
    },
    "dialog_save_filter": {
        "hu": "BM Markdown Notebook (*.bm.md);;Jupyter Notebook (*.ipynb)",
        "en": "BM Markdown Notebook (*.bm.md);;Jupyter Notebook (*.ipynb)",
    },
    "error_save_title": {
        "hu": "Mentési hiba",
        "en": "Save Error",
    },
    "error_save_msg": {
        "hu": "Nem sikerült menteni:\n{error}",
        "en": "Failed to save:\n{error}",
    },
    "dialog_export_title": {
        "hu": "Exportálás Jupyter (.ipynb) formátumba",
        "en": "Export to Jupyter (.ipynb) format",
    },
    "dialog_export_filter": {
        "hu": "Jupyter Notebook (*.ipynb)",
        "en": "Jupyter Notebook (*.ipynb)",
    },
    "error_export_title": {
        "hu": "Export hiba",
        "en": "Export Error",
    },
    "error_export_msg": {
        "hu": "Nem sikerült exportálni:\n{error}",
        "en": "Failed to export:\n{error}",
    },
    "warn_cycle_title": {
        "hu": "Függőségi ciklus",
        "en": "Dependency Cycle",
    },
    "warn_cycle_msg": {
        "hu": (
            "A cella kölcsönös (ciklikus) változó-függőségben van más cellákkal. "
            "Szüntesd meg a ciklust a reaktív futtatáshoz."
        ),
        "en": (
            "This cell has circular variable dependencies with other cells. "
            "Resolve the cycle for reactive execution."
        ),
    },
    "warn_cycle_detected_title": {
        "hu": "Függőségi ciklus észlelve",
        "en": "Dependency Cycle Detected",
    },
    "warn_cycle_detected_msg": {
        "hu": "Néhány cella függőségi ciklusban van, ezek kihagyásra kerülnek.",
        "en": "Some cells have circular dependencies and will be skipped.",
    },
    "embedded_kernel_display_name": {
        "hu": "Python (beépített)",
        "en": "Python (embedded)",
    },
    "untitled_doc": {
        "hu": "Névtelen",
        "en": "Untitled",
    },
}


def get_current_language() -> str:
    """Return currently active language code ('hu' or 'en')."""
    return _state.current


def set_current_language(lang: str) -> None:
    """Set active language code ('hu' or 'en')."""
    if lang in SUPPORTED_LANGUAGES:
        _state.current = lang


def t(key: str, lang: str | None = None, **kwargs: Any) -> str:
    """Translate `key` into target language with optional formatting parameters."""
    target_lang = lang if lang in SUPPORTED_LANGUAGES else _state.current
    entry = TRANSLATIONS.get(key)
    if entry is None:
        template = key
    else:
        template = entry.get(target_lang) or entry.get(DEFAULT_LANGUAGE) or entry.get("en") or key
    if kwargs:
        try:
            return template.format(**kwargs)
        except Exception:
            return template
    return template
