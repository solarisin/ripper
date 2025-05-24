import logging
import re
from datetime import datetime

from PySide6.QtCore import QSize, Qt, QUrl, Signal
from PySide6.QtGui import QCursor, QImage, QMouseEvent, QPixmap
from PySide6.QtNetwork import QNetworkAccessManager, QNetworkReply, QNetworkRequest
from PySide6.QtWidgets import (
    QApplication,
    QComboBox,
    QDialog,
    QFormLayout,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QPushButton,
    QScrollArea,
    QSplitter,
    QVBoxLayout,
    QWidget,
)
from beartype.typing import Any, Dict, List, Optional, cast

from ripper.ripperlib.auth import AuthManager
from ripper.ripperlib.database import Db
from ripper.ripperlib.defs import SheetProperties
from ripper.ripperlib.sheets_backend import fetch_and_store_spreadsheets, read_spreadsheet_metadata

log = logging.getLogger("ripper:sheets_selection_view")


def col_to_letter(col_index: int) -> str:
    """
    Convert column index to letter (A=1, B=2, etc.).
    """
    letter = ""
    while col_index > 0:
        col_index, remainder = divmod(col_index - 1, 26)
        letter = chr(65 + remainder) + letter
    return letter


def parse_cell(cell_text: str) -> tuple[int, int]:
    """
    Basic parsing of cell like A1, B5.

    Args:
        cell_text: The cell text (e.g., "A1").

    Returns:
        A tuple containing the row number (1-indexed) and column number (1-indexed).

    Raises:
        ValueError: If the cell format is invalid.
    """
    col_str = "".join(filter(str.isalpha, cell_text))
    row_str = "".join(filter(str.isdigit, cell_text))
    if not col_str or not row_str:
        raise ValueError("Invalid cell format")

    # Convert column letter to number (A=1, B=2, ...)
    col_num = 0
    for char in col_str.upper():
        col_num = col_num * 26 + (ord(char) - ord("A") + 1)
    row_num = int(row_str)
    return row_num, col_num


