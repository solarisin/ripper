import logging

from PySide6.QtCore import QSize
from PySide6.QtGui import QAction, QIcon, QKeySequence
from PySide6.QtWidgets import QApplication, QDialog, QMainWindow, QMessageBox, QWidget, QGridLayout, QLabel

from rippergui.oauth_client_config_view import AuthView
from ripperlib.auth import AuthManager, AuthState, AuthInfo


class MainView(QMainWindow):
    def __init__(self):
        super().__init__()

        self.log = logging.getLogger("ripper:mainview")

        self._file_menu = None
        self._edit_menu = None
        self._view_menu = None
        self._oauth_menu = None
        self._help_menu = None

        self._file_tool_bar = None
        self._edit_tool_bar = None

        self._register_oauth_act = None
        self._authenticate_oauth_act = None
        self._new_source_act = None
        self._save_act = None
        self._print_act = None
        self._undo_act = None
        self._quit_act = None
        self._about_act = None
        self._about_qt_act = None

        self.setWindowTitle("ripper")
        self.dockNestingEnabled = True
        self.resize(QSize(640, 480))

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
        self._file_tool_bar.addAction(self._save_act)
        self._file_tool_bar.addAction(self._print_act)

        self._edit_tool_bar = self.addToolBar("Edit")
        self._edit_tool_bar.addAction(self._undo_act)

    def create_status_bar(self):
        self.statusBar().showMessage("Ready")

        # Create a permanent widget for auth status
        self.auth_status_label = QLabel()
        # self.auth_status_label.setFrameStyle(QLabel.Panel | QLabel.Sunken)
        self.auth_status_label.setMinimumWidth(200)
        self.statusBar().addPermanentWidget(self.auth_status_label)

        # Connect to auth state changed signal
        AuthManager().authStateChanged.connect(self.update_auth_status)

        # Initialize auth status display
        self.update_auth_status(AuthManager().auth_info())

    ####### Actions #####################################################################

    # noinspection PyArgumentList
    def create_actions(self):
        # TODO add google oauth-specific icon
        icon = QIcon.fromTheme("document-new", QIcon(":/res/new.png"))
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

        icon = QIcon.fromTheme("document-new", QIcon(":/res/new.png"))
        self._new_source_act = QAction(
            icon,
            "&New Source",
            self,
            shortcut=QKeySequence.StandardKey.New,
            statusTip="Import a new source sheet",
            triggered=self.new_source,
        )

        icon = QIcon.fromTheme("document-save", QIcon(":/res/save.png"))
        self._save_act = QAction(
            icon,
            "&Save...",
            self,
            shortcut=QKeySequence.StandardKey.Save,
            statusTip="Save the current spreadsheet",
            triggered=self.save,
        )

        icon = QIcon.fromTheme("edit-undo", QIcon(":/res/undo.png"))
        self._undo_act = QAction(
            icon,
            "&Undo",
            self,
            shortcut=QKeySequence.StandardKey.Undo,
            statusTip="Undo the last editing action",
            triggered=self.undo,
        )

        self._quit_act = QAction(
            "&Quit", self, shortcut="Ctrl+Q", statusTip="Quit the application", triggered=self.close
        )

        self._about_act = QAction("&About", self, statusTip="About ripper", triggered=self.about)

        self._about_qt_act = QAction("About &Qt", self, statusTip="About Qt", triggered=QApplication.instance().aboutQt)

    # User is prompted to supply an OAuth client and authenticate with Google API
    def register_oauth(self):
        self.log.debug("Register OAuth selected")
        self.show_auth_view()

    # Start the Google OAuth authentication flow
    def authenticate_oauth(self):
        self.log.debug("Authenticate OAuth selected")
        # Start the OAuth flow
        cred = AuthManager().authorize()

        if cred:
            QMessageBox.information(self, "Authentication Successful", "Successfully authenticated with Google!")
        else:
            QMessageBox.warning(self, "Authentication Failed", "Failed to authenticate with Google. Please try again.")

    # Check if OAuth client is configured and update UI accordingly
    def update_oauth_ui(self):
        """Check if OAuth client credentials are available and update UI accordingly"""
        # Get current auth state
        state = AuthManager().auth_info().auth_state()
        has_credentials = state != AuthState.NO_CLIENT

        # Enable/disable the authenticate action based on whether credentials are available
        if hasattr(self, "_authenticate_oauth_act") and self._authenticate_oauth_act:
            self._authenticate_oauth_act.setEnabled(has_credentials)

        self.log.debug(
            f"OAuth client credentials {'found' if has_credentials else 'not found'}, "
            f"authenticate action {'enabled' if has_credentials else 'disabled'}"
        )

    def new_source(self):
        self.log.debug("New source selected")

    def show_auth_view(self):
        """Show the authentication view as a dialog"""
        self.auth_dialog = QDialog(self)
        self.auth_dialog.setWindowTitle("Google API Authentication")
        self.auth_dialog.setMinimumWidth(500)

        # Create auth view
        auth_view = AuthView(self.auth_dialog)
        auth_view.oauth_client_registered.connect(self.on_oauth_client_registered)

        # Set layout
        layout = QGridLayout(self.auth_dialog)
        layout.addWidget(auth_view)
        self.auth_dialog.setLayout(layout)

        # Show dialog
        self.auth_dialog.exec()

    def save(self):
        self.log.debug("Save selected")
        self.statusBar().showMessage(f"Saved '[filename]'", 2000)

    def undo(self):
        self.log.debug("Undo selected")

    def about(self):
        QMessageBox.about(self, "About ripper", "This is ripper")

    ####### Slots #######################################################################

    # Slot to update the auth status in the status bar
    def update_auth_status(self, info: AuthInfo):
        """Update the auth status display in the status bar"""
        if info.auth_state() == AuthState.NO_CLIENT:
            self.auth_status_label.setText("No OAuth Client")
        elif info.auth_state() == AuthState.NOT_LOGGED_IN:
            self.auth_status_label.setText("Not Logged In")
        elif info.auth_state() == AuthState.LOGGED_IN:
            self.auth_status_label.setText(f"Logged In: {info.user_email()}")
        else:
            self.auth_status_label.setText("Unknown Auth State")

        # Update UI elements that depend on auth state
        self.update_oauth_ui()

    # Slot to be called when the user successfully selects or updates the target OAuth client
    def on_oauth_client_registered(self):
        """Handle user update of target oauth client"""
        self.log.debug("User configured OAuth client credentials")

        # Close the auth dialog
        if hasattr(self, "auth_dialog") and self.auth_dialog:
            self.auth_dialog.accept()

        # Update UI to enable options only available after an OAuth client is configured
        self.update_oauth_ui()

        # Show a message that authentication was successful
        QMessageBox.information(
            self, "OAuth Client Update Successful", "OAuth Client credentials successfully updated and stored securely"
        )
