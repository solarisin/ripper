import os
import json
import keyring
from pathlib import Path
from PySide6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QLabel, 
                              QLineEdit, QPushButton, QFileDialog, QRadioButton,
                              QGroupBox, QFormLayout, QMessageBox)
from PySide6.QtCore import Signal, Qt

class AuthView(QWidget):
    """
    A view that allows users to either enter Google Console client ID and client secret,
    or select a client_secret.json file.
    """

    # Signal emitted when authentication is successful
    oauth_client_registered = Signal()  # Signal emitted when OAuth client is registered

    # Constants for keyring
    KEYRING_SERVICE = "ripper-oauth-client"
    KEYRING_USERNAME = "default-user"

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setup_ui()
        self.load_credentials_from_keyring()

    def store_credentials_in_keyring(self, client_id, client_secret):
        """Store client ID and secret in keyring"""
        credentials = {
            "client_id": client_id,
            "client_secret": client_secret
        }
        keyring.set_password(self.KEYRING_SERVICE, self.KEYRING_USERNAME, json.dumps(credentials))

        # Update auth state after storing credentials
        from src.auth import auth_manager
        auth_manager.update_auth_state()

    def load_credentials_from_keyring(self):
        """Load client ID and secret from keyring and populate fields"""
        try:
            credentials_json = keyring.get_password(self.KEYRING_SERVICE, self.KEYRING_USERNAME)
            if credentials_json:
                credentials = json.loads(credentials_json)
                self.client_id_edit.setText(credentials.get("client_id", ""))
                self.client_secret_edit.setText(credentials.get("client_secret", ""))
                # If we have credentials, select the manual entry option
                if credentials.get("client_id") and credentials.get("client_secret"):
                    self.manual_radio.setChecked(True)
        except Exception as e:
            # If there's any error loading credentials, just continue without them
            pass

    def setup_ui(self):
        # Main layout
        main_layout = QVBoxLayout(self)

        # Title
        title_label = QLabel("Register Google API OAuth Client")
        title_label.setStyleSheet("font-size: 16px; font-weight: bold;")
        title_label.setAlignment(Qt.AlignCenter)
        main_layout.addWidget(title_label)

        # Description
        desc_label = QLabel("Please provide your Google API credentials to access Google Sheets.")
        desc_label.setWordWrap(True)
        desc_label.setAlignment(Qt.AlignCenter)
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
        self.client_secret_edit.setEchoMode(QLineEdit.Password)

        manual_layout.addRow("Client ID:", self.client_id_edit)
        manual_layout.addRow("Client Secret:", self.client_secret_edit)

        self.manual_group.setLayout(manual_layout)
        main_layout.addWidget(self.manual_group)

        # Connect radio buttons to update UI
        self.file_radio.toggled.connect(self.update_ui)
        self.manual_radio.toggled.connect(self.update_ui)

        # Initial UI update
        self.update_ui()

        # Authenticate button
        assign_client_button = QPushButton("Register OAuth Client")
        assign_client_button.clicked.connect(self.register_client)
        main_layout.addWidget(assign_client_button)

        # Set layout
        self.setLayout(main_layout)

    def update_ui(self):
        """Update UI based on selected option"""
        self.file_group.setEnabled(self.file_radio.isChecked())
        self.manual_group.setEnabled(self.manual_radio.isChecked())

    def browse_file(self):
        """Open file dialog to select client_secret.json file"""

        file_path, _ = QFileDialog.getOpenFileName(
            self, "Select client_secret.json file", str(Path.home()), "JSON Files (*.json)"
        )

        if file_path:
            self.file_path_edit.setText(file_path)

    def register_client(self):
        """Process oauth client registry based on selected method"""
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
            try:
                with open(file_path, 'r') as f:
                    client_data = json.load(f)

                # Extract client ID and secret from the file
                if 'installed' in client_data:
                    client_id = client_data['installed'].get('client_id')
                    client_secret = client_data['installed'].get('client_secret')

                    if not client_id or not client_secret:
                        QMessageBox.warning(self, "OAuth Client Error", 
                                          "The selected file does not contain valid client ID and secret.")
                        return

                    # Store credentials in keyring
                    self.store_credentials_in_keyring(client_id, client_secret)
                else:
                    QMessageBox.warning(self, "OAuth Client Error", 
                                      "The selected file does not have the expected format.")
                    return
            except Exception as e:
                QMessageBox.warning(self, "OAuth Client Error", 
                                  f"Error reading the selected file: {str(e)}")
                return

            # Emit signal indicating successful registration
            self.oauth_client_registered.emit()

        else:
            # Manual entry method
            client_id = self.client_id_edit.text()
            client_secret = self.client_secret_edit.text()

            if not client_id or not client_secret:
                QMessageBox.warning(self, "OAuth Client Error", "Please enter both Client ID and Client Secret.")
                return

            # Store credentials in keyring for future use
            self.store_credentials_in_keyring(client_id, client_secret)

            # Emit signal indicating successful registration
            self.oauth_client_registered.emit()
