"""
Main application window for the ripper application.

This module provides MainView, a QMainWindow subclass that manages the main UI layout, menus, toolbars, actions,
authentication state, and UI updates for the ripper application.
"""

from pathlib import Path

import PySide6QtAds as ads  # type: ignore[import-untyped]
from loguru import logger
from PySide6.QtCore import QSettings, QSize, QThread, Signal
from PySide6.QtGui import QAction, QCloseEvent, QIcon, QKeySequence, Qt
from PySide6.QtWidgets import (
    QApplication,
    QDialog,
    QGridLayout,
    QLabel,
    QMainWindow,
    QMenu,
    QMessageBox,
    QProgressDialog,
    QToolBar,
    QToolTip,
    QVBoxLayout,
    QWidget,
)

import ripper.ripperlib.sheets_backend as sheets_backend
from ripper.rippergui import table_view
from ripper.rippergui.datasource_list_widget import DataSourceListWidget
from ripper.rippergui.fonts import FontId, FontManager
from ripper.rippergui.oauth_client_config_view import AuthView
from ripper.rippergui.sheets_selection_view import SheetsSelectionDialog
from ripper.ripperlib.auth import AuthInfo, AuthManager, AuthState
from ripper.ripperlib.database import Db
from ripper.ripperlib.defs import LoadSource, get_app_data_dir


class _DataFetchWorker(QThread):
    """
    Background worker that authenticates with Google and fetches sheet data.

    Used by :class:`MainView` to keep network I/O off the UI thread when loading
    or refreshing a data source.

    Signals:
        finished (list, list): Emitted with ``(sheet_data, range_sources)`` on
            success.  ``sheet_data`` is a 2-D list of cell values; ``range_sources``
            is the list of ``(LoadSource, range_str)`` pairs.
        error (str): Emitted with a human-readable message on failure.
    """

    finished: Signal = Signal(list, list)  # type: ignore[misc]
    error: Signal = Signal(str)

    def __init__(self, spreadsheet_id: str, range_name: str, parent: QWidget | None = None) -> None:
        """Initialise with the target spreadsheet ID and range name."""
        super().__init__(parent)
        self._spreadsheet_id = spreadsheet_id
        self._range_name = range_name

    def run(self) -> None:
        """Authenticate and fetch sheet data in the background."""
        try:
            service = AuthManager().create_sheets_service()
            if not service:
                self.error.emit("Could not authenticate with Google Sheets API.")
                return
            sheet_data, range_sources = sheets_backend.retrieve_sheet_data(
                service, self._spreadsheet_id, self._range_name
            )
            self.finished.emit(sheet_data, range_sources)
        except Exception as exc:
            logger.error(f"Error fetching sheet data: {exc}")
            self.error.emit(str(exc))


def _log_range_sources(range_sources: list, sheet_data: list) -> None:
    """
    Log the origin of each loaded range for debugging.

    Args:
        range_sources: List of ``(LoadSource, range_str)`` pairs.
        sheet_data: Loaded sheet rows, used for the row count in the log message.
    """
    if len(range_sources) == 1 or all(s == range_sources[0][0] for s, _ in range_sources):
        source, range_str = range_sources[0]
        source_text = "database cache" if source == LoadSource.DATABASE else "Google Sheets API"
        logger.info(f"Loaded {len(sheet_data)} rows from {source_text} (range: {range_str})")
    else:
        logger.info(f"Loaded {len(sheet_data)} total rows across {len(range_sources)} ranges.")
        for source, range_str in range_sources:
            source_text = "database cache" if source == LoadSource.DATABASE else "Google Sheets API"
            logger.debug(f"Range '{range_str}' loaded from {source_text}")


