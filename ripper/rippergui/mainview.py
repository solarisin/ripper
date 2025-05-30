"""
Main application window for the ripper application.

This module provides MainView, a QMainWindow subclass that manages the main UI layout, menus, toolbars, actions,
authentication state, and UI updates for the ripper application.
"""

from loguru import logger
from PySide6.QtCore import QSize
from PySide6.QtGui import QAction, QIcon, QKeySequence, Qt
from PySide6.QtWidgets import (
    QApplication,
    QDialog,
    QDockWidget,
    QGridLayout,
    QLabel,
    QMainWindow,
    QMenu,
    QMessageBox,
    QToolBar,
    QToolTip,
    QWidget,
)

from ripper.rippergui.fonts import FontId, FontManager
from ripper.rippergui.oauth_client_config_view import AuthView
from ripper.rippergui.sheets_selection_view import SheetsSelectionDialog
from ripper.ripperlib.auth import AuthInfo, AuthManager, AuthState


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
        self._new_source_act.setStatusTip("Import a new source sheet")
        self._new_source_act.triggered.connect(self.new_source)

        self._select_sheet_act = QAction(parent=self)
        self._select_sheet_act.setIcon(QIcon.fromTheme("document-open"))
        self._select_sheet_act.setText("Select &Google Sheet")
        self._select_sheet_act.setShortcut(QKeySequence.StandardKey.Open)
        self._select_sheet_act.setStatusTip("Select a Google Sheet from your Drive")
        self._select_sheet_act.triggered.connect(self.select_google_sheet)
        self._select_sheet_act.setEnabled(False)

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

        # Setup monospace font for tooltips
        QToolTip.setFont(FontManager().get(FontId.TOOLTIP))

        # Set up the main window
        self.setWindowTitle("ripper")
        self.setDockOptions(
            QMainWindow.DockOption.AllowTabbedDocks
            | QMainWindow.DockOption.AnimatedDocks
            | QMainWindow.DockOption.AllowNestedDocks
        )
        self.resize(QSize(1200, 600))

        # Create UI elements
        self.create_menus()
        self.create_tool_bars()
        self.create_status_bar()

        # Ensure we have a central widget, then hide it
        grid_layout = QGridLayout()
        widget = QWidget()
        widget.setLayout(grid_layout)
        self.setCentralWidget(widget)
        self.centralWidget().hide()

        # Check if OAuth client is configured and update UI accordingly
        self.update_oauth_ui()

    def create_menus(self) -> None:
        """
        Create and configure the main menu bar and its menus.
        """
        self.menuBar().addMenu(self._file_menu)
        self._file_menu.addAction(self._new_source_act)
        self._file_menu.addAction(self._select_sheet_act)
        self._file_menu.addAction(self._save_act)
        self._file_menu.addAction(self._print_act)
        self._file_menu.addSeparator()
        self._file_menu.addAction(self._quit_act)

        self.menuBar().addMenu(self._edit_menu)
        self._edit_menu.addAction(self._undo_act)

        self.menuBar().addMenu(self._view_menu)

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
        self._file_tool_bar.addAction(self._select_sheet_act)
        self._file_tool_bar.addAction(self._save_act)
        self._file_tool_bar.addAction(self._print_act)

        self.addToolBar(self._edit_tool_bar)
        self._edit_tool_bar.addAction(self._undo_act)

    def create_status_bar(self) -> None:
        """
        Create and configure the status bar.

        Sets up the status bar with an authentication status label and connects
        the auth state changed signal to update the status.
        """
        """
        Create and configure the status bar.

        Sets up the status bar with an authentication status label.
        """
        self.statusBar().showMessage("Ready")

        # Create a permanent widget for auth status
        self.statusBar().addPermanentWidget(self._auth_status_label)

        # Connect to auth state changed signal
        AuthManager().authStateChanged.connect(self.update_auth_status)

        # Initialize auth status display
        self.update_auth_status(AuthManager().auth_info())

    # Actions ###########################################################################

    def register_oauth(self) -> None:
        """
        Prompt the user to supply OAuth client credentials.

        Opens a dialog where the user can enter their Google API OAuth client ID and secret.
        Returns:
            None
        """
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
        Returns:
            None. Shows a message box on success or failure.
        """
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
        Returns:
            None
        """
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

        # Enable/disable the select sheet action based on whether user is logged in
        if self._select_sheet_act:
            self._select_sheet_act.setEnabled(is_logged_in)

        logger.debug(
            f"OAuth client credentials {'found' if has_credentials else 'not found'}, "
            f"authentication is {'enabled' if has_credentials else 'disabled'}, "
            f"sheet selection is {'enabled' if is_logged_in else 'disabled'}"
        )

    def new_source(self) -> None:
        """
        Create a new data source view.

        Creates a new transaction table view in a dock widget.
        Returns:
            None
        """
        """
        Create a new data source view.

        Creates a new transaction table view in a dock widget.
        """
        logger.debug("New source selected")
        # TODO plan and implement the new source functionality

    def show_auth_view(self) -> None:
        """
        Show the authentication view as a dialog.

        Creates and displays a dialog where the user can enter their
        Google API OAuth client ID and secret.
        Returns:
            None
        """
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
        Returns:
            None
        """
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
        Returns:
            None
        """
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
        Returns:
            None
        """
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

        Returns:
            None
        """
        """
        Show the about dialog with information about the application.
        """
        QMessageBox.about(self, "About ripper", "Ripper - A tool for extracting and analyzing data from Google Sheets")

    def select_google_sheet(self) -> None:
        """
        Open the Google Sheets selection dialog.

        Displays a dialog where the user can select a Google Sheet from their Drive.
        Checks if the user is authenticated first and shows a warning if not.
        Returns:
            None
        """
        """
        Open the Google Sheets selection dialog.

        Displays a dialog where the user can select a Google Sheet from their Drive.
        Checks if the user is authenticated first and shows a warning if not.
        """
        logger.debug("Select Google Sheet selected")

        # Check if user is authenticated
        auth_info = AuthManager().auth_info()
        if auth_info.auth_state() != AuthState.LOGGED_IN:
            QMessageBox.warning(
                self,
                "Authentication Required",
                "You need to authenticate with Google before selecting a sheet. "
                "Please use the OAuth menu to authenticate.",
            )
            return

        # Open the sheet selection dialog
        self._sheet_selection_dialog = SheetsSelectionDialog(self)
        self._sheet_selection_dialog.sheet_selected.connect(self.data_source_selected)
        self._sheet_selection_dialog.exec()

    # Slots #############################################################################

    def update_auth_status(self, info: AuthInfo) -> None:
        """
        Update the authentication status display in the status bar.

        This slot is connected to the authStateChanged signal from AuthManager.

        Args:
            info (AuthInfo): The current authentication information

        Returns:
            None
        """
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

        Returns:
            None
        """
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

    def data_source_selected(self, source_info: dict) -> None:
        """
        Handle selection of a data source from the sheet selection dialog.

        Args:
            source_info (dict): Information about the selected data source.

        Returns:
            None
        """
        # Close the sheet selection dialog if it is open
        if self._sheet_selection_dialog:
            self._sheet_selection_dialog.accept()

        logger.info(f"Data source selected: {source_info}")

        # Fetch data from Google Sheets API for the selected range
        import ripper.ripperlib.sheets_backend as sheets_backend
        from ripper.ripperlib.auth import AuthManager

        spreadsheet_id = source_info["spreadsheet_id"]
        sheet_name = source_info["sheet_name"]
        sheet_range = source_info["sheet_range"]
        range_name = f"{sheet_name}!{sheet_range}" if sheet_range else sheet_name

        sheets_service = AuthManager().create_sheets_service()
        if not sheets_service:
            QMessageBox.warning(self, "Google Sheets", "Could not authenticate with Google Sheets API.")
            return

        # Fetch the data (SheetData is list[list[Any]])
        sheet_data = sheets_backend.fetch_data_from_spreadsheet(sheets_service, spreadsheet_id, range_name)
        if not sheet_data:
            QMessageBox.warning(self, "Google Sheets", "No data found in the selected range.")
            return

        # Convert SheetData to list of dicts for TransactionTableViewWidget
        headers = sheet_data[0] if sheet_data else []
        records = [dict(zip(headers, row)) for row in sheet_data[1:]] if len(sheet_data) > 1 else []

        # Create and show the table view
        from ripper.rippergui import table_view

        table_widget = table_view.TransactionTableViewWidget(records)
        dock = QDockWidget(f"Table: {source_info['spreadsheet_name']} - {sheet_name}", self)
        dock.setAllowedAreas(Qt.DockWidgetArea.AllDockWidgetAreas)
        dock.setWidget(table_widget)
        self.addDockWidget(Qt.DockWidgetArea.LeftDockWidgetArea, dock)
        self._view_menu.addAction(dock.toggleViewAction())
