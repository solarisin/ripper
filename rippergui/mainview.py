import logging
from typing import Optional

from PySide6.QtCore import QSize
from PySide6.QtGui import QAction, QIcon, QKeySequence, Qt
from PySide6.QtWidgets import (QApplication, QDialog, QDockWidget, QGridLayout,
                               QLabel, QMainWindow, QMenu, QMessageBox,
                               QToolBar, QToolTip, QWidget)
from ripperlib.auth import AuthInfo, AuthManager, AuthState

from rippergui.globals import Fonts
from rippergui.oauth_client_config_view import AuthView
from rippergui.sheets_selection_view import SheetsSelectionDialog

log = logging.getLogger("ripper:mainview")


class MainView(QMainWindow):
    """
    Main application window for the ripper application.

    This class handles the main UI layout, menus, toolbars, and actions.
    It also manages the authentication state and UI updates.
    """

    def __init__(self):
        """Initialize the main window and set up the UI."""
        super().__init__()

        # Initialize menu attributes
        self._file_menu: Optional[QMenu] = None
        self._edit_menu: Optional[QMenu] = None
        self._view_menu: Optional[QMenu] = None
        self._oauth_menu: Optional[QMenu] = None
        self._help_menu: Optional[QMenu] = None

        # Initialize toolbar attributes
        self._file_tool_bar: Optional[QToolBar] = None
        self._edit_tool_bar: Optional[QToolBar] = None

        # Initialize action attributes
        self._register_oauth_act: Optional[QAction] = None
        self._authenticate_oauth_act: Optional[QAction] = None
        self._new_source_act: Optional[QAction] = None
        self._select_sheet_act: Optional[QAction] = None
        self._save_act: Optional[QAction] = None
        self._print_act: Optional[QAction] = None
        self._undo_act: Optional[QAction] = None
        self._quit_act: Optional[QAction] = None
        self._about_act: Optional[QAction] = None
        self._about_qt_act: Optional[QAction] = None

        # Initialize status bar attributes
        self._auth_status_label: Optional[QLabel] = None

        # Initialize dialog attributes
        self._auth_dialog: Optional[QDialog] = None

        # Setup monospace font for tooltips
        QToolTip.setFont(Fonts.get(Fonts.FontId.TOOLTIP))

        # Set up the main window
        self.setWindowTitle("ripper")
        self.setDockOptions(
            QMainWindow.DockOption.AllowTabbedDocks
            | QMainWindow.DockOption.AnimatedDocks
            | QMainWindow.DockOption.AllowNestedDocks
        )
        self.resize(QSize(1200, 600))

        # Create UI elements
        self.create_actions()
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

    def create_menus(self):
        self._file_menu = self.menuBar().addMenu("&File")
        self._file_menu.addAction(self._new_source_act)
        self._file_menu.addAction(self._select_sheet_act)
        self._file_menu.addAction(self._save_act)
        self._file_menu.addAction(self._print_act)
        self._file_menu.addSeparator()
        self._file_menu.addAction(self._quit_act)

        self._edit_menu = self.menuBar().addMenu("&Edit")
        self._edit_menu.addAction(self._undo_act)

        self._view_menu = self.menuBar().addMenu("&View")

        self._oauth_menu = self.menuBar().addMenu("&OAuth")
        self._oauth_menu.addAction(self._register_oauth_act)
        self._oauth_menu.addAction(self._authenticate_oauth_act)

        self.menuBar().addSeparator()

        self._help_menu = self.menuBar().addMenu("&Help")
        self._help_menu.addAction(self._about_act)
        self._help_menu.addAction(self._about_qt_act)

    def create_tool_bars(self):
        self._file_tool_bar = self.addToolBar("File")
        self._file_tool_bar.addAction(self._new_source_act)
        self._file_tool_bar.addAction(self._select_sheet_act)
        self._file_tool_bar.addAction(self._save_act)
        self._file_tool_bar.addAction(self._print_act)

        self._edit_tool_bar = self.addToolBar("Edit")
        self._edit_tool_bar.addAction(self._undo_act)

    def create_status_bar(self) -> None:
        """
        Create and configure the status bar.

        Sets up the status bar with an authentication status label.
        """
        self.statusBar().showMessage("Ready")

        # Create a permanent widget for auth status
        self._auth_status_label = QLabel()
        self._auth_status_label.setMinimumWidth(200)
        self._auth_status_label.setFont(Fonts.get(Fonts.FontId.TOOLTIP))
        self.statusBar().addPermanentWidget(self._auth_status_label)

        # Connect to auth state changed signal
        AuthManager().authStateChanged.connect(self.update_auth_status)

        # Initialize auth status display
        self.update_auth_status(AuthManager().auth_info())

    # Actions ###########################################################################

    def create_actions(self) -> None:
        """
        Create all the actions used in the application.

        Sets up actions for menus and toolbars with appropriate icons, shortcuts,
        and connections to handler methods.
        """
        # OAuth actions
        icon = QIcon.fromTheme("document-new", QIcon(":/res/new.png"))  # TODO: add google oauth-specific icon
        self._register_oauth_act = QAction(
            icon,
            "Register/Update OAuth Client",
            self,
            statusTip="Register or update the target Google OAuth Client",
            triggered=self.register_oauth,
        )

        # Authenticate action
        icon = QIcon.fromTheme("dialog-password", QIcon(":/res/new.png"))
        self._authenticate_oauth_act = QAction(
            icon,
            "Authenticate",
            self,
            statusTip="Start Google OAuth authentication flow",
            triggered=self.authenticate_oauth,
        )
        # Initially disabled until client is configured
        self._authenticate_oauth_act.setEnabled(False)

        # New source action
        icon = QIcon.fromTheme("document-new", QIcon(":/res/new.png"))
        self._new_source_act = QAction(
            icon,
            "&New Source",
            self,
            shortcut=QKeySequence.StandardKey.New,
            statusTip="Import a new source sheet",
            triggered=self.new_source,
        )

        # Select Google Sheet action
        icon = QIcon.fromTheme("document-open", QIcon(":/res/new.png"))
        self._select_sheet_act = QAction(
            icon,
            "Select &Google Sheet",
            self,
            shortcut=QKeySequence.StandardKey.Open,
            statusTip="Select a Google Sheet from your Drive",
            triggered=self.select_google_sheet,
        )
        # Initially disabled until user is logged in
        self._select_sheet_act.setEnabled(False)

        # Save action
        icon = QIcon.fromTheme("document-save", QIcon(":/res/save.png"))
        self._save_act = QAction(
            icon,
            "&Save...",
            self,
            shortcut=QKeySequence.StandardKey.Save,
            statusTip="Save the current spreadsheet",
            triggered=self.save,
        )

        # Print action
        icon = QIcon.fromTheme("document-print", QIcon(":/res/print.png"))
        self._print_act = QAction(
            icon,
            "&Print...",
            self,
            shortcut=QKeySequence.StandardKey.Print,
            statusTip="Print the current view",
            triggered=self.print_document,
        )

        # Undo action
        icon = QIcon.fromTheme("edit-undo", QIcon(":/res/undo.png"))
        self._undo_act = QAction(
            icon,
            "&Undo",
            self,
            shortcut=QKeySequence.StandardKey.Undo,
            statusTip="Undo the last editing action",
            triggered=self.undo,
        )

        # Quit action
        self._quit_act = QAction(
            "&Quit", self, shortcut="Ctrl+Q", statusTip="Quit the application", triggered=self.close
        )

        # About actions
        self._about_act = QAction("&About", self, statusTip="About ripper", triggered=self.about)

        self._about_qt_act = QAction("About &Qt", self, statusTip="About Qt", triggered=QApplication.instance().aboutQt)

    def register_oauth(self) -> None:
        """
        Prompt the user to supply OAuth client credentials.

        Opens a dialog where the user can enter their Google API OAuth client ID and secret.
        """
        log.debug("Register OAuth selected")
        self.show_auth_view()

    def authenticate_oauth(self) -> None:
        """
        Start the Google OAuth authentication flow.

        Initiates the OAuth flow to authenticate with Google and gain access to the user's
        Google Sheets and Drive.
        """
        log.debug("Authenticate OAuth selected")
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

        # Enable/disable the select sheet action based on whether user is logged in
        if self._select_sheet_act:
            self._select_sheet_act.setEnabled(is_logged_in)

        log.debug(
            f"OAuth client credentials {'found' if has_credentials else 'not found'}, "
            f"authentication is {'enabled' if has_credentials else 'disabled'}, "
            f"sheet selection is {'enabled' if is_logged_in else 'disabled'}"
        )

    def new_source(self) -> None:
        """
        Create a new data source view.

        Creates a new transaction table view in a dock widget.
        """
        log.debug("New source selected")

        from rippergui import table_view

        table_widget = table_view.TransactionTableViewWidget(None, simulate=True)

        dock = QDockWidget("Table", self)
        dock.setAllowedAreas(Qt.DockWidgetArea.AllDockWidgetAreas)
        dock.setWidget(table_widget)
        self.addDockWidget(Qt.DockWidgetArea.LeftDockWidgetArea, dock)
        self._view_menu.addAction(dock.toggleViewAction())

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
        log.debug("Save selected")
        # TODO: implement saving functionality
        self.statusBar().showMessage("Saved '[filename]'", 2000)

    def print_document(self) -> None:
        """
        Print the current document.

        This is a placeholder for future implementation.
        """
        log.debug("Print selected")
        # TODO: implement printing functionality
        self.statusBar().showMessage("Printing...", 2000)

    def undo(self) -> None:
        """
        Undo the last action.

        This is a placeholder for future implementation.
        """
        log.debug("Undo selected")
        # TODO: implement undo functionality
        self.statusBar().showMessage("Undo", 2000)

    def about(self) -> None:
        """
        Show the about dialog with information about the application.
        """
        QMessageBox.about(self, "About ripper", "Ripper - A tool for extracting and analyzing data from Google Sheets")

    def select_google_sheet(self) -> None:
        """
        Open the Google Sheets selection dialog.

        Displays a dialog where the user can select a Google Sheet from their Drive.
        Checks if the user is authenticated first and shows a warning if not.
        """
        log.debug("Select Google Sheet selected")

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

        # Open the sheets selection dialog
        dialog = SheetsSelectionDialog(self)
        dialog.exec()

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
        log.debug("User configured OAuth client credentials")

        # Close the auth dialog if it is open
        if self._auth_dialog:
            self._auth_dialog.accept()

        # Update UI to enable options only available after an OAuth client is configured
        self.update_oauth_ui()
        log.info("OAuth client registration successful")
