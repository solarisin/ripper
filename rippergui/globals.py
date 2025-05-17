from enum import Enum, auto
from typing import Dict, Optional, Union

from PySide6.QtGui import QFont
from PySide6.QtWidgets import QApplication


# Define fonts to be used throughout the app
class FontId(Enum):
    """Font identifiers."""

    NORMAL = auto()
    BOLD = auto()
    ITALIC = auto()
    TOOLTIP = auto()


class FontManager:
    """Global font storage."""

    _instance: Optional["FontManager"] = None
    _fonts: Dict[FontId, str] = {}

    def __new__(cls) -> "FontManager":
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._fonts = {
                FontId.NORMAL: "Segoe UI",
                FontId.BOLD: "Segoe UI Bold",
                FontId.ITALIC: "Segoe UI Italic",
                FontId.TOOLTIP: "Consolas",
            }
        return cls._instance

    def get(self, font_id: FontId) -> Union[QFont, str]:
        """Get a font."""
        if font_id in self._fonts:
            return self._fonts[font_id]
        return QApplication.font()

    def set(self, font_id: FontId, font: str) -> None:
        """Set a font."""
        self._fonts[font_id] = font


# Global font manager instance
fonts = FontManager()


def get_font(font_id: FontId) -> Union[QFont, str]:
    """Get a font by ID."""
    if font_id in fonts._fonts:
        return fonts._fonts[font_id]
    return QApplication.font()
