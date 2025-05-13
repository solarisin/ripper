import logging
import io
from datetime import datetime

from PySide6.QtCore import Qt, QUrl
from PySide6.QtGui import QPixmap, QImage
from PySide6.QtNetwork import QNetworkAccessManager, QNetworkRequest, QNetworkReply
from PySide6.QtWidgets import (
    QDialog,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QWidget,
    QGridLayout,
    QFrame,
    QSplitter,
)
from googleapiclient.errors import HttpError

from ripperlib.auth import AuthManager
from ripperlib.database import get_thumbnail, store_thumbnail

log = logging.getLogger("ripper:sheets_selection_view")


class SheetThumbnailWidget(QFrame):
    """Widget to display a Google Sheet thumbnail with its name"""

    def __init__(self, sheet_info, dialog=None, parent=None):
        super().__init__(parent)
        self.sheet_info = sheet_info
        self.dialog = dialog
        self.setFrameShape(QFrame.Box)
        self.setFrameShadow(QFrame.Raised)
        self.setLineWidth(1)
        self.setMinimumSize(200, 200)
        self.setMaximumSize(200, 200)

        # Set up layout
        layout = QVBoxLayout(self)

        # Thumbnail image
        self.thumbnail_label = QLabel()
        self.thumbnail_label.setAlignment(Qt.AlignCenter)
        self.thumbnail_label.setMinimumSize(180, 150)
        self.thumbnail_label.setMaximumSize(180, 150)
        self.thumbnail_label.setScaledContents(True)

        # Sheet name
        self.name_label = QLabel(sheet_info.get("name", "Unknown"))
        self.name_label.setAlignment(Qt.AlignCenter)
        self.name_label.setWordWrap(True)

        # Loading indicator
        self.loading_label = QLabel("Loading...")
        self.loading_label.setAlignment(Qt.AlignCenter)
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

    def set_default_thumbnail(self):
        """Set a default thumbnail for the sheet"""
        # Create a simple colored rectangle as default thumbnail
        pixmap = QPixmap(180, 150)
        pixmap.fill(Qt.lightGray)
        self.thumbnail_label.setPixmap(pixmap)

    def load_thumbnail(self, url, sheet_id):
        """Load thumbnail from cache or URL asynchronously"""
        # Check cache first
        cached_thumbnail = get_thumbnail(sheet_id)
        if cached_thumbnail:
            try:
                thumbnail_data = cached_thumbnail["thumbnail_data"]
                image = QImage()
                image.loadFromData(thumbnail_data)
                pixmap = QPixmap.fromImage(image)
                self.thumbnail_label.setPixmap(pixmap)
                log.debug(f"Loaded thumbnail for sheet {sheet_id} from cache")
                return
            except Exception as e:
                log.error(f"Error loading cached thumbnail: {e}")
                # Continue to load from URL if cache fails

        # Show loading indicator
        self.loading_label.show()

        # Load from URL asynchronously
        request = QNetworkRequest(QUrl(url))
        self.network_manager.get(request)
        log.debug(f"Requesting thumbnail for sheet {sheet_id} from URL: {url}")

    def handle_thumbnail_response(self, reply):
        """Handle the network reply with the thumbnail data"""
        # Hide loading indicator
        self.loading_label.hide()

        if reply.error() == QNetworkReply.NoError:
            # Get the image data
            image_data = reply.readAll().data()

            # Create image from data
            image = QImage()
            image.loadFromData(image_data)
            pixmap = QPixmap.fromImage(image)
            self.thumbnail_label.setPixmap(pixmap)

            # Store in cache if we have a sheet ID
            if "id" in self.sheet_info:
                sheet_id = self.sheet_info["id"]
                last_modified = datetime.now().isoformat()
                store_thumbnail(sheet_id, image_data, last_modified)
                log.debug(f"Stored thumbnail for sheet {sheet_id} in cache")
        else:
            log.error(f"Error loading thumbnail: {reply.errorString()}")

        # Clean up
        reply.deleteLater()

    def mousePressEvent(self, event):
        """Handle mouse press events to select this sheet"""
        super().mousePressEvent(event)
        self.setFrameShadow(QFrame.Sunken)
        if self.dialog:
            self.dialog.select_sheet(self.sheet_info)

    def mouseReleaseEvent(self, event):
        """Handle mouse release events"""
        super().mouseReleaseEvent(event)
        self.setFrameShadow(QFrame.Raised)


