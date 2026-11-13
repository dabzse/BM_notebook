"""Dark and Light modern native Qt themes and color tokens."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ThemePalette:
    name: str
    bg_window: str
    bg_surface: str
    bg_card: str
    bg_card_active: str
    bg_editor: str
    bg_gutter: str
    bg_output: str
    bg_toolbar: str
    border: str
    border_active: str
    text_primary: str
    text_secondary: str
    text_muted: str
    accent: str
    accent_hover: str
    success: str
    warning: str
    error: str
    stale: str
    running: str
    # Syntax tokens
    syn_keyword: str
    syn_builtin: str
    syn_string: str
    syn_comment: str
    syn_number: str
    syn_def: str
    syn_decorator: str
    syn_operator: str


DARK_THEME = ThemePalette(
    name="dark",
    bg_window="#111318",
    bg_surface="#171A21",
    bg_card="#1C2029",
    bg_card_active="#222734",
    bg_editor="#14171F",
    bg_gutter="#181C26",
    bg_output="#12151C",
    bg_toolbar="#161922",
    border="#2A3040",
    border_active="#5B8AF5",
    text_primary="#E6EAF2",
    text_secondary="#B2BAC9",
    text_muted="#737D94",
    accent="#5B8AF5",
    accent_hover="#749DF8",
    success="#3DD68C",
    warning="#F5B849",
    error="#F26D78",
    stale="#E5A93B",
    running="#5B8AF5",
    syn_keyword="#C792EA",
    syn_builtin="#82AAFF",
    syn_string="#A5E075",
    syn_comment="#67718A",
    syn_number="#F78C6C",
    syn_def="#FFCB6B",
    syn_decorator="#89DDFF",
    syn_operator="#89DDFF",
)

LIGHT_THEME = ThemePalette(
    name="light",
    bg_window="#F4F6FA",
    bg_surface="#FFFFFF",
    bg_card="#FFFFFF",
    bg_card_active="#F8FAFF",
    bg_editor="#F9FAFC",
    bg_gutter="#F0F3F8",
    bg_output="#F6F8FB",
    bg_toolbar="#FFFFFF",
    border="#DCE2EE",
    border_active="#2F6FED",
    text_primary="#1A202C",
    text_secondary="#4A5568",
    text_muted="#8A94A6",
    accent="#2F6FED",
    accent_hover="#1E5CD8",
    success="#169C5D",
    warning="#C77D0A",
    error="#D63649",
    stale="#C77D0A",
    running="#2F6FED",
    syn_keyword="#8B3DFF",
    syn_builtin="#0550AE",
    syn_string="#116329",
    syn_comment="#7A869A",
    syn_number="#BC4C00",
    syn_def="#953800",
    syn_decorator="#0969DA",
    syn_operator="#0550AE",
)


def build_stylesheet(p: ThemePalette) -> str:
    return f"""
    QMainWindow, QWidget#MainCanvas, QScrollArea {{
        background-color: {p.bg_window};
        color: {p.text_primary};
        font-family: "Inter", "Segoe UI", "Ubuntu", sans-serif;
        font-size: 13px;
    }}
    QToolBar {{
        background-color: {p.bg_toolbar};
        border-bottom: 1px solid {p.border};
        padding: 4px 8px;
        spacing: 6px;
    }}
    QToolButton, QPushButton {{
        background-color: {p.bg_surface};
        color: {p.text_primary};
        border: 1px solid {p.border};
        border-radius: 6px;
        padding: 5px 10px;
        font-weight: 500;
    }}
    QToolButton:hover, QPushButton:hover {{
        border-color: {p.accent};
        background-color: {p.bg_card_active};
    }}
    QToolButton:checked, QPushButton:checked {{
        background-color: {p.accent};
        color: #FFFFFF;
        border-color: {p.accent};
    }}
    QPushButton#PrimaryBtn {{
        background-color: {p.accent};
        color: #FFFFFF;
        border-color: {p.accent};
    }}
    QPushButton#PrimaryBtn:hover {{
        background-color: {p.accent_hover};
    }}
    QComboBox {{
        background-color: {p.bg_surface};
        color: {p.text_primary};
        border: 1px solid {p.border};
        border-radius: 6px;
        padding: 4px 10px;
        min-width: 120px;
    }}
    QComboBox QAbstractItemView {{
        background-color: {p.bg_card};
        color: {p.text_primary};
        border: 1px solid {p.border};
        selection-background-color: {p.accent};
    }}
    QSplitter::handle {{
        background-color: {p.border};
        width: 2px;
    }}
    QTabWidget::pane {{
        border: 1px solid {p.border};
        background-color: {p.bg_surface};
        border-radius: 6px;
    }}
    QTabBar::tab {{
        background-color: {p.bg_window};
        color: {p.text_secondary};
        border: 1px solid {p.border};
        padding: 6px 12px;
        border-top-left-radius: 6px;
        border-top-right-radius: 6px;
        margin-right: 2px;
    }}
    QTabBar::tab:selected {{
        background-color: {p.bg_surface};
        color: {p.text_primary};
        border-bottom-color: {p.bg_surface};
        font-weight: 600;
    }}
    QTableWidget {{
        background-color: {p.bg_surface};
        color: {p.text_primary};
        gridline-color: {p.border};
        border: none;
        font-size: 12px;
    }}
    QHeaderView::section {{
        background-color: {p.bg_card};
        color: {p.text_secondary};
        border: none;
        border-bottom: 1px solid {p.border};
        padding: 5px 8px;
        font-weight: 600;
    }}
    QStatusBar {{
        background-color: {p.bg_toolbar};
        color: {p.text_secondary};
        border-top: 1px solid {p.border};
        font-size: 12px;
    }}
    QScrollBar:vertical {{
        background: transparent;
        width: 10px;
        margin: 0px;
    }}
    QScrollBar::handle:vertical {{
        background: {p.border};
        min-height: 24px;
        border-radius: 5px;
    }}
    QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
        height: 0px;
    }}
    """
