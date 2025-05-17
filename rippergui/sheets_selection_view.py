import logging
from datetime import datetime
from typing import Any, Dict, List, Optional, Set, cast

from googleapiclient.errors import HttpError
from PySide6.QtCore import QObject, QSize, Qt, QUrl, Signal, Slot
from PySide6.QtGui import QIcon, QImage, QMouseEvent, QPixmap
from PySide6.QtNetwork import QNetworkAccessManager, QNetworkReply, QNetworkRequest
from PySide6.QtWidgets import (
    QCheckBox,
    QDialog,
    QFormLayout,
    QFrame,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QScrollArea,
    QSplitter,
    QVBoxLayout,
    QWidget,
)

from ripperlib.auth import AuthManager
from ripperlib.database import get_thumbnail, store_thumbnail
from ripperlib.sheets_backend import list_sheets

log = logging.getLogger("ripper:sheets_selection_view")


class SheetThumbnailWidget(QFrame):
    """
    Widget to display a Google Sheet thumbnail with its name.

    This widget shows a thumbnail image of a Google Sheet along with its name.
    It loads the thumbnail from cache if available, or from the Google API if not.
    """

    def __init__(
        self,
        sheet_info: Dict[str, Any],
        dialog: Optional["SheetsSelectionDialog"] = None,
        parent: Optional[QWidget] = None,
    ):
        """
        Initialize the thumbnail widget.

        Args:
            sheet_info: Dictionary containing sheet information (id, name, thumbnailLink, etc.)
            dialog: Parent dialog that will handle sheet selection
            parent: Parent widget
        """
        super().__init__(parent)
        self.sheet_info: Dict[str, Any] = sheet_info
        self.dialog: Optional["SheetsSelectionDialog"] = dialog

        # Configure frame appearance
        self.setFrameShape(QFrame.Shape.Box)
        self.setFrameShadow(QFrame.Shadow.Raised)
        self.setLineWidth(1)
        self.setMinimumSize(200, 200)
        self.setMaximumSize(200, 200)

        # Set up layout
        layout = QVBoxLayout(self)

        # Sheet name - truncate long names and add tooltip
        sheet_name = sheet_info.get("name", "Unknown")
        sheet_created = sheet_info.get("createdTime")
        sheet_modified = sheet_info.get("modifiedTime")

        # Set some info about the sheet as the tooltip
        tooltip = "{:9} {}\n{:9} {}\n{:9} {}".format(
            "Name:", sheet_name, "Created:", sheet_created, "Modified:", sheet_modified
        )

        # Thumbnail image
        self.thumbnail_label = QLabel()
        self.thumbnail_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.thumbnail_label.setMinimumSize(180, 150)
        self.thumbnail_label.setMaximumSize(180, 150)
        self.thumbnail_label.setScaledContents(True)
        self.thumbnail_label.setToolTip(tooltip)

        # Create a QFontMetrics object to measure text width
        font_metrics = self.fontMetrics()
        # Get available width (slightly less than thumbnail width)
        available_width = 170

        # Check if the text needs to be elided
        if font_metrics.horizontalAdvance(sheet_name) > available_width:
            # Elide the text (add ... at the end)
            elided_text = font_metrics.elidedText(sheet_name, Qt.TextElideMode.ElideMiddle, available_width)
            sheet_name = elided_text

        self.name_label = QLabel(sheet_name)
        self.name_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.name_label.setWordWrap(False)
        self.name_label.setFixedWidth(180)
        self.name_label.setMaximumHeight(30)
        self.name_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self.name_label.setToolTip(tooltip)

        # Loading indicator
        self.loading_label = QLabel("Loading...")
        self.loading_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.loading_label.hide()  # Hide initially

        layout.addWidget(self.thumbnail_label)
        layout.addWidget(self.name_label)
        layout.addWidget(self.loading_label)

        # Create network manager for async loading
        self.network_manager = QNetworkAccessManager()
        self.network_manager.finished.connect(self.handle_thumbnail_response)

        # Set default thumbnail
        self.set_default_thumbnail()

        # Load thumbnail if available
        if "thumbnailLink" in sheet_info and "id" in sheet_info:
            self.load_thumbnail(sheet_info["thumbnailLink"], sheet_info["id"])

    def set_default_thumbnail(self) -> None:
        """
        Set a default thumbnail for the sheet.

        Creates a simple colored rectangle as a placeholder.
        """
        pixmap = QPixmap(180, 150)
        pixmap.fill(Qt.GlobalColor.lightGray)
        self.thumbnail_label.setPixmap(pixmap)

    def load_thumbnail(self, url: str, sheet_id: str) -> None:
        """
        Load thumbnail from cache or URL asynchronously.

        Args:
            url: URL to load the thumbnail from if not in cache
            sheet_id: ID of the sheet to use as cache key
        """
        # Check cache first
        cached_thumbnail = get_thumbnail(sheet_id)
        if cached_thumbnail:
            try:
                thumbnail_data = cached_thumbnail["thumbnail_data"]
                image = QImage()
                if image.loadFromData(thumbnail_data):
                    pixmap = QPixmap.fromImage(image)
                    self.thumbnail_label.setPixmap(pixmap)
                    log.debug(f"Loaded thumbnail for sheet {sheet_id} from cache")
                    return
                else:
                    log.warning(f"Failed to load image data for sheet {sheet_id} from cache")
            except KeyError as e:
                log.error(f"Missing key in cached thumbnail data: {e}")
            except Exception as e:
                log.error(f"Error loading cached thumbnail: {e}")
            # Continue to load from URL if cache fails

        # Show loading indicator
        self.loading_label.show()

        # Load from URL asynchronously
        request = QNetworkRequest(QUrl(url))
        self.network_manager.get(request)
        log.debug(f"Requesting thumbnail for sheet {sheet_id} from URL: {url}")

    def handle_thumbnail_response(self, reply: QNetworkReply) -> None:
        """
        Handle the network reply with the thumbnail data.

        Args:
            reply: Network reply containing the thumbnail data
        """
        # Hide loading indicator
        self.loading_label.hide()

        if reply.error() == QNetworkReply.NetworkError.NoError:
            try:
                # Get the image data
                image_data = reply.readAll().data()

                # Create image from data
                image = QImage()
                if image.loadFromData(image_data):
                    pixmap = QPixmap.fromImage(image)
                    self.thumbnail_label.setPixmap(pixmap)

                    # Store in cache if we have a sheet ID
                    if "id" in self.sheet_info:
                        sheet_id = self.sheet_info["id"]
                        last_modified = datetime.now().isoformat()
                        store_thumbnail(sheet_id, image_data, last_modified)
                        log.debug(f"Stored thumbnail for sheet {sheet_id} in cache")
                else:
                    log.error("Failed to load image data from network response")
                    self.set_default_thumbnail()
            except Exception as e:
                log.error(f"Error processing thumbnail data: {e}")
                self.set_default_thumbnail()
        else:
            log.error(f"Error loading thumbnail: {reply.errorString()}")
            self.set_default_thumbnail()

        # Clean up
        reply.deleteLater()

    def mousePressEvent(self, event: QMouseEvent) -> None:
        """
        Handle mouse press events to select this sheet.

        Args:
            event: Mouse event
        """
        super().mousePressEvent(event)
        self.setFrameShadow(QFrame.Shadow.Sunken)
        if self.dialog:
            self.dialog.select_sheet(self.sheet_info)

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:
        """
        Handle mouse release events.

        Args:
            event: Mouse event
        """
        super().mouseReleaseEvent(event)
        self.setFrameShadow(QFrame.Shadow.Raised)


