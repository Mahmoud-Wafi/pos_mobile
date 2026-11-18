"""Bundled Lucide SVG icons (ISC licence, see assets/icons/LICENSE-lucide.txt), tinted on demand."""
from __future__ import annotations

from functools import lru_cache

from PySide6.QtCore import QByteArray, QSize, Qt
from PySide6.QtGui import QIcon, QImage, QPainter, QPixmap
from PySide6.QtSvg import QSvgRenderer

from app.core.paths import resource_dir
from app.ui.design.tokens import COLORS as C


@lru_cache(maxsize=256)
def _svg_bytes(name: str, color: str) -> bytes:
    path = resource_dir() / "assets" / "icons" / f"{name}.svg"
    return path.read_text(encoding="utf-8").replace("currentColor", color).encode("utf-8")


@lru_cache(maxsize=512)
def pixmap(name: str, color: str = C["text_muted"], size: int = 20) -> QPixmap:
    renderer = QSvgRenderer(QByteArray(_svg_bytes(name, color)))
    img = QImage(size * 2, size * 2, QImage.Format_ARGB32_Premultiplied)
    img.fill(Qt.transparent)
    p = QPainter(img)
    renderer.render(p)
    p.end()
    pm = QPixmap.fromImage(img)
    pm.setDevicePixelRatio(2)
    return pm


def icon(name: str, color: str = C["text_muted"], active_color: str | None = None, size: int = 20) -> QIcon:
    """QIcon with a normal and (optional) active tint."""
    ic = QIcon()
    ic.addPixmap(pixmap(name, color, size), QIcon.Normal, QIcon.Off)
    ic.addPixmap(pixmap(name, active_color or color, size), QIcon.Normal, QIcon.On)
    ic.addPixmap(pixmap(name, C["text_disabled"], size), QIcon.Disabled, QIcon.Off)
    return ic


ICON_SIZE = QSize(20, 20)
