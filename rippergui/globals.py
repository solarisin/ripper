from enum import Enum

from PySide6.QtGui import QFont
from PySide6.QtWidgets import QApplication


# Define fonts to be used throughout the app
class Fonts:
    class FontId(Enum):
        TOOLTIP = 0

    def __init__(self):
        self._tip_font = QFont("monospace")
        self._tip_font.setStyleHint(QFont.StyleHint.Monospace)
        self._tip_font.setPointSize(9)

    def get(self, font_id: FontId):
        if font_id == self.FontId.TOOLTIP:
            return self._tip_font
        return QApplication.font()


Fonts = Fonts()
