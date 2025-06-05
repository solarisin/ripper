"""Main application window for the financial dashboard."""

from pathlib import Path
from typing import Optional

from PySide6.QtCore import QSize
from PySide6.QtGui import QAction, QCloseEvent
from PySide6.QtWidgets import (
    QMainWindow,
    QMessageBox,
    QTabWidget,
    QToolBar,
    QVBoxLayout,
    QWidget,
)

from ripper.rippergui.dashboard.models import Dashboard, DashboardManager
from ripper.rippergui.dashboard.views.dashboard_editor import DashboardEditor
from ripper.rippergui.dashboard.views.financial_dashboard import FinancialDashboardView


class MainWindow(QMainWindow):
    """Main application window for the financial dashboard."""

    def __init__(self, parent: Optional[QWidget] = None):
        """Initialize the main window."""
        super().__init__(parent)

        # Initialize dashboard manager
        self.dashboard_manager = DashboardManager(Path.home() / ".ripper" / "dashboards")
        self.current_dashboard: Optional[Dashboard] = None

        # Initialize UI
        self._init_ui()

        # Create a default dashboard if none exists
        if not self.dashboard_manager.get_all_dashboards():
            self._create_default_dashboard()
        # Load the first dashboard
        self._load_dashboard()

    def _init_ui(self) -> None:
        """Initialize the user interface."""
        self.setWindowTitle("Financial Dashboard")
        self.setMinimumSize(1024, 768)

        # Create central widget
        central_widget = QWidget()
        self.setCentralWidget(central_widget)

        # Main layout
        layout = QVBoxLayout()
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        central_widget.setLayout(layout)

        # Create tab widget
        self.tab_widget = QTabWidget()
        self.tab_widget.setTabsClosable(True)
        self.tab_widget.tabCloseRequested.connect(self._on_tab_close_requested)
        layout.addWidget(self.tab_widget)

        # Create toolbar
        self._create_toolbar()

        # Create status bar
        self.statusBar().showMessage("Ready")

    def _create_toolbar(self) -> None:
        """Create the application toolbar."""
        toolbar = QToolBar("Main Toolbar")
        toolbar.setIconSize(QSize(16, 16))
        self.addToolBar(toolbar)

        # New dashboard action
        new_action = QAction("New Dashboard", self)
        new_action.triggered.connect(self._on_new_dashboard)
        toolbar.addAction(new_action)

        # Open dashboard action
        open_action = QAction("Open Dashboard", self)
        open_action.triggered.connect(self._on_open_dashboard)
        toolbar.addAction(open_action)

        # Save dashboard action
        self.save_action = QAction("Save", self)
        self.save_action.triggered.connect(self._on_save_dashboard)
        self.save_action.setEnabled(False)
        toolbar.addAction(self.save_action)

        toolbar.addSeparator()

        # Edit dashboard action
        self.edit_action = QAction("Edit", self)
        self.edit_action.triggered.connect(self._on_edit_dashboard)
        self.edit_action.setEnabled(False)
        toolbar.addAction(self.edit_action)

        # Refresh action
        refresh_action = QAction("Refresh", self)
        refresh_action.triggered.connect(self._on_refresh_dashboard)
        toolbar.addAction(refresh_action)

    def _create_default_dashboard(self) -> None:
        """Create a default dashboard with some example widgets."""
        dashboard = self.dashboard_manager.create_dashboard(
            "My Financial Dashboard", "A sample financial dashboard with common widgets."
        )

        # In a real app, you would add some default widgets here

        # Save the dashboard
        self.dashboard_manager.save_dashboard(dashboard)

    def _load_dashboard(self, dashboard_id: Optional[str] = None) -> None:
        """Load a dashboard by ID.

        Args:
            dashboard_id: ID of the dashboard to load, or None to load the first one
        """
        dashboard: Optional[Dashboard]
        if not dashboard_id:
            dashboards = self.dashboard_manager.get_all_dashboards()
            if not dashboards:
                return
            dashboard = dashboards[0]
        else:
            dashboard = self.dashboard_manager.get_dashboard(dashboard_id)
            if dashboard is None:
                QMessageBox.warning(self, "Error", f"Could not load dashboard with ID {dashboard_id}")
                return

        # At this point dashboard is guaranteed to be not None
        self.current_dashboard = dashboard  # type: ignore[assignment]
        self._update_ui()

    def _update_ui(self) -> None:
        """Update the UI to reflect the current state."""
        if not self.current_dashboard:
            return

        # Clear existing tabs
        while self.tab_widget.count() > 0:
            self.tab_widget.removeTab(0)

        # Add a tab for the current dashboard
        dashboard_view = FinancialDashboardView(self.current_dashboard)
        dashboard_view.edit_requested.connect(self._on_edit_dashboard)
        dashboard_view.refresh_requested.connect(self._on_refresh_dashboard)

        self.tab_widget.addTab(dashboard_view, self.current_dashboard.name)

        # Update actions
        self.save_action.setEnabled(True)
        self.edit_action.setEnabled(True)

        # Update status bar
        self.statusBar().showMessage(f"Loaded dashboard: {self.current_dashboard.name}")

    def _on_new_dashboard(self) -> None:
        """Handle new dashboard action."""
        # In a real app, you would show a dialog to enter dashboard details
        dashboard = self.dashboard_manager.create_dashboard("New Dashboard")
        self.current_dashboard = dashboard
        self._update_ui()

    def _on_open_dashboard(self) -> None:
        """Handle open dashboard action."""
        # In a real app, you would show a dialog to select a dashboard
        dashboards = self.dashboard_manager.get_all_dashboards()
        if not dashboards:
            QMessageBox.information(self, "No Dashboards", "No dashboards found.")
            return

        # For now, just load the first dashboard
        self._load_dashboard(dashboards[0].id)

    def _on_save_dashboard(self) -> None:
        """Handle save dashboard action."""
        if not self.current_dashboard:
            return

        try:
            self.dashboard_manager.save_dashboard(self.current_dashboard)
            self.statusBar().showMessage(f"Saved dashboard: {self.current_dashboard.name}", 3000)
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to save dashboard: {str(e)}")

    def _on_edit_dashboard(self) -> None:
        """Handle edit dashboard action."""
        if not self.current_dashboard:
            return

        # Create and show the dashboard editor
        editor = DashboardEditor(self.current_dashboard)
        # TODO: Consider making DashboardEditor a QDialog for modal editing and result handling
        editor.show()  # Non-modal for now
        # If modal dialog support is needed, refactor DashboardEditor to inherit QDialog and implement exec()

    def _on_refresh_dashboard(self) -> None:
        """Handle refresh dashboard action."""
        current_widget = self.tab_widget.currentWidget()
        if isinstance(current_widget, FinancialDashboardView):
            current_widget.refresh()
            self.statusBar().showMessage("Dashboard refreshed", 2000)

    def _on_tab_close_requested(self, index: int) -> None:
        """Handle tab close request."""
        widget = self.tab_widget.widget(index)
        if widget:
            widget.deleteLater()
        self.tab_widget.removeTab(index)

    def closeEvent(self, event: QCloseEvent) -> None:
        """Handle window close event."""
        # Save any unsaved changes
        try:
            if self.current_dashboard:
                self.dashboard_manager.save_dashboard(self.current_dashboard)
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to save dashboard: {str(e)}")

        event.accept()