class SpreadsheetThumbnailWidget(QFrame):
    """
    Widget to display a Google Spreadsheet thumbnail with its name.

    This widget shows a thumbnail image of a Google Spreadsheet along with its name.
    It loads the thumbnail from cache if available, or from the Google API if not.
    """

    def __init__(
        self,
        sheet_info: Dict[str, Any],
        parent: Optional[QWidget] = None,
    ):
        """
        Initialize the thumbnail widget.

        Args:
            sheet_info: Dictionary containing spreadsheet information (id, name, thumbnailLink, etc.)
            dialog: Parent dialog that will handle spreadsheet selection
            parent: Parent widget
        """
        super().__init__(parent)
        self.spreadsheet_info: Dict[str, Any] = sheet_info
        self.sheet_id: Optional[str] = sheet_info.get("id")  # sheet id is for a spreadsheet
        self.dialog: Optional[SheetsSelectionDialog] = cast(SheetsSelectionDialog, parent)

        # Configure frame appearance
        self.setFrameShape(QFrame.Shape.Box)
        self.setFrameShadow(QFrame.Shadow.Raised)
        self.setLineWidth(1)
        self.setMinimumSize(200, 200)
        self.setMaximumSize(200, 200)

        # Set up layout
        layout = QVBoxLayout(self)

        # Sheet name - truncate long names and add tooltip
        spreadsheet_name = sheet_info.get("name", "Unknown")
        spreadsheet_created = sheet_info.get("createdTime")
        spreadsheet_modified = sheet_info.get("modifiedTime")

        # Set some info about the sheet as the tooltip
        tooltip = "{:9} {}\n{:9} {}\n{:9} {}".format(
            "Name:", spreadsheet_name, "Created:", spreadsheet_created, "Modified:", spreadsheet_modified
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
        if font_metrics.horizontalAdvance(spreadsheet_name) > available_width:
            # Elide the text (add ... at the end)
            elided_text = font_metrics.elidedText(spreadsheet_name, Qt.TextElideMode.ElideMiddle, available_width)
            spreadsheet_name = elided_text

        self.name_label = QLabel(spreadsheet_name)
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

    def load_thumbnail(self, url: str, spreadsheet_id: str) -> None:
        """
        Load thumbnail from cache or URL asynchronously.

        Args:
            url: URL to load the thumbnail from if not in cache
            sheet_id: ID of the sheet to use as cache key
        """
        # Check cache first
        cached_thumbnail = Db().get_spreadsheet_thumbnail(spreadsheet_id)
        if cached_thumbnail:
            try:
                thumbnail_data = cached_thumbnail["thumbnail"]
                image = QImage()
                if image.loadFromData(thumbnail_data):
                    pixmap = QPixmap.fromImage(image)
                    self.thumbnail_label.setPixmap(pixmap)
                    log.debug(f"Loaded thumbnail for spreadsheet id {spreadsheet_id} from cache")
                    return
                else:
                    log.warning(f"Failed to load image data for spreadsheet id {spreadsheet_id} from cache")
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
        log.debug(f"Requesting thumbnail for spreadsheet id {spreadsheet_id} from URL: {url}")

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

                    # Store in cache if we have a spreadsheet ID
                    if "id" in self.spreadsheet_info:
                        spreadsheet_id = self.spreadsheet_info["id"]
                        modifiedTime = datetime.now().isoformat()
                        Db().store_spreadsheet_thumbnail(spreadsheet_id, image_data, modifiedTime)
                        log.debug(f"Stored thumbnail for spreadsheet id {spreadsheet_id} in cache")
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
        Handle mouse press events to select this spreadsheet.

        Args:
            event: Mouse event
        """
        super().mousePressEvent(event)
        self.setFrameShadow(QFrame.Shadow.Sunken)
        if self.dialog:
            self.dialog.select_spreadsheet(self.spreadsheet_info)

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

    # Signal emitted when the user chooses a sheet
    sheet_selected = Signal(dict)

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
        self.resize(1600, 900)

        self.selected_sheet: Optional[Dict[str, Any]] = None
        self.sheets_list: List[Dict[str, Any]] = []
        self.all_sheet_properties: Dict[str, List[SheetProperties]] = {}

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

        # Sheet name and range input
        advanced_options_layout = QFormLayout()

        # Sheet name combobox
        self.sheet_name_combobox = QComboBox()
        advanced_options_layout.addRow("Sheet Name:", self.sheet_name_combobox)

        # Sheet range input
        self.sheet_range_input = QLineEdit()
        advanced_options_layout.addRow("Sheet Range:", self.sheet_range_input)
        self.sheet_range_input.textChanged.connect(self._validate_sheet_range)

        # Add the form layout directly to details_layout
        details_layout.addLayout(advanced_options_layout)

        # Add widgets to splitter
        splitter.addWidget(thumbnails_widget)
        splitter.addWidget(details_widget)
        splitter.setSizes([650, 250])  # Give more space to thumbnails grid to show all 3 columns

        main_layout.addWidget(splitter)

        # Buttons
        buttons_layout = QHBoxLayout()

        self.select_button = QPushButton("Select Sheet")
        self.select_button.setEnabled(False)
        self.select_button.clicked.connect(self.user_confirmed_sheet)

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
            sheets_service = AuthManager().create_sheets_service()
            if not drive_service or not sheets_service:
                self.show_error("Not authenticated. Please authenticate with Google first.")
                return

            # Fetch and store sheets using the backend function
            db = Db()
            self.sheets_list = fetch_and_store_spreadsheets(drive_service, db) or []
            if not self.sheets_list:
                self.show_error("Failed to fetch and store sheets list. Please try again.")
                return

            # Display sheets in grid
            self.display_sheets()

        except Exception as e:
            log.error(f"Error loading sheets: {e}")
            self.show_error(f"Error loading sheets: {str(e)}")

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
            thumbnail = SpreadsheetThumbnailWidget(sheet, parent=self)
            self.grid_layout.addWidget(thumbnail, row, col)

            col += 1
            if col >= max_cols:
                col = 0
                row += 1

    def select_spreadsheet(self, spreadsheet_info: Dict[str, Any]) -> None:
        """
        Handle spreadsheet selection.

        Updates the UI to show details about the selected spreadsheet and enables
        the select button.

        Args:
            spreadsheet_info: Dictionary containing information about the selected spreadsheet
        """
        self.selected_sheet = spreadsheet_info
        self.select_button.setEnabled(True)

        # Update details view
        details = f"<b>Name:</b> {spreadsheet_info['name']}<br>"
        details += f"<b>ID:</b> {spreadsheet_info['id']}<br>"

        if "createdTime" in spreadsheet_info:
            details += f"<b>Created:</b> {spreadsheet_info['createdTime']}<br>"

        if "modifiedTime" in spreadsheet_info:
            details += f"<b>Modified:</b> {spreadsheet_info['modifiedTime']}<br>"

        if "owners" in spreadsheet_info and spreadsheet_info["owners"]:
            owner = spreadsheet_info["owners"][0]
            details += f"<b>Owner:</b> {owner.get('displayName', 'Unknown')}<br>"

        if "shared" in spreadsheet_info:
            details += f"<b>Shared:</b> {'Yes' if spreadsheet_info['shared'] else 'No'}<br>"

        if "webViewLink" in spreadsheet_info:
            details += "<b>Web Link:</b>"
            details += f"<a href='{spreadsheet_info['webViewLink']}'>{spreadsheet_info['webViewLink']}</a><br>"

        # Update sheet name in advanced options if not already modified by user
        self.details_text = details
        self.details_content.setText(self.details_text)

        self._load_and_cache_sheet_metadata(spreadsheet_info)
        self._update_sheet_details(spreadsheet_info)

    def _load_and_cache_sheet_metadata(self, spreadsheet_info: Dict[str, Any]) -> None:
        """
        Load sheet metadata from cache or API and store in cache.
        """
        sheets_service = AuthManager().create_sheets_service()
        if sheets_service:
            spreadsheet_id = spreadsheet_info["id"]
            modified_time = spreadsheet_info.get("modifiedTime")

            cached_metadata: Optional[Dict[str, Any]] = None
            if modified_time:
                cached_metadata = Db().get_sheet_metadata(spreadsheet_id, modified_time)

            sheets_properties: Optional[List[SheetProperties]] = None

            if cached_metadata is None:
                log.debug(f"Metadata for sheet {spreadsheet_id} not found in cache or is outdated. Fetching from API.")
                QApplication.setOverrideCursor(QCursor(Qt.CursorShape.WaitCursor))
                api_metadata = read_spreadsheet_metadata(sheets_service, spreadsheet_id)
                if api_metadata is not None and modified_time:
                    # Convert list of SheetProperties to a dictionary for caching
                    metadata_to_cache = {"sheets": [sheet.to_dict() for sheet in api_metadata]}
                    Db().store_sheet_metadata(spreadsheet_id, metadata_to_cache, modified_time)
                    log.debug(f"Stored metadata for sheet {spreadsheet_id} in cache.")
                    sheets_properties = api_metadata
                    QApplication.restoreOverrideCursor()
                else:
                    log.error("Failed to fetch metadata from API")
                    sheets_properties = None
            else:
                log.debug(f"Metadata for sheet {spreadsheet_id} found in cache.")
                # Convert cached dictionary back to list of SheetProperties
                if "sheets" in cached_metadata:
                    try:
                        sheets_properties = []
                        for sheet_dict in cached_metadata["sheets"]:
                            # Create a properly structured dictionary for SheetProperties
                            sheet_info = {
                                "properties": {
                                    "sheetId": sheet_dict["sheetId"],
                                    "index": sheet_dict["index"],
                                    "title": sheet_dict["title"],
                                    "sheetType": sheet_dict["sheetType"],
                                    "gridProperties": sheet_dict["gridProperties"],
                                }
                            }
                            sheets_properties.append(SheetProperties(sheet_info))
                    except Exception as e:
                        log.error(f"Error converting cached metadata to SheetProperties: {e}")
                        sheets_properties = None  # Invalidate cached data if conversion fails

            if sheets_properties is not None:
                log.debug(f"Spreadsheet contains {len(sheets_properties)} sheets")
                # Store the sheet properties
                self.all_sheet_properties[spreadsheet_id] = sheets_properties

    def _update_sheet_details(self, spreadsheet_info: Dict[str, Any]) -> None:
        """
        Update the sheet name combobox and range input based on the selected spreadsheet's metadata.
        """
        spreadsheet_id = spreadsheet_info["id"]
        sheets_properties = self.all_sheet_properties.get(spreadsheet_id)

        # Block signals temporarily instead of disconnecting
        old_state = self.sheet_name_combobox.blockSignals(True)

        self.sheet_name_combobox.clear()
        self.sheet_range_input.clear()

        if sheets_properties:
            sheet_names = [sheet.title for sheet in sheets_properties]
            self.sheet_name_combobox.addItems(sheet_names)

            # Restore the previous signal blocking state
            self.sheet_name_combobox.blockSignals(old_state)

            # Connect the signal if not already connected
            # This is safe to call multiple times as it won't create duplicate connections
            self.sheet_name_combobox.currentIndexChanged.connect(self._sheet_name_selected)

            # Select the first sheet by default and update the range
            if sheet_names:
                self.sheet_name_combobox.setCurrentIndex(0)
                # Explicitly call the function to ensure it runs
                self._sheet_name_selected(0)

    def _sheet_name_selected(self, index: int) -> None:
        """
        Handle sheet name selection from the combobox and update the range input.
        """
        if self.selected_sheet and index >= 0:
            spreadsheet_id = self.selected_sheet["id"]
            sheets_properties = self.all_sheet_properties.get(spreadsheet_id)

            if sheets_properties and index < len(sheets_properties):
                selected_sheet_props = sheets_properties[index]

                # Calculate the range (e.g., Sheet1!A1:Z100)
                row_count = selected_sheet_props.grid.row_count
                col_count = selected_sheet_props.grid.column_count

                # Convert column index to letter (A=1, B=2, etc.)
                end_column_letter = col_to_letter(col_count)

                sheet_range = f"A1:{end_column_letter}{row_count}"
                self.sheet_range_input.setText(sheet_range)
                # Store the full calculated range for validation
                self._current_full_range = sheet_range
                # Also trigger validation for the pre-filled text
                self._validate_sheet_range(sheet_range)
        else:
            self.sheet_range_input.clear()
            self.select_button.setEnabled(False)
            return

    def _validate_sheet_range(self, text: str) -> None:
        """
        Validates the sheet range input by checking if it's empty,
        has a valid format, and is within the sheet dimensions.
        """
        if not self._is_range_empty(text):
            return

        if not self._is_range_format_valid(text):
            return

        # Get sheet dimensions for bounds check
        sheet_row_count = 0
        sheet_col_count = 0
        if self.selected_sheet:
            spreadsheet_id = self.selected_sheet["id"]
            sheets_properties = self.all_sheet_properties.get(spreadsheet_id)
            if sheets_properties:
                current_sheet_name = self.sheet_name_combobox.currentText().strip()
                for sheet_props in sheets_properties:
                    if sheet_props.title == current_sheet_name:
                        sheet_row_count = sheet_props.grid.row_count
                        sheet_col_count = sheet_props.grid.column_count
                        break

        # Only perform bounds check if dimensions are available
        if sheet_row_count > 0 and sheet_col_count > 0:
            if not self._is_range_within_bounds(text, sheet_row_count, sheet_col_count):
                return
            # If bounds are valid, proceed to enable button
            self.details_content.setText(self.details_text)  # Restore original details text
            self.select_button.setEnabled(True)
        else:
            # If dimensions are not available, format is valid, but bounds can't be checked.
            # Treat as valid for now, but this might need refinement based on desired UX.
            self.details_content.setText("Warning: Cannot validate range bounds (sheet dimensions not available).")
            self.select_button.setEnabled(True)

    def _is_range_empty(self, text: str) -> bool:
        """
        Checks if the range input is empty.
        """
        if not text.strip():
            self.show_error("Sheet range cannot be empty.")
            self.select_button.setEnabled(False)
            return False
        return True

    def _is_range_format_valid(self, text: str) -> bool:
        """
        Checks if the range input matches the expected A1:B5 format.
        """
        range_pattern = r"^[a-zA-Z]+\d+:[a-zA-Z]+\d+$"
        if not re.match(range_pattern, text):
            self.show_error("Invalid range format. Expected A1:B5.")
            self.select_button.setEnabled(False)
            return False
        return True

    def _is_range_within_bounds(self, text: str, sheet_row_count: int, sheet_col_count: int) -> bool:
        """
        Checks if the range is within the sheet dimensions.
        """
        try:
            parts = text.split(":")
            start_cell_text = parts[0]
            end_cell_text = parts[1]

            start_row, start_col = parse_cell(start_cell_text)
            end_row, end_col = parse_cell(end_cell_text)

            # Check if the range is within the sheet dimensions and is valid (start <= end)
            if (
                start_row < 1
                or start_col < 1
                or end_row > sheet_row_count
                or end_col > sheet_col_count
                or start_row > end_row
                or start_col > end_col
            ):
                self.show_error(
                    f"Range ({text}) outside dimensions (A1:{col_to_letter(sheet_col_count)}{sheet_row_count})."
                )
                self.select_button.setEnabled(False)
                return False

        except ValueError:
            # If parsing fails, it's an invalid format for bounds check
            self.show_error("Could not parse range for bounds check. Use A1:B5 format.")
            self.select_button.setEnabled(False)
            return False

        return True

    def print_spreadsheet_info(self, spreadsheet_info: Dict[str, Any]) -> None:
        """
        Gets the sheet name and range from the advanced options and
        logs details about the selected sheet.
        """
        spreadsheet_name = spreadsheet_info.get("name")
        spreadsheet_id = spreadsheet_info.get("id")
        sheet_name = spreadsheet_info.get("sheet_name")
        sheet_range = spreadsheet_info.get("sheet_range")

        log.info("Selected Google Sheet Information:")
        log.info(f"Spreadsheet Name: {spreadsheet_name}")
        log.info(f"Spreadsheet ID: {spreadsheet_id}")
        log.info(f"Sheet Name: {sheet_name}")
        log.info(f"Sheet Range: {sheet_range}")

    def user_confirmed_sheet(self) -> None:
        if not self.selected_sheet:
            return

        try:
            spreadsheet_name = self.selected_sheet.get("name")
            spreadsheet_id = self.selected_sheet.get("id")
        except KeyError as e:
            log.error(f"Missing required data key in selected sheet: {e}")
            return

        # Get sheet name and range from the combobox and line edit
        sheet_name = self.sheet_name_combobox.currentText().strip()
        sheet_range = self.sheet_range_input.text().strip()

        # Validate sheet name (required)
        if not sheet_name:
            self.show_error("Sheet name is required. Please enter a sheet name in the Advanced Options.")
            self.sheet_name_combobox.setFocus()
            return

        # Validate the entered sheet range before proceeding
        self._validate_sheet_range(sheet_range)
        if not self.select_button.isEnabled():
            return

        sheet_info = {
            "spreadsheet_name": spreadsheet_name,
            "spreadsheet_id": spreadsheet_id,
            "sheet_name": sheet_name,
            "sheet_range": sheet_range,
        }

        self.print_spreadsheet_info(sheet_info)

        self.sheet_selected.emit(sheet_info)

    def show_error(self, message: str) -> None:
        """
        Display error message in the dialog.

        Args:
            message: The error message to display
        """
        # Append the error message below the existing text
        current_text = self.details_content.text()
        if not current_text.endswith("<br>"):
            # Add a line break if the current text doesn't end with one
            current_text += "<br>"
        self.details_content.setText(f"{current_text}<br><br><br><span style='color: red;'>{message}</span>")
