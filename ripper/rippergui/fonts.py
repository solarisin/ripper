"""
Font management utilities for the ripper application.

This module provides a FontId enum for font roles and a singleton FontManager
for global font storage and retrieval throughout the application.
"""

from enum import Enum, auto

from beartype.typing import Dict, Optional
from PySide6.QtGui import QFont
from PySide6.QtWidgets import QApplication

# Define fonts to be used throughout the app


class FontId(Enum):
    """
    Font identifiers for different font roles in the application.
    """

    NORMAL = auto()
    BOLD = auto()
    ITALIC = auto()
    TOOLTIP = auto()


class FontManager:
    """
    Singleton for global font storage and retrieval.

    Provides methods to get and set fonts for different roles (FontId) across the application.
    """

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

    def get(self, font_id: FontId) -> QFont:
        """
        Get the QFont for the given font role.

        Callers pass the result directly to ``setFont(...)``, which requires a ``QFont`` (PySide6
        does not coerce a family-name string), so this builds one from the configured family.

        Args:
            font_id (FontId): The font role identifier.

        Returns:
            QFont: A font for this role, built from its configured family. Falls back to the
            application's default font family when the role is unset.
        """
        family = self._fonts.get(font_id) or QApplication.font().family()
        return QFont(family)

    def set(self, font_id: FontId, font: str) -> None:
        """
        Set the font family name for the given font role.

        Args:
            font_id (FontId): The font role identifier.
            font (str): The font family name to set.
        """
        self._fonts[font_id] = font