class SheetsSelectionDialog(QDialog):
    """Dialog for selecting Google Sheets"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Select Google Sheet")
        self.resize(1600, 900)

        self.selected_sheet = None
        self.sheets_list = []

        # Main layout
        main_layout = QVBoxLayout(self)

        # Create splitter for thumbnails and details
        splitter = QSplitter(Qt.Horizontal)

        # Left side - Thumbnails
        thumbnails_widget = QWidget()
        thumbnails_layout = QVBoxLayout(thumbnails_widget)

        # Title for thumbnails section
        thumbnails_title = QLabel("Available Google Sheets")
        thumbnails_title.setAlignment(Qt.AlignCenter)
        thumbnails_layout.addWidget(thumbnails_title)

        # Scroll area for thumbnails
        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        scroll_content = QWidget()
        self.grid_layout = QGridLayout(scroll_content)
        scroll_area.setWidget(scroll_content)
        thumbnails_layout.addWidget(scroll_area)

        # Right side - Details
        details_widget = QWidget()
        details_layout = QVBoxLayout(details_widget)

        # Title for details section
        details_title = QLabel("Sheet Details")
        details_title.setAlignment(Qt.AlignCenter)
        details_layout.addWidget(details_title)

        # Details content
        self.details_content = QLabel("Select a sheet to view details")
        self.details_content.setAlignment(Qt.AlignTop | Qt.AlignLeft)
        self.details_content.setWordWrap(True)
        details_layout.addWidget(self.details_content)

        # Add widgets to splitter
        splitter.addWidget(thumbnails_widget)
        splitter.addWidget(details_widget)
        splitter.setSizes([650, 250])  # Give more space to thumbnails grid to show all 3 columns

        main_layout.addWidget(splitter)

        # Buttons
        buttons_layout = QHBoxLayout()

        self.select_button = QPushButton("Print Sheet Info")
        self.select_button.setEnabled(False)
        self.select_button.clicked.connect(self.print_sheet_info)

        close_button = QPushButton("Close")
        close_button.clicked.connect(self.reject)

        buttons_layout.addWidget(self.select_button)
        buttons_layout.addWidget(close_button)

        main_layout.addLayout(buttons_layout)

        # Load sheets
        self.load_sheets()

    def load_sheets(self):
        """Load Google Sheets from Drive"""
        try:
            # Get Drive service
            drive_service = AuthManager().create_drive_service()
            if not drive_service:
                self.show_error("Not authenticated. Please authenticate with Google first.")
                return

            # List sheets with more fields
            self.sheets_list = self.list_sheets_with_thumbnails(drive_service)

            # Display sheets in grid
            self.display_sheets()

        except Exception as e:
            log.error(f"Error loading sheets: {e}")
            self.show_error(f"Error loading sheets: {str(e)}")

    def list_sheets_with_thumbnails(self, service):
        """List Google Sheets with thumbnail links and additional metadata"""
        files = []
        try:
            page_token = None
            while True:
                response = (
                    service.files()
                    .list(
                        q="mimeType='application/vnd.google-apps.spreadsheet'",
                        spaces="drive",
                        fields="nextPageToken, files(id, name, thumbnailLink, webViewLink, createdTime, modifiedTime, owners, size, shared)",
                        pageToken=page_token,
                    )
                    .execute()
                )
                files.extend(response.get("files", []))
                page_token = response.get("nextPageToken", None)
                if page_token is None:
                    break

        except HttpError as error:
            log.error(f"An error occurred fetching sheets list: {error}")
            files = []

        return files

    def display_sheets(self):
        """Display sheets in the grid layout"""
        # Clear existing items
        while self.grid_layout.count():
            item = self.grid_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        if not self.sheets_list:
            no_sheets_label = QLabel("No Google Sheets found in your Drive")
            no_sheets_label.setAlignment(Qt.AlignCenter)
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

    def select_sheet(self, sheet_info):
        """Handle sheet selection"""
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

        self.details_content.setText(details)

    def print_sheet_info(self):
        """Print information about the selected sheet to the log"""
        if not self.selected_sheet:
            return

        log.info("Selected Google Sheet Information:")
        log.info(f"Name: {self.selected_sheet.get('name', 'Unknown')}")
        log.info(f"ID: {self.selected_sheet.get('id', 'Unknown')}")
        log.info("To use this sheet in your code, you need:")
        log.info(f"  - Spreadsheet ID: {self.selected_sheet.get('id', 'Unknown')}")
        log.info("  - Range: 'Sheet1!A1:Z1000' (adjust according to your needs)")
        log.info("Example code:")
        log.info(f"  spreadsheet_id = '{self.selected_sheet.get('id', 'Unknown')}'")
        log.info("  range_name = 'Sheet1!A1:Z1000'")
        log.info("  service = AuthManager().create_sheets_service()")
        log.info("  data = read_data_from_spreadsheet(service, spreadsheet_id, range_name)")

        # Show confirmation to user
        self.details_content.setText(
            self.details_content.text() + "<br><br><b>Sheet information has been printed to the log.</b>"
        )

    def show_error(self, message):
        """Display error message in the dialog"""
        self.details_content.setText(f"<span style='color: red;'>{message}</span>")
