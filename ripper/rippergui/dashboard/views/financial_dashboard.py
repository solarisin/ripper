"""Financial dashboard view implementation."""

from pathlib import Path
from typing import Optional

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from ripper.rippergui.dashboard.models import Dashboard
from ripper.rippergui.dashboard.views.dashboard_view import DashboardView


class FinancialDashboardView(QWidget):
    """Financial dashboard view that displays financial widgets."""

    edit_requested = Signal()
    refresh_requested = Signal()

    def __init__(self, dashboard: Dashboard, parent: Optional[QWidget] = None):
        """Initialize the financial dashboard view.

        Args:
            dashboard: The dashboard model to display
            parent: Parent widget
        """
        super().__init__(parent)
        self.dashboard = dashboard
        self._init_ui()

    def _init_ui(self) -> None:
        """Initialize the user interface."""
        # Main layout
        layout = QVBoxLayout()
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(10)
        self.setLayout(layout)

        # Header
        header = QWidget()
        header_layout = QHBoxLayout()
        header_layout.setContentsMargins(0, 0, 0, 0)
        header.setLayout(header_layout)

        title = QLabel(self.dashboard.name)
        title.setStyleSheet("font-size: 18px; font-weight: bold;")
        header_layout.addWidget(title)

        # Action buttons
        btn_layout = QHBoxLayout()
        btn_layout.setSpacing(5)

        refresh_btn = QPushButton("Refresh")
        refresh_btn.clicked.connect(self.refresh_requested.emit)
        btn_layout.addWidget(refresh_btn)

        edit_btn = QPushButton("Edit")
        edit_btn.clicked.connect(self.edit_requested.emit)
        btn_layout.addWidget(edit_btn)

        header_layout.addLayout(btn_layout)

        layout.addWidget(header)

        # Dashboard view - create a temporary directory for the dashboard manager
        # or pass the dashboard directly
        import tempfile

        temp_dir = Path(tempfile.gettempdir()) / "ripper_dashboard_temp"
        temp_dir.mkdir(exist_ok=True)
        self.dashboard_view = DashboardView(temp_dir)
        # Set the current dashboard directly
        self.dashboard_view._set_current_dashboard(self.dashboard)
        layout.addWidget(self.dashboard_view)

    def refresh(self) -> None:
        """Refresh the dashboard data."""
        self.dashboard_view.refresh()
