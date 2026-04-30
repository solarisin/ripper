"""Test widget removal functionality."""

import sys

from PySide6.QtWidgets import QApplication

from ripper.rippergui.dashboard.models.dashboard import Dashboard
from ripper.rippergui.dashboard.models.widget_types import WidgetType
from ripper.rippergui.dashboard.views.dashboard_editor import DashboardEditor


def main() -> None:
    """Test widget removal functionality."""
    print("Testing widget removal...")
    app = QApplication(sys.argv)
    app.setStyle("Fusion")

    # Create test dashboard
    dashboard = Dashboard(id="test-dashboard", name="Test Dashboard")

    # Create editor
    editor = DashboardEditor(dashboard)
    editor.setWindowTitle("Widget Removal Test")
    editor.resize(1200, 800)

    # Add some test widgets programmatically
    print("Adding test widgets...")
    editor._on_add_widget_requested(WidgetType.SPENDING_TREND, 0, 0, 2, 2)
    editor._on_add_widget_requested(WidgetType.CATEGORY_BREAKDOWN, 0, 3, 2, 2)
    editor._on_add_widget_requested(WidgetType.BUDGET_VS_ACTUAL, 3, 0, 2, 2)

    print(f"Added {len(dashboard.widgets)} widgets")
    print("Widgets in dashboard:", list(dashboard.widgets.keys()))
    print("Widgets in canvas:", list(editor.canvas.widgets.keys()))

    editor.show()
    print("Editor shown. Try clicking the 'x' button on widgets to test removal.")
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
