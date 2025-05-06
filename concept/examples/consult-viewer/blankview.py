from PySide6.QtWidgets import QWidget, QLabel
from dockutils import DockableView

class BlankView(QWidget, DockableView):
    def initial_expanded_size(self) -> int:
        return 20

    def __init__(self, parent=None):
        super().__init__(parent)
        label = QLabel(self)
        label.setText("BlankView")

