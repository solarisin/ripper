"""
OAuth Client Configuration View for the ripper application.

This module provides AuthView, a Qt widget for registering Google API OAuth client credentials
either by manual entry or by selecting a client_secret.json file. It handles UI state, validation,
and emits a signal when registration is successful.
"""

import logging
import os
from pathlib import Path

from beartype.typing import Optional
from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QFileDialog,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QRadioButton,
    QVBoxLayout,
    QWidget,
)

from ripper.ripperlib.auth import AuthManager

log = logging.getLogger("ripper:oauth_client_config_view")


class AuthView(QWidget):
    """
    Widget for registering Google API OAuth client credentials.

    Signals:
        oauth_client_registered (): Emitted when OAuth client is registered successfully.

    Allows users to either enter Google Console client ID and client secret manually,
    or select a client_secret.json file. Handles UI state, validation, and registration.
    """

    # Signal emitted when authentication is successful
    oauth_client_registered = Signal()  # Signal emitted when OAuth client is registered

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        """
        Initialize the auth view and set up the UI.

        Args:
            parent (Optional[QWidget]): Parent widget.

        Side effects:
            Sets up the widget UI and loads any stored credentials.
        """
        super().__init__(parent)
        self.setup_ui()
        self.load_credentials()

    def store_credentials(self, client_id: Optional[str] = None, client_secret: Optional[str] = None) -> None:
        """
        Store client ID and secret in AuthManager, handling exceptions.

        Args:
            client_id (Optional[str]): Google API client ID.
            client_secret (Optional[str]): Google API client secret.

        Raises:
            Shows a warning dialog if storing credentials fails.
        """
        client_id = client_id or self.client_id_edit.text()
        client_secret = client_secret or self.client_secret_edit.text()
        if client_id and client_secret:
            try:
                AuthManager().store_oauth_client_credentials(client_id, client_secret)
            except Exception as e:
                QMessageBox.warning(self, "OAuth Client Error", f"Failed to store credentials: {e}")

    def load_credentials(self) -> None:
        """
        Load client ID and secret from AuthManager and populate fields.
        """
        client_id, client_secret = AuthManager().load_oauth_client_credentials()
        self.client_id_edit.setText(client_id or "")
        self.client_secret_edit.setText(client_secret or "")

        # If we have credentials, select the manual entry option
        if client_id and client_secret:
            self.manual_radio.setChecked(True)

    def setup_ui(self) -> None:
        """
        Set up the UI components for OAuth client registration.
        """
        # Main layout
        main_layout = QVBoxLayout(self)

        # Title
        title_label = QLabel("Register Google API OAuth Client")
        title_label.setStyleSheet("font-size: 16px; font-weight: bold;")
        title_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        main_layout.addWidget(title_label)

        # Description
        desc_label = QLabel("Please provide your Google API credentials to access Google Sheets.")
        desc_label.setWordWrap(True)
        desc_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        main_layout.addWidget(desc_label)

        # Option selection
        option_group = QGroupBox("Client Registry Method")
        option_layout = QVBoxLayout()

        # Radio buttons for selection
        self.file_radio = QRadioButton("Select client_secret.json file")
        self.manual_radio = QRadioButton("Enter client ID and client secret manually")
        self.file_radio.setChecked(True)  # Default option

        option_layout.addWidget(self.file_radio)
        option_layout.addWidget(self.manual_radio)

        option_group.setLayout(option_layout)
        main_layout.addWidget(option_group)

        # File selection section
        self.file_group = QGroupBox("Select client_secret.json file")
        file_layout = QHBoxLayout()

        self.file_path_edit = QLineEdit()
        self.file_path_edit.setReadOnly(True)
        self.file_path_edit.setPlaceholderText("No file selected")

        browse_button = QPushButton("Browse...")
        browse_button.clicked.connect(self.browse_file)

        file_layout.addWidget(self.file_path_edit, 1)
        file_layout.addWidget(browse_button, 0)

        self.file_group.setLayout(file_layout)
        main_layout.addWidget(self.file_group)

        # Manual entry section
        self.manual_group = QGroupBox("Enter client credentials manually")
        manual_layout = QFormLayout()

        self.client_id_edit = QLineEdit()
        self.client_secret_edit = QLineEdit()
        self.client_secret_edit.setEchoMode(QLineEdit.EchoMode.Password)

        manual_layout.addRow("Client ID:", self.client_id_edit)
        manual_layout.addRow("Client Secret:", self.client_secret_edit)

        self.manual_group.setLayout(manual_layout)
        main_layout.addWidget(self.manual_group)

        # Connect radio buttons to update UI
        self.file_radio.toggled.connect(lambda: self.update_ui())
        self.manual_radio.toggled.connect(lambda: self.update_ui())

        # Initial UI update
        self.update_ui()

        # Authenticate button
        assign_client_button = QPushButton("Register OAuth Client")
        assign_client_button.clicked.connect(self.register_client)
        main_layout.addWidget(assign_client_button)

        # Set layout
        self.setLayout(main_layout)

    def update_ui(self) -> None:
        """
        Update UI based on selected option (file/manual).
        """
        self.file_group.setEnabled(self.file_radio.isChecked())
        self.manual_group.setEnabled(self.manual_radio.isChecked())

    def browse_file(self) -> None:
        """
        Open file dialog to select client_secret.json file.
        """

        file_path, _ = QFileDialog.getOpenFileName(
            self, "Select client_secret.json file", str(Path.home()), "JSON Files (*.json)"
        )

        if file_path:
            self.file_path_edit.setText(file_path)

    def register_client(self) -> None:
        """
        Process OAuth client registry based on selected method (file/manual).

        Raises:
            Shows a warning dialog if registration fails or input is invalid.
        """
        if self.file_radio.isChecked():
            # File selection method
            file_path = self.file_path_edit.text()
            if not file_path:
                QMessageBox.warning(self, "OAuth Client Error", "Please select a client_secret.json file.")
                return

            if not os.path.exists(file_path):
                QMessageBox.warning(self, "OAuth Client Error", "The selected file does not exist.")
                return

            # Extract credentials from the file
            client_id, client_secret = AuthManager.oauth_client_credentials_from_json(file_path)
            if not client_id or not client_secret:
                QMessageBox.warning(self, "OAuth Client Error", f"Invalid client_secret.json file: {file_path}")
                return

            # Store entered credentials and emit signal indicating successful registration
            self.store_credentials(client_id, client_secret)
            self.oauth_client_registered.emit()

        else:
            # Manual entry method
            client_id = self.client_id_edit.text()
            client_secret = self.client_secret_edit.text()

            if not client_id or not client_secret:
                QMessageBox.warning(self, "OAuth Client Error", "Please enter both Client ID and Client Secret.")
                return

            # Store credentials for future use
            self.store_credentials(client_id, client_secret)

            # Emit signal indicating successful registration
            self.oauth_client_registered.emit()

    def _get_client_secret_path(self) -> str:
        """
        Get the path to the client secret file.

        Returns:
            str: Path to the client secret file.
        """
        return os.path.join(os.environ.get("APPDATA", ""), "ripper", "client_secret.json")