class SheetsSelectionDialog(QDialog):
    """
    Dialog for selecting Google Sheets.

    This dialog displays a grid of thumbnails for all Google Sheets in the user's Drive,
    and allows the user to select one to view details and get information about it.
    """

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        """
        Initialize the sheets selection dialog.

        Args:
            parent: Parent widget
        """
        super().__init__(parent)
        self.setWindowTitle("Select Google Sheet")
        self.setMinimumWidth(600)
        self.setMinimumHeight(400)

        self.selected_sheet: Optional[Dict[str, Any]] = None
        self.sheets_list: List[Dict[str, Any]] = []
        self.sheet_name: str = "Sheet1"  # Default sheet name
        self.sheet_range: Optional[str] = None  # Default to None (entire table)

        # Main layout
        main_layout = QVBoxLayout(self)

        # Create splitter for thumbnails and details
        splitter = QSplitter(Qt.Orientation.Horizontal)

        # Left side - Thumbnails
        thumbnails_widget = QWidget()
        thumbnails_layout = QVBoxLayout(thumbnails_widget)

        # Title for thumbnails section
        thumbnails_title = QLabel("Available Google Sheets")
        thumbnails_title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        thumbnails_layout.addWidget(thumbnails_title)

        # Scroll area for thumbnails
        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        scroll_content = QWidget()
        self.grid_layout = QGridLayout(scroll_content)
        self.sheets_list_widget = QListWidget()
        self.sheets_list_widget.setIconSize(QSize(120, 80))
        self.sheets_list_widget.itemDoubleClicked.connect(self.on_sheet_selected)
        scroll_area.setWidget(scroll_content)
        thumbnails_layout.addWidget(scroll_area)

        # Right side - Details
        details_widget = QWidget()
        details_layout = QVBoxLayout(details_widget)

        # Title for details section
        details_title = QLabel("Sheet Details")
        details_title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        details_layout.addWidget(details_title)

        # Details content
        self.details_content = QLabel("Select a sheet to view details")
        self.details_content.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft)
        self.details_content.setWordWrap(True)
        self.details_text = ""
        details_layout.addWidget(self.details_content)

        # Advanced Options section (collapsible)
        self.advanced_options_checkbox = QCheckBox("Advanced Options")
        self.advanced_options_checkbox.setChecked(False)  # Hidden by default
        details_layout.addWidget(self.advanced_options_checkbox)

        # Advanced Options group box
        self.advanced_options_group = QGroupBox()
        self.advanced_options_group.setVisible(False)  # Hidden by default
        advanced_options_layout = QFormLayout(self.advanced_options_group)

        # Sheet name input
        self.sheet_name_input = QLineEdit(self.sheet_name)  # Default to Sheet1
        self.sheet_name_input.setPlaceholderText("Required - Default: Sheet1")
        advanced_options_layout.addRow("Sheet Name:", self.sheet_name_input)

        # Sheet range input
        self.sheet_range_input = QLineEdit()
        self.sheet_range_input.setPlaceholderText("Optional - e.g., A1:Z100")
        advanced_options_layout.addRow("Sheet Range:", self.sheet_range_input)

        details_layout.addWidget(self.advanced_options_group)

        # Connect checkbox to toggle advanced options visibility
        self.advanced_options_checkbox.toggled.connect(self.toggle_advanced_options)

        # Add widgets to splitter
        splitter.addWidget(thumbnails_widget)
        splitter.addWidget(details_widget)
        splitter.setSizes([650, 250])  # Give more space to thumbnails grid to show all 3 columns

        main_layout.addWidget(splitter)

        # Buttons
        buttons_layout = QHBoxLayout()

        self.select_button = QPushButton("Select Sheet")
        self.select_button.setEnabled(False)
        self.select_button.clicked.connect(self.print_sheet_info)

        close_button = QPushButton("Close")
        close_button.clicked.connect(self.reject)

        buttons_layout.addWidget(self.select_button)
        buttons_layout.addWidget(close_button)

        main_layout.addLayout(buttons_layout)

        # Load sheets
        self.load_sheets()

    def load_sheets(self) -> None:
        """
        Load Google Sheets from Drive.

        Fetches the list of Google Sheets from the user's Drive and displays them
        in the grid. Shows an error message if authentication fails or an error occurs.
        """
        try:
            # Get Drive service
            drive_service = AuthManager().create_drive_service()
            if not drive_service:
                self.show_error("Not authenticated. Please authenticate with Google first.")
                return

            # List sheets with more fields
            self.sheets_list = self.list_sheets_with_thumbnails(drive_service) or []
            if not self.sheets_list:
                self.show_error("Failed to fetch sheets list. Please try again.")
                return

            # Display sheets in grid
            self.display_sheets()

        except Exception as e:
            log.error(f"Error loading sheets: {e}")
            self.show_error(f"Error loading sheets: {str(e)}")

    def list_sheets_with_thumbnails(self, service: Any) -> Optional[List[Dict[str, Any]]]:
        """
        List Google Sheets with thumbnail links and additional metadata.

        This method extends the basic list_sheets functionality by requesting
        additional fields like thumbnailLink, webViewLink, etc.

        Args:
            service: Authenticated Google Drive API service

        Returns:
            List of dictionaries containing sheet information, or None if an error occurred
        """
        try:
            # Use the Drive API to list files with additional fields
            page_token = None
            files = []

            while True:
                response = (
                    service.files()
                    .list(
                        q="mimeType='application/vnd.google-apps.spreadsheet'",
                        spaces="drive",
                        fields="nextPageToken, files(id, name, thumbnailLink, webViewLink, createdTime, modifiedTime, \
                            owners, size, shared)",
                        pageToken=page_token,
                    )
                    .execute()
                )
                files.extend(response.get("files", []))
                page_token = response.get("nextPageToken", None)
                if page_token is None:
                    break

            log.debug(f"Found {len(files)} sheets with thumbnail information")
            return files

        except HttpError as error:
            log.error(f"An error occurred fetching sheets list: {error}")
            return None

    def display_sheets(self) -> None:
        """
        Display sheets in the grid layout.

        Clears any existing widgets in the grid and adds thumbnails for each sheet.
        If no sheets are found, displays a message.
        """
        # Clear existing items
        while self.grid_layout.count():
            item = self.grid_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        if not self.sheets_list:
            no_sheets_label = QLabel("No Google Sheets found in your Drive")
            no_sheets_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            self.grid_layout.addWidget(no_sheets_label, 0, 0)
            return

        # Add sheets to grid
        row, col = 0, 0
        max_cols = 3  # Number of columns in the grid

        for sheet in self.sheets_list:
            thumbnail = SheetThumbnailWidget(sheet, dialog=self)
            self.grid_layout.addWidget(thumbnail, row, col)

            col += 1
            if col >= max_cols:
                col = 0
                row += 1

    def select_sheet(self, sheet_info: Dict[str, Any]) -> None:
        """
        Handle sheet selection.

        Updates the UI to show details about the selected sheet and enables
        the select button.

        Args:
            sheet_info: Dictionary containing information about the selected sheet
        """
        self.selected_sheet = sheet_info
        self.select_button.setEnabled(True)

        # Update details view
        details = f"<b>Name:</b> {sheet_info.get('name', 'Unknown')}<br>"
        details += f"<b>ID:</b> {sheet_info.get('id', 'Unknown')}<br>"

        if "createdTime" in sheet_info:
            details += f"<b>Created:</b> {sheet_info['createdTime']}<br>"

        if "modifiedTime" in sheet_info:
            details += f"<b>Modified:</b> {sheet_info['modifiedTime']}<br>"

        if "owners" in sheet_info and sheet_info["owners"]:
            owner = sheet_info["owners"][0]
            details += f"<b>Owner:</b> {owner.get('displayName', 'Unknown')}<br>"

        if "shared" in sheet_info:
            details += f"<b>Shared:</b> {'Yes' if sheet_info['shared'] else 'No'}<br>"

        if "webViewLink" in sheet_info:
            details += f"<b>Web Link:</b> <a href='{sheet_info['webViewLink']}'>{sheet_info['webViewLink']}</a><br>"

        # Update sheet name in advanced options if not already modified by user
        if self.sheet_name_input.text() == "Sheet1" and not self.sheet_name_input.isModified():
            self.sheet_name_input.setText("Sheet1")
            self.sheet_name_input.setModified(False)  # Reset modified state
        self.details_text = details
        self.details_content.setText(self.details_text)

    def print_sheet_info(self) -> None:
        """
        Process the selected sheet with advanced options.

        Gets the sheet name and range from the advanced options,
        logs details about the selected sheet, and shows a confirmation message
        in the details panel.
        """
        if not self.selected_sheet:
            return

        # Get sheet name and range from advanced options
        sheet_name = self.sheet_name_input.text().strip()
        sheet_range = self.sheet_range_input.text().strip()

        # Validate sheet name (required)
        if not sheet_name:
            self.show_error("Sheet name is required. Please enter a sheet name in the Advanced Options.")
            self.advanced_options_checkbox.setChecked(True)  # Show advanced options
            self.sheet_name_input.setFocus()
            return

        # Store the values for later use
        self.sheet_name = sheet_name
        self.sheet_range = sheet_range if sheet_range else None

        # Construct the range string
        range_string = f"{sheet_name}"
        if sheet_range:
            range_string += f"!{sheet_range}"

        log.info("Selected Google Sheet Information:")
        log.info(f"Spreadsheet Name: {self.selected_sheet.get('name', 'Unknown')}")
        log.info(f"ID: {self.selected_sheet.get('id', 'Unknown')}")
        log.info(f"Worksheet Name: {sheet_name}")
        log.info(f"Worksheet Range: {sheet_range if sheet_range else 'Entire table'}")

        # Show confirmation to user with sheet name and range
        confirmation = "<br><br><b>Sheet information has been printed to the log.</b><br>"
        confirmation += f"<b>Sheet Name:</b> {sheet_name}<br>"
        confirmation += f"<b>Sheet Range:</b> {sheet_range if sheet_range else 'Entire table'}"
        log.info(self.details_text + confirmation)
        self.details_content.setText(self.details_text + confirmation)

    def toggle_advanced_options(self, checked: bool) -> None:
        """
        Toggle the visibility of the advanced options section.

        Args:
            checked: Whether the checkbox is checked
        """
        self.advanced_options_group.setVisible(checked)

    def show_error(self, message: str) -> None:
        """
        Display error message in the dialog.

        Args:
            message: The error message to display
        """
        self.details_content.setText(f"<span style='color: red;'>{message}</span>")

    @Slot()
    def on_sheet_selected(self) -> None:
        """Handle sheet selection."""
        current_item = self.sheets_list_widget.currentItem()
        if not current_item:
            return

        sheet_data = current_item.data(Qt.ItemDataRole.UserRole)
        if not sheet_data:
            return

        self.accept()
