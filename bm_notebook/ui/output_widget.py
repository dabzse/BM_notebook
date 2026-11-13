"""Native Qt output widgets (PNG/JPEG/SVG images, HTML tables, ANSI stdout/tracebacks)."""

from __future__ import annotations

import base64
import html

from PySide6.QtCore import QByteArray, Qt
from PySide6.QtGui import QAction, QImage, QPainter, QPixmap
from PySide6.QtSvg import QSvgRenderer
from PySide6.QtWidgets import (
    QApplication,
    QFileDialog,
    QLabel,
    QMenu,
    QTextBrowser,
    QVBoxLayout,
    QWidget,
)

from bm_notebook.model import CellOutput

from .ansi import ansi_to_html, strip_ansi
from .theme import ThemePalette

_MIN_WIDGET_WIDTH_FOR_SCALE = 50
_TRANSPARENT_BG_STYLE = "background: transparent;"

class _ImageLabel(QLabel):
    """Pixmap label with crisp scaling and right-click Copy/Save Image menu."""

    def __init__(self, pixmap: QPixmap, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._orig_pixmap = pixmap
        self.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop)
        self.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.customContextMenuRequested.connect(self._show_menu)
        self._update_scaled_pixmap()

    def _update_scaled_pixmap(self) -> None:
        if self._orig_pixmap.isNull():
            return
        max_w = (
            max(360, self.width() - 8)
            if self.width() > _MIN_WIDGET_WIDTH_FOR_SCALE
            else 780
        )
        if self._orig_pixmap.width() > max_w:
            scaled = self._orig_pixmap.scaledToWidth(
                max_w, Qt.TransformationMode.SmoothTransformation
            )
            self.setPixmap(scaled)
        else:
            self.setPixmap(self._orig_pixmap)

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self._update_scaled_pixmap()

    def _show_menu(self, pos) -> None:
        menu = QMenu(self)
        copy_act = QAction("Copy Image", self)
        save_act = QAction("Save Image As...", self)
        copy_act.triggered.connect(lambda: QApplication.clipboard().setPixmap(self._orig_pixmap))
        save_act.triggered.connect(self._save_image)
        menu.addAction(copy_act)
        menu.addAction(save_act)
        menu.exec(self.mapToGlobal(pos))

    def _save_image(self) -> None:
        path, _ = QFileDialog.getSaveFileName(
            self, "Save Output Image", "plot.png", "PNG Image (*.png);;JPEG (*.jpg)"
        )
        if path:
            self._orig_pixmap.save(path)


