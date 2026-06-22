"""Dashboard module for Ripper."""

from pathlib import Path
from typing import Any, Callable, Optional

from PySide6.QtWidgets import QVBoxLayout, QWidget


class DashboardManagerWidget(QWidget):
    """Main widget for managing dashboards."""

    def __init__(
        self,
        storage_dir: Path,
        parent: Optional[QWidget] = None,
        records_fn: Optional[Callable[[str, str, str], list[dict[str, Any]] | None]] = None,
    ):
        """Initialize the dashboard manager.

        Args:
            storage_dir: Directory where dashboard files are stored
            parent: Parent widget
            records_fn: Optional callable ``(spreadsheet_id, sheet_name, range_a1)
                -> list[dict] | None`` that returns already-fetched records for a
                data source range.  When provided, the dashboard uses these records
                instead of a fresh API call.
        """
        super().__init__(parent)
        self.storage_dir = storage_dir
        self._records_fn = records_fn
        self._init_ui()

    def _init_ui(self) -> None:
        """Initialize the user interface."""
        self.setWindowTitle("Dashboards")

        # Main layout
        layout = QVBoxLayout()
        self.setLayout(layout)

        # Show dashboard view by default
        from ripper.rippergui.dashboard.views.dashboard_view import DashboardView

        self.current_view = DashboardView(self.storage_dir, self, records_fn=self._records_fn)
        layout.addWidget(self.current_view)