class MainView(QMainWindow):
    """
    Main window for the ripper application.

    Manages the main UI layout, menus, toolbars, actions, and authentication state.

    Key slots:
        update_auth_status: Updates the authentication status display in the status bar.
        on_oauth_client_registered: Handles user update of target OAuth client.
        data_source_selected: Handles selection of a data source from the sheet selection dialog.
    """

    def __init__(self) -> None:
        """Initialize the main window and set up the UI."""
        super().__init__()

        # Initialize menu attributes
        self._file_menu = QMenu("&File", self)
        self._edit_menu = QMenu("&Edit", self)
        self._view_menu = QMenu("&View", self)
        self._dashboard_menu = QMenu("&Dashboard", self)
        self._oauth_menu = QMenu("&OAuth", self)
        self._help_menu = QMenu("&Help", self)

        # Initialize toolbar attributes
        self._file_tool_bar = QToolBar("File", self)
        self._edit_tool_bar = QToolBar("Edit", self)

        # Initialize action attributes
        self._register_oauth_act = QAction(parent=self)
        self._register_oauth_act.setIcon(QIcon.fromTheme("document-new"))
        self._register_oauth_act.setText("Register/Update OAuth Client")
        self._register_oauth_act.setStatusTip("Register or update the target Google OAuth Client")
        self._register_oauth_act.triggered.connect(self.register_oauth)

        self._authenticate_oauth_act = QAction(parent=self)
        self._authenticate_oauth_act.setIcon(QIcon.fromTheme("dialog-password"))
        self._authenticate_oauth_act.setText("Authenticate")
        self._authenticate_oauth_act.setStatusTip("Start Google OAuth authentication flow")
        self._authenticate_oauth_act.triggered.connect(self.authenticate_oauth)
        self._authenticate_oauth_act.setEnabled(False)

        self._new_source_act = QAction(parent=self)
        self._new_source_act.setIcon(QIcon.fromTheme("document-new"))
        self._new_source_act.setText("&New Source")
        self._new_source_act.setShortcut(QKeySequence.StandardKey.New)
        self._new_source_act.setStatusTip("Create a new named data source from a Google Sheet range")
        self._new_source_act.triggered.connect(self.new_source)
        self._new_source_act.setEnabled(False)

        self._save_act = QAction(parent=self)
        self._save_act.setIcon(QIcon.fromTheme("document-save"))
        self._save_act.setText("&Save...")
        self._save_act.setShortcut(QKeySequence.StandardKey.Save)
        self._save_act.setStatusTip("Save the current spreadsheet")
        self._save_act.triggered.connect(self.save)

        self._print_act = QAction(parent=self)
        self._print_act.setIcon(QIcon.fromTheme("document-print"))
        self._print_act.setText("&Print...")
        self._print_act.setShortcut(QKeySequence.StandardKey.Print)
        self._print_act.setStatusTip("Print the current view")
        self._print_act.triggered.connect(self.print_document)

        self._undo_act = QAction(parent=self)
        self._undo_act.setIcon(QIcon.fromTheme("edit-undo"))
        self._undo_act.setText("&Undo")
        self._undo_act.setShortcut(QKeySequence.StandardKey.Undo)
        self._undo_act.setStatusTip("Undo the last editing action")
        self._undo_act.triggered.connect(self.undo)

        self._quit_act = QAction(parent=self)
        self._quit_act.setText("&Quit")
        self._quit_act.setShortcut("Ctrl+Q")
        self._quit_act.setStatusTip("Quit the application")
        self._quit_act.triggered.connect(self.close)

        self._about_act = QAction(parent=self)
        self._about_act.setText("&About")
        self._about_act.setStatusTip("About ripper")
        self._about_act.triggered.connect(self.about)

        self._save_layout_act = QAction(parent=self)
        self._reset_layout_act = QAction(parent=self)

        app = QApplication.instance()
        if app:
            self._about_qt_act = QAction(parent=self)
            self._about_qt_act.setText("About &Qt")
            self._about_qt_act.setStatusTip("About Qt")
            self._about_qt_act.triggered.connect(lambda: QMessageBox.aboutQt(self))
        else:
            self._about_qt_act = QAction(parent=self)
            self._about_qt_act.setText("About &Qt")
            self._about_qt_act.setStatusTip("About Qt")
            self._about_qt_act.setEnabled(False)

        # Initialize status bar attributes
        self._auth_status_label = QLabel(self)
        self._auth_status_label.setMinimumWidth(200)
        self._auth_status_label.setFont(FontManager().get(FontId.TOOLTIP))

        # Initialize dialog attributes
        self._auth_dialog: QDialog | None = None
        self._sheet_selection_dialog: QDialog | None = None

        # Single persistent dock for the active data source table view
        self._table_dock: ads.CDockWidget | None = None
        # ID of the data source currently displayed in the dock
        self._active_data_source_id: int | None = None
        # Map (spreadsheet_id, sheet_name, range_a1) -> TransactionTableViewWidget for dashboard
        # data. range_a1 is part of the key so two sources on the same tab but different ranges
        # don't collide and serve each other's rows.
        self._table_widgets: dict[tuple[str, str, str], table_view.TransactionTableViewWidget] = {}
        # Keeps Python references to running background workers so they aren't GC'd before finishing.
        self._active_workers: set[_DataFetchWorker] = set()
        # Dock manager and dashboard dock (fully assigned in create_main_layout / _init_dashboard_dock)
        self._dock_manager: ads.CDockManager
        self._dashboard_dock: ads.CDockWidget | None = None
        self._sources_dock: ads.CDockWidget | None = None
        # Dashboard content widget; set to None until _init_dashboard_dock() succeeds.
        self.dashboard_widget: QWidget | None = None

        # Setup monospace font for tooltips
        QToolTip.setFont(FontManager().get(FontId.TOOLTIP))

        # Configure CDockManager before creating it
        ads.CDockManager.setConfigFlag(ads.CDockManager.eConfigFlag.OpaqueSplitterResize, True)
        ads.CDockManager.setConfigFlag(ads.CDockManager.eConfigFlag.XmlAutoFormattingEnabled, True)

        # Set up the main window
        self.setWindowTitle("ripper")
        self.resize(QSize(1200, 600))  # Create UI elements
        self.create_menus()
        self.create_tool_bars()
        self.create_status_bar()

        # Create the main layout with CDockManager and dockable panels
        self.create_main_layout()

        # Check if OAuth client is configured and update UI accordingly
        self.update_oauth_ui()

    def create_menus(self) -> None:
        """
        Create and configure the main menu bar and its menus.
        """
        self.menuBar().addMenu(self._file_menu)
        self._file_menu.addAction(self._new_source_act)
        self._file_menu.addAction(self._save_act)
        self._file_menu.addAction(self._print_act)
        self._file_menu.addSeparator()
        self._file_menu.addAction(self._quit_act)

        self.menuBar().addMenu(self._edit_menu)
        self._edit_menu.addAction(self._undo_act)

        self.menuBar().addMenu(self._view_menu)
        self._save_layout_act = QAction("Save Layout", self)
        self._save_layout_act.setStatusTip("Save the current dock layout")
        self._save_layout_act.triggered.connect(self._save_layout)
        self._view_menu.addAction(self._save_layout_act)

        self._reset_layout_act = QAction("Reset Layout", self)
        self._reset_layout_act.setStatusTip("Reset dock layout to default")
        self._reset_layout_act.triggered.connect(self._reset_layout)
        self._view_menu.addAction(self._reset_layout_act)

        # Add dashboard menu
        self._show_dashboard_act = QAction("Show &Dashboard", self)
        self._show_dashboard_act.setStatusTip("Show the dashboard dock")
        self._show_dashboard_act.triggered.connect(self.show_dashboard_dock)
        self._dashboard_menu.addAction(self._show_dashboard_act)
        self.menuBar().addMenu(self._dashboard_menu)

        self.menuBar().addMenu(self._oauth_menu)
        self._oauth_menu.addAction(self._register_oauth_act)
        self._oauth_menu.addAction(self._authenticate_oauth_act)

        self.menuBar().addSeparator()

        self.menuBar().addMenu(self._help_menu)
        self._help_menu.addAction(self._about_act)
        self._help_menu.addAction(self._about_qt_act)

    def create_tool_bars(self) -> None:
        """
        Create and configure the toolbars for file and edit actions.
        """
        self.addToolBar(self._file_tool_bar)
        self._file_tool_bar.addAction(self._new_source_act)
        self._file_tool_bar.addAction(self._save_act)
        self._file_tool_bar.addAction(self._print_act)

        self.addToolBar(self._edit_tool_bar)
        self._edit_tool_bar.addAction(self._undo_act)

    def create_status_bar(self) -> None:
        """
        Create and configure the status bar.

        Sets up the status bar with an authentication status label.
        """
        self.statusBar().showMessage("Ready")

        # Create a permanent widget for auth status
        self.statusBar().addPermanentWidget(self._auth_status_label)  # Connect to auth state changed signal
        AuthManager().authStateChanged.connect(self.update_auth_status)

        # Initialize auth status display
        self.update_auth_status(AuthManager().auth_info())

    def _init_dashboard_dock(self) -> None:
        """Initialize the dashboard dock widget."""
        try:
            from ripper.rippergui.dashboard import DashboardManagerWidget

            # Create dashboard widget
            dashboards_dir = Path(get_app_data_dir()) / "dashboards"
            dashboards_dir.mkdir(parents=True, exist_ok=True)
            self.dashboard_widget = DashboardManagerWidget(
                storage_dir=dashboards_dir,
                records_fn=self._get_records_for_dashboard,
            )
            self._dashboard_dock = ads.CDockWidget(self._dock_manager, "Dashboard")
            self._dashboard_dock.setWidget(self.dashboard_widget)
            self._dock_manager.addDockWidget(ads.RightDockWidgetArea, self._dashboard_dock)

        except ImportError as e:
            logger.error(f"Failed to initialize dashboard: {e}")
            QMessageBox.warning(
                self, "Dashboard Error", "Failed to initialize dashboard. Some features may not be available."
            )

    def _get_records_for_dashboard(self, spreadsheet_id: str, sheet_name: str, range_a1: str) -> list[dict] | None:
        """Return filtered records from the loaded table widget for a data source.

        Called by :class:`DashboardDataService` when refreshing dashboard data.
        Returns ``None`` if no table widget exists for the given source (falls
        back to the normal API fetch path).

        Args:
            spreadsheet_id: The spreadsheet ID to look up.
            sheet_name: The sheet tab name to look up.
            range_a1: The A1 range of the source; part of the key so two sources on
                the same tab with different ranges resolve to their own widget.

        Returns:
            List of filtered record dicts or ``None`` if not loaded yet.
        """
        widget = self._table_widgets.get((spreadsheet_id, sheet_name, range_a1))
        if widget is None:
            return None
        return widget.get_filtered_records()

    def show_dashboard_dock(self) -> None:
        """Show the dashboard dock widget."""
        if self._dashboard_dock is not None:
            self._dashboard_dock.toggleView(True)
            self._dashboard_dock.raise_()
        else:
            QMessageBox.warning(self, "Dashboard", "The dashboard is not available.")

    def _save_layout(self) -> None:
        """Save the current dock layout to QSettings."""
        QSettings("solarisin", "ripper").setValue("dock_layout/state", self._dock_manager.saveState())

    def _restore_layout(self) -> None:
        """Restore dock layout from QSettings; silently skips on failure."""
        state = QSettings("solarisin", "ripper").value("dock_layout/state")
        if state is not None:
            try:
                self._dock_manager.restoreState(state)
            except Exception as exc:
                logger.warning(f"Could not restore dock layout: {exc}")

    def _reset_layout(self) -> None:
        """Clear saved layout from QSettings so next launch uses the default."""
        QSettings("solarisin", "ripper").remove("dock_layout/state")
        QMessageBox.information(self, "Layout Reset", "Layout will reset to default on next launch.")

    def closeEvent(self, event: QCloseEvent) -> None:  # type: ignore[override]
        """Save layout and wait briefly for any in-flight data fetches before closing."""
        self._save_layout()
        for worker in list(self._active_workers):
            worker.setParent(None)  # detach so window destruction won't force-destroy a running thread
            worker.wait(2000)
        super().closeEvent(event)

    def create_main_layout(self) -> None:
        """
        Create the main layout with CDockManager as the central widget.
        """
        # Create the CDockManager and set it as the central widget
        self._dock_manager = ads.CDockManager(self)
        self.setCentralWidget(self._dock_manager)

        # Create the Data Sources dock in the left area
        self._sources_dock = ads.CDockWidget(self._dock_manager, "Data Sources")
        self._datasource_list_widget = DataSourceListWidget(parent=self)
        self._datasource_list_widget.source_selected.connect(self._load_data_source_by_id)
        self._datasource_list_widget.refresh_requested.connect(self._refresh_data_source)
        self._sources_dock.setWidget(self._datasource_list_widget)
        self._dock_manager.addDockWidget(ads.LeftDockWidgetArea, self._sources_dock)

        # Initialize dashboard dock
        self._init_dashboard_dock()
        self._restore_layout()
        self._setup_view_menu_dock_actions()

    def _setup_view_menu_dock_actions(self) -> None:
        """Wire dock toggle actions into the View menu."""
        self._view_menu.addSeparator()
        if self._sources_dock is not None:
            self._view_menu.addAction(self._sources_dock.toggleViewAction())
        if self._dashboard_dock is not None:
            self._view_menu.addAction(self._dashboard_dock.toggleViewAction())

    def _load_data_source_by_id(self, ds_id: int, stamp_on_success: bool = False) -> None:
        """
        Load a saved data source from Google Sheets and display it in the dock.

        The fetch runs on a background thread so the UI stays responsive.  Called
        when the user clicks a data source in the sidebar, and also when refreshing.

        Args:
            ds_id: Primary key of the data source to load.
            stamp_on_success: When ``True``, update ``last_fetched_at`` and refresh
                the sidebar list after a successful load (used by
                :py:meth:`_refresh_data_source`).
        """
        record = Db.get_data_source(ds_id)
        if record is None:
            QMessageBox.warning(self, "Data Source", "Could not find the selected data source.")
            return

        spreadsheet_id = record["spreadsheet_id"]
        sheet_name = record["sheet_name"]
        range_a1 = record["range_a1"]
        name = record["name"]
        range_name = f"{sheet_name}!{range_a1}" if range_a1 else sheet_name

        progress = QProgressDialog("Loading data\u2026", "", 0, 0, self)
        progress.setWindowModality(Qt.WindowModality.WindowModal)
        progress.setMinimumDuration(300)
        progress.setValue(0)

        worker = _DataFetchWorker(spreadsheet_id, range_name, self)
        self._active_workers.add(worker)

        def on_finished(sheet_data: list, range_sources: list) -> None:
            self._active_workers.discard(worker)
            progress.reset()
            if not sheet_data:
                QMessageBox.warning(self, "Google Sheets", "No data found in the selected range.")
                return
            self._active_data_source_id = ds_id
            self._show_data_source_in_dock(
                ds_id,
                name,
                sheet_data,
                {
                    "spreadsheet_id": spreadsheet_id,
                    "spreadsheet_name": record.get("spreadsheet_name", ""),
                    "sheet_name": sheet_name,
                },
            )
            if stamp_on_success:
                Db.update_data_source_fetched_at(ds_id)
                self._datasource_list_widget.refresh()
            _log_range_sources(range_sources, sheet_data)

        def on_error(message: str) -> None:
            self._active_workers.discard(worker)
            progress.reset()
            QMessageBox.warning(self, "Google Sheets", message)

        worker.finished.connect(on_finished)
        worker.error.connect(on_error)
        worker.finished.connect(worker.deleteLater)
        worker.error.connect(worker.deleteLater)
        worker.start()

    def _refresh_data_source(self, ds_id: int) -> None:
        """
        Re-fetch a data source from the Google Sheets API and update the cache.

        Called from the DataSourceListWidget context-menu *Refresh* action.

        Args:
            ds_id: Primary key of the data source to refresh.
        """
        from ripper.ripperlib.sheet_data_cache import SheetDataCache  # avoid circular at module level

        record = Db.get_data_source(ds_id)
        if record is None:
            return

        SheetDataCache.invalidate_cache(record["spreadsheet_id"], record["sheet_name"])
        self._load_data_source_by_id(ds_id, stamp_on_success=True)

    # Actions ###########################################################################

    def register_oauth(self) -> None:
        """
        Prompt the user to supply OAuth client credentials.

        Opens a dialog where the user can enter their Google API OAuth client ID and secret.
        """
        logger.debug("Register OAuth selected")
        self.show_auth_view()

    def authenticate_oauth(self) -> None:
        """
        Start the Google OAuth authentication flow.

        Initiates the OAuth flow to authenticate with Google and gain access to the user's
        Google Sheets and Drive.
        """
        logger.debug("Authenticate OAuth selected")
        # Start the OAuth flow
        cred = AuthManager().authorize()

        if cred:
            QMessageBox.information(self, "Authentication Successful", "Successfully authenticated with Google!")
        else:
            QMessageBox.warning(self, "Authentication Failed", "Failed to authenticate with Google. Please try again.")

    def update_oauth_ui(self) -> None:
        """
        Update UI elements based on the current authentication state.

        Enables or disables actions based on whether OAuth client credentials are available
        and whether the user is logged in.
        """
        # Get current auth state
        state = AuthManager().auth_info().auth_state()
        has_credentials = state != AuthState.NO_CLIENT
        is_logged_in = state == AuthState.LOGGED_IN

        # Enable/disable the authenticate action based on whether credentials are available
        if self._authenticate_oauth_act:
            self._authenticate_oauth_act.setEnabled(has_credentials)

        # Enable/disable the new source action based on whether user is logged in
        if self._new_source_act:
            self._new_source_act.setEnabled(is_logged_in)

        logger.debug(
            f"OAuth client credentials {'found' if has_credentials else 'not found'}, "
            f"authentication is {'enabled' if has_credentials else 'disabled'}, "
            f"sheet selection is {'enabled' if is_logged_in else 'disabled'}"
        )

    def new_source(self) -> None:
        """
        Open the Create Data Source dialog.

        Checks authentication, opens the sheet picker dialog, and on confirmation
        persists the new data source to the database and refreshes the sidebar.
        """
        logger.debug("New source selected")

        auth_info = AuthManager().auth_info()
        if auth_info.auth_state() != AuthState.LOGGED_IN:
            QMessageBox.warning(
                self,
                "Authentication Required",
                "You need to authenticate with Google before creating a data source. "
                "Please use the OAuth menu to authenticate.",
            )
            return

        self._sheet_selection_dialog = SheetsSelectionDialog(self)
        self._sheet_selection_dialog.sheet_selected.connect(self.data_source_selected)
        self._sheet_selection_dialog.exec()

    def show_auth_view(self) -> None:
        """
        Show the authentication view as a dialog.

        Creates and displays a dialog where the user can enter their
        Google API OAuth client ID and secret.
        """
        self._auth_dialog = QDialog(self)
        self._auth_dialog.setWindowTitle("Google API Authentication")
        self._auth_dialog.setMinimumWidth(500)

        # Create auth view
        auth_view = AuthView(self._auth_dialog)
        auth_view.oauth_client_registered.connect(self.on_oauth_client_registered)

        # Set layout
        layout = QGridLayout(self._auth_dialog)
        layout.addWidget(auth_view)
        self._auth_dialog.setLayout(layout)

        # Show dialog
        self._auth_dialog.exec()

    def save(self) -> None:
        """
        Save the current document.

        This is a placeholder for future implementation.
        """
        logger.debug("Save selected")
        # TODO: implement saving functionality
        self.statusBar().showMessage("Saved '[filename]'", 2000)

    def print_document(self) -> None:
        """
        Print the current document.

        This is a placeholder for future implementation.
        """
        logger.debug("Print selected")
        # TODO: implement printing functionality
        self.statusBar().showMessage("Printing...", 2000)

    def undo(self) -> None:
        """
        Undo the last action.

        This is a placeholder for future implementation.
        """
        logger.debug("Undo selected")
        # TODO: implement undo functionality
        self.statusBar().showMessage("Undo", 2000)

    def about(self) -> None:
        """
        Show the about dialog with information about the application.
        """
        QMessageBox.about(self, "About ripper", "Ripper - A tool for extracting and analyzing data from Google Sheets")

    # Slots #############################################################################

    def update_auth_status(self, info: AuthInfo) -> None:
        """
        Update the authentication status display in the status bar.

        This slot is connected to the authStateChanged signal from AuthManager.

        Args:
            info: The current authentication information
        """
        if info.auth_state() == AuthState.NO_CLIENT:
            self._auth_status_label.setText("No OAuth Client")
        elif info.auth_state() == AuthState.NOT_LOGGED_IN:
            self._auth_status_label.setText("Not Logged In")
        elif info.auth_state() == AuthState.LOGGED_IN:
            self._auth_status_label.setText(f"Logged In: {info.user_email()}")
        else:
            self._auth_status_label.setText("Unknown Auth State")

        # Update UI elements that depend on auth state
        self.update_oauth_ui()

    def on_oauth_client_registered(self) -> None:
        """
        Handle user update of target OAuth client.

        This slot is called when the user successfully registers or updates
        their OAuth client credentials. It closes the auth dialog and updates
        the UI accordingly.
        """
        logger.debug("User configured OAuth client credentials")

        # Close the auth dialog if it is open
        if self._auth_dialog:
            self._auth_dialog.accept()

        # Update UI to enable options only available after an OAuth client is configured
        self.update_oauth_ui()
        logger.info("OAuth client registration successful")

        # Offer to authenticate immediately now that credentials are available
        reply = QMessageBox.question(
            self,
            "OAuth Client Registered",
            "Credentials saved. Would you like to authenticate with Google now?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.Yes,
        )
        if reply == QMessageBox.StandardButton.Yes:
            self.authenticate_oauth()

    def data_source_selected(self, source_info: dict) -> None:
        """
        Handle confirmation from the Create Data Source dialog.

        Fetches sheet data on a background thread so the UI stays responsive.
        The data source record is only persisted after a successful fetch to
        avoid orphaned DB rows when auth or the network call fails.

        Args:
            source_info: Dict emitted by SheetsSelectionDialog.sheet_selected with keys
                ``spreadsheet_name``, ``spreadsheet_id``, ``sheet_name``,
                ``sheet_range``, ``data_source_name``.
        """
        # Close the sheet selection dialog if it is open
        if self._sheet_selection_dialog:
            self._sheet_selection_dialog.accept()

        logger.info(f"Data source selected: {source_info}")

        spreadsheet_id = source_info["spreadsheet_id"]
        sheet_name = source_info["sheet_name"]
        sheet_range = source_info["sheet_range"]
        data_source_name = source_info.get("data_source_name") or f"{source_info['spreadsheet_name']} – {sheet_name}"
        range_name = f"{sheet_name}!{sheet_range}" if sheet_range else sheet_name

        progress = QProgressDialog("Loading data…", "", 0, 0, self)
        progress.setWindowModality(Qt.WindowModality.WindowModal)
        progress.setMinimumDuration(300)
        progress.setValue(0)

        worker = _DataFetchWorker(spreadsheet_id, range_name, self)
        self._active_workers.add(worker)

        def on_finished(sheet_data: list, range_sources: list) -> None:
            self._active_workers.discard(worker)
            progress.reset()
            if not sheet_data:
                QMessageBox.warning(self, "Google Sheets", "No data found in the selected range.")
                return
            # Only persist the record after a confirmed successful fetch
            ds_id = Db.create_data_source(
                name=data_source_name,
                spreadsheet_id=spreadsheet_id,
                sheet_name=sheet_name,
                range_a1=sheet_range,
            )
            if ds_id is None:
                QMessageBox.warning(self, "Database Error", "Could not save the data source. Please try again.")
                return
            Db.update_data_source_fetched_at(ds_id)
            if hasattr(self, "_datasource_list_widget"):
                self._datasource_list_widget.refresh()
            self._active_data_source_id = ds_id
            self._show_data_source_in_dock(ds_id, data_source_name, sheet_data, source_info)
            _log_range_sources(range_sources, sheet_data)

        def on_error(message: str) -> None:
            self._active_workers.discard(worker)
            progress.reset()
            QMessageBox.warning(self, "Google Sheets", message)

        worker.finished.connect(on_finished)
        worker.error.connect(on_error)
        worker.finished.connect(worker.deleteLater)
        worker.error.connect(worker.deleteLater)
        worker.start()

    def _show_data_source_in_dock(
        self,
        data_source_id: int,
        title: str,
        sheet_data: list,
        source_info: dict,
    ) -> None:
        """
        Display sheet data in the single persistent data dock widget.

        Reuses the existing dock if already present; replaces its inner widget.
        Adds a thin banner above the table showing the source name and load origin.

        Args:
            data_source_id: Primary key of the data source record.
            title: Human-readable title for the dock.
            sheet_data: 2-D list of cell values (first row is headers).
            source_info: Original source_info dict (for spreadsheet_name, sheet_name).
        """
        headers = sheet_data[0] if sheet_data else []
        records = [dict(zip(headers, row)) for row in sheet_data[1:]] if len(sheet_data) > 1 else []

        # Build the container: banner + table
        container = QWidget()
        container_layout = QVBoxLayout(container)
        container_layout.setContentsMargins(0, 0, 0, 0)
        container_layout.setSpacing(2)

        # Fetch last_fetched_at for banner
        ds_record = Db.get_data_source(data_source_id)
        fetched_at = ds_record.get("last_fetched_at", "") if ds_record else ""
        banner_text = f"{title}" + (f"  —  last synced: {fetched_at}" if fetched_at else "")

        banner = QLabel(banner_text)
        banner.setStyleSheet(
            "padding: 4px 8px; background: #2a2a2a; color: #aaa; font-size: 11px; border-bottom: 1px solid #444;"
        )
        container_layout.addWidget(banner)

        table_widget = table_view.TransactionTableViewWidget(records)
        container_layout.addWidget(table_widget)

        # Track by (spreadsheet_id, sheet_name, range_a1) so the dashboard can access filtered
        # rows for the exact source range (not just the tab).
        if source_info:
            key = (
                source_info.get("spreadsheet_id", ""),
                source_info.get("sheet_name", ""),
                source_info.get("sheet_range", ""),
            )
            if key[0] and key[1]:
                self._table_widgets[key] = table_widget
                table_widget.destroyed.connect(
                    lambda _, k=key, w=table_widget: (
                        self._table_widgets.pop(k) if self._table_widgets.get(k) is w else None
                    )
                )

        if self._table_dock is None:
            self._table_dock = ads.CDockWidget(self._dock_manager, title)
            self._dock_manager.addDockWidget(ads.CenterDockWidgetArea, self._table_dock)
        else:
            self._table_dock.setWindowTitle(title)

        self._table_dock.setWidget(container)
        self._table_dock.toggleView(True)