class _AutoTextBrowser(QTextBrowser):
    """Read-only auto-sizing QTextBrowser for streams, tracebacks, and HTML tables."""

    def __init__(self, max_height: int = 380, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._max_height = max_height
        self.setOpenExternalLinks(True)
        self.setFrameShape(QTextBrowser.Shape.NoFrame)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.document().contentsChanged.connect(self._adjust_height)

    def _adjust_height(self) -> None:
        self.document().setTextWidth(max(200, self.viewport().width()))
        doc_h = int(self.document().size().height()) + 12
        self.setFixedHeight(max(28, min(doc_h, self._max_height)))

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self._adjust_height()


class CellOutputContainer(QWidget):
    """Displays all outputs for a cell cleanly with native Qt widgets."""

    def __init__(self, palette: ThemePalette, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._palette = palette
        self._outputs: list[CellOutput] = []
        self._layout = QVBoxLayout(self)
        self._layout.setContentsMargins(8, 6, 8, 6)
        self._layout.setSpacing(6)
        self.setVisible(False)
        self.apply_palette(palette)

    def apply_palette(self, palette: ThemePalette) -> None:
        self._palette = palette
        self.setStyleSheet(
            f"""
            CellOutputContainer {{
                background-color: {palette.bg_output};
                border: 1px solid {palette.border};
                border-radius: 6px;
            }}
            """
        )
        if self._outputs:
            self.set_outputs(self._outputs)

    def clear(self) -> None:
        self._outputs = []
        while self._layout.count():
            item = self._layout.takeAt(0)
            w = item.widget()
            if w is not None:
                w.deleteLater()
        self.setVisible(False)

    def append_output(self, out: CellOutput) -> None:
        # Coalesce consecutive stdout/stderr stream chunks
        if (
            out.output_type == "stream"
            and self._outputs
            and self._outputs[-1].output_type == "stream"
            and self._outputs[-1].name == out.name
        ):
            self._outputs[-1].text += out.text
            self.set_outputs(list(self._outputs))
            return
        self._outputs.append(out)
        self._render_single(out)
        self.setVisible(True)

    def set_outputs(self, outputs: list[CellOutput]) -> None:
        self.clear()
        coalesced: list[CellOutput] = []
        for out in outputs:
            if (
                out.output_type == "stream"
                and coalesced
                and coalesced[-1].output_type == "stream"
                and coalesced[-1].name == out.name
            ):
                coalesced[-1] = CellOutput(
                    output_type="stream",
                    name=out.name,
                    text=coalesced[-1].text + out.text,
                )
            else:
                coalesced.append(out)
        self._outputs = coalesced
        for out in coalesced:
            self._render_single(out)
        self.setVisible(bool(coalesced))

    def _render_single(self, out: CellOutput) -> None:
        if out.output_type == "stream":
            self._render_stream(out)
            return
        if out.output_type == "error":
            self._render_error(out)
            return
        self._render_mime_bundle(out.data)

    def _make_pre_browser(
        self,
        body_html: str,
        color: str,
        max_height: int,
        extra_style: str = "",
    ) -> _AutoTextBrowser:
        browser = _AutoTextBrowser(max_height=max_height, parent=self)
        browser.setHtml(
            f'<pre style="margin:0; font-family:monospace; font-size:12px; '
            f'color:{color};">{body_html}</pre>'
        )
        browser.setStyleSheet(extra_style or _TRANSPARENT_BG_STYLE)
        return browser

    def _render_stream(self, out: CellOutput) -> None:
        p = self._palette
        fg = p.error if out.name == "stderr" else p.text_primary
        body_html = ansi_to_html(out.text, dark=(p.name == "dark")).replace("\n", "<br>")
        self._layout.addWidget(self._make_pre_browser(body_html, fg, max_height=320))

    def _render_error(self, out: CellOutput) -> None:
        p = self._palette
        tb_text = "\n".join(out.traceback) if out.traceback else f"{out.ename}: {out.evalue}"
        body_html = ansi_to_html(tb_text, dark=(p.name == "dark")).replace("\n", "<br>")
        border_style = f"{_TRANSPARENT_BG_STYLE} border-left: 3px solid {p.error}; padding-left: 8px;"
        self._layout.addWidget(
            self._make_pre_browser(body_html, p.error, max_height=360, extra_style=border_style)
        )

    def _render_mime_bundle(self, data: dict[str, str]) -> None:
        if self._try_render_raster_image(data) or self._try_render_svg(data):
            return
        if self._try_render_html(data):
            return
        self._try_render_plain_text(data)

    def _try_render_raster_image(self, data: dict[str, str]) -> bool:
        for mime in ("image/png", "image/jpeg"):
            if mime not in data:
                continue
            try:
                raw_bytes = base64.b64decode(data[mime])
                img = QImage.fromData(raw_bytes)
                if not img.isNull():
                    self._layout.addWidget(_ImageLabel(QPixmap.fromImage(img), self))
                    return True
            except (ValueError, RuntimeError):
                continue
        return False

    def _try_render_svg(self, data: dict[str, str]) -> bool:
        if "image/svg+xml" not in data:
            return False
        try:
            svg_bytes = QByteArray(data["image/svg+xml"].encode("utf-8"))
            renderer = QSvgRenderer(svg_bytes)
            if not renderer.isValid():
                return False
            sz = renderer.defaultSize()
            w = max(240, min(840, sz.width() if sz.width() > 0 else 600))
            h = max(120, min(640, sz.height() if sz.height() > 0 else 400))
            pix = QPixmap(w, h)
            pix.fill(Qt.GlobalColor.transparent)
            painter = QPainter(pix)
            renderer.render(painter)
            painter.end()
            self._layout.addWidget(_ImageLabel(pix, self))
        except RuntimeError:
            return False
        else:
            return True

    def _try_render_html(self, data: dict[str, str]) -> bool:
        html_body = data.get("text/html", "")
        if not html_body.strip():
            return False
        p = self._palette
        browser = _AutoTextBrowser(max_height=400, parent=self)
        styled = f"""
        <style>
            body {{ color: {p.text_primary}; font-family: sans-serif; font-size: 12px; margin: 0; }}
            table {{ border-collapse: collapse; margin: 4px 0; }}
            th, td {{ border: 1px solid {p.border}; padding: 4px 8px; text-align: left; }}
            th {{ background-color: {p.bg_card}; color: {p.text_primary}; font-weight: 600; }}
            tr:nth-child(even) td {{ background-color: {p.bg_surface}; }}
            pre, code {{ font-family: monospace; }}
        </style>
        {html_body}
        """
        browser.setHtml(styled)
        browser.setStyleSheet(_TRANSPARENT_BG_STYLE)
        self._layout.addWidget(browser)
        return True

    def _try_render_plain_text(self, data: dict[str, str]) -> None:
        if "text/plain" not in data:
            return
        p = self._palette
        escaped = html.escape(strip_ansi(data["text/plain"])).replace("\n", "<br>")
        self._layout.addWidget(self._make_pre_browser(escaped, p.text_primary, max_height=320))
