"""Tests for the FontManager singleton (#38)."""

import pytest
from PySide6.QtGui import QFont
from PySide6.QtWidgets import QApplication

from ripper.rippergui.fonts import FontId, FontManager


@pytest.mark.qt
class TestFontManager:
    """FontManager.get() must return a QFont usable directly with setFont() (#38)."""

    def test_get_returns_qfont_with_configured_family(self, qtbot):
        font = FontManager().get(FontId.TOOLTIP)
        assert isinstance(font, QFont)
        assert font.family() == "Consolas"

    def test_get_unset_role_falls_back_to_application_font(self, qtbot):
        manager = FontManager()
        original = manager._fonts.pop(FontId.NORMAL, None)
        try:
            font = manager.get(FontId.NORMAL)
            assert isinstance(font, QFont)
            assert font.family() == QApplication.font().family()
        finally:
            if original is not None:
                manager.set(FontId.NORMAL, original)

    def test_set_overrides_family(self, qtbot):
        manager = FontManager()
        original = manager.get(FontId.BOLD).family()
        try:
            manager.set(FontId.BOLD, "Arial")
            result = manager.get(FontId.BOLD)
            assert isinstance(result, QFont)
            assert result.family() == "Arial"
        finally:
            manager.set(FontId.BOLD, original)

    def test_is_singleton(self):
        assert FontManager() is FontManager()
