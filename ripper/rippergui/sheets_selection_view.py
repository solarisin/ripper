"""
Dialog for selecting and validating Google Sheets and ranges in the ripper application.

This module provides SheetsSelectionDialog, a Qt dialog for browsing, selecting, and validating Google Sheets
and their ranges. It includes input validation, error feedback, and emits a signal when a sheet and range are selected.

"""

import traceback

from beartype.typing import Optional
from loguru import logger
from PySide6.QtCore import QSize, Qt, Signal
from PySide6.QtWidgets import (
    QApplication,
    QComboBox,
    QDialog,
    QFormLayout,
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

import ripper.ripperlib.sheets_backend as sheets_backend
from ripper.rippergui.sheet_utils import col_to_letter
from ripper.rippergui.spreadsheet_thumbnail_widget import SpreadsheetThumbnailWidget
from ripper.ripperlib.auth import AuthManager
from ripper.ripperlib.defs import SheetProperties, SpreadsheetProperties


class SheetsSelectionDialog(QDialog):
    """
    Dialog for selecting Google Sheets and specifying a range.

    Signals:
        sheet_selected (dict): Emitted when the user confirms a sheet and range selection.

    This dialog displays a grid of thumbnails for all Google Sheets in the user's Drive,
    allows the user to select one, view details, and specify a range for further operations.
    Input is validated and errors are shown in the dialog.
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

        self.selected_spreadsheet: SpreadsheetProperties | None = None
        self.sheet_properties_list: list[SheetProperties] = []

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
        self.sheet_range_input.textChanged.connect(lambda text: self._validate_sheet_range(text) if text else None)

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

        # Load spreadsheets
        self.load_spreadsheets()

    def load_spreadsheets(self) -> None:
        """
        Load Google Spreadsheets from Drive and display them in the grid.

        Fetches the list of Google Spreadsheets from the user's Drive and displays them
        in the grid. Shows an error message if authentication fails or an error occurs.
        """
        try:
            # Get Drive service
            drive_service = AuthManager().create_drive_service()
            if not drive_service:
                self.show_error("Not authenticated. Please authenticate with Google first.")
                return

            # Fetch and store sheets using the backend function
            QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
            self.spreadsheets_list = sheets_backend.retrieve_spreadsheets(drive_service)
            QApplication.restoreOverrideCursor()

            # Display sheets in grid
            self.display_spreadsheets()

        except Exception as e:
            logger.error(f"Error loading sheets: {e}, {traceback.format_exc()}")
            self.show_error(f"Error loading sheets: {str(e)}")

    def display_spreadsheets(self) -> None:
        """
        Display spreadsheets in the grid layout.

        Clears any existing widgets in the grid and adds thumbnails for each spreadsheet.
        If no spreadsheets are found, displays a message.
        """
        # Clear existing items
        while self.grid_layout.count():
            item = self.grid_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        if not self.spreadsheets_list:
            no_sheets_label = QLabel("No Google Spreadsheets found in your Drive")
            no_sheets_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            self.grid_layout.addWidget(no_sheets_label, 0, 0)
            return

        # Add spreadsheets to grid
        row, col = 0, 0
        max_cols = 3  # Number of columns in the grid

        for spreadsheet in self.spreadsheets_list:
            thumb_widget = SpreadsheetThumbnailWidget(spreadsheet, parent=self)
            thumb_widget.spreadsheet_selected.connect(
                lambda spreadsheet_properties: self.select_spreadsheet(spreadsheet_properties)
            )
            self.grid_layout.addWidget(thumb_widget, row, col)
            col += 1
            if col >= max_cols:
                col = 0
                row += 1

    def select_spreadsheet(self, spreadsheet_properties: SpreadsheetProperties) -> None:
        """
        Handle spreadsheet selection from the grid.

        Updates the UI to show details about the selected spreadsheet and enables
        the select button. Called directly from the thumbnail widget.

        Args:
            spreadsheet_properties (SpreadsheetProperties): Spreadsheet information.
        """
        self.selected_spreadsheet = spreadsheet_properties
        self.select_button.setEnabled(True)

        # Update details view
        details = f"<b>Name:</b> {spreadsheet_properties.name}<br>"
        details += f"<b>ID:</b> {spreadsheet_properties.id}<br>"

        if spreadsheet_properties.created_time:
            details += f"<b>Created:</b> {spreadsheet_properties.created_time}<br>"

        if spreadsheet_properties.modified_time:
            details += f"<b>Modified:</b> {spreadsheet_properties.modified_time}<br>"

        if spreadsheet_properties.owners:
            owner = spreadsheet_properties.owners[0]
            details += f"<b>Owner:</b> {owner.get('displayName', 'Unknown')}<br>"

        if spreadsheet_properties.shared:
            details += f"<b>Shared:</b> {'Yes' if spreadsheet_properties.shared else 'No'}<br>"

        if spreadsheet_properties.web_view_link:
            details += "<b>Web Link:</b>"
            details += (
                f"<a href='{spreadsheet_properties.web_view_link}'>{spreadsheet_properties.web_view_link}</a><br>"
            )

        # Update sheet name in advanced options if not already modified by user
        self.details_text = details
        self.details_content.setText(self.details_text)

        sheets_service = AuthManager().create_sheets_service()
        if sheets_service:
            spreadsheet_id = spreadsheet_properties.id
            QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
            self.sheet_properties_list = sheets_backend.retrieve_sheets_of_spreadsheet(sheets_service, spreadsheet_id)
            logger.debug(f"Spreadsheet contains {len(self.sheet_properties_list)} sheets")
            QApplication.restoreOverrideCursor()

        # Block signals temporarily instead of disconnecting
        old_state = self.sheet_name_combobox.blockSignals(True)

        self.sheet_name_combobox.clear()
        self.sheet_range_input.clear()

        if len(self.sheet_properties_list) > 0:
            sheet_names = [sheet.title for sheet in self.sheet_properties_list]
            self.sheet_name_combobox.addItems(sheet_names)

            # Connect the signal if not already connected
            # This is safe to call multiple times as it won't create duplicate connections
            self.sheet_name_combobox.currentIndexChanged.connect(self._sheet_name_selected)

            # Select the first sheet by default and update the range
            if sheet_names:
                self.sheet_name_combobox.setCurrentIndex(0)
                # Explicitly call the function to ensure it runs
                self._sheet_name_selected(0)

        # Restore the previous signal blocking state
        self.sheet_name_combobox.blockSignals(old_state)

    def _sheet_name_selected(self, index: int) -> None:
        """
        Handle sheet name selection from the combobox and update the range input.

        Args:
            index (int): Index of the selected sheet in the combobox.
        """
        if 0 <= index < len(self.sheet_properties_list) and self.selected_spreadsheet:
            selected_sheet_props = self.sheet_properties_list[index]

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
        Validate the sheet range input using SheetRangeValidator.

        Args:
            text (str): The range string to validate.
        """
        from ripper.rippergui.sheet_utils import SheetRangeValidator

        if not SheetRangeValidator.is_range_empty(text):
            self.show_error("Sheet range cannot be empty.")
            self.select_button.setEnabled(False)
            return

        if not SheetRangeValidator.is_range_format_valid(text):
            self.show_error(f"Invalid range format. Expected 'A1:B5', found {text}.")
            self.select_button.setEnabled(False)
            return

        # Get sheet dimensions for bounds check
        sheet_row_count = 0
        sheet_col_count = 0
        if self.selected_spreadsheet and len(self.sheet_properties_list) > 0:
            current_sheet_name = self.sheet_name_combobox.currentText().strip()
            for sheet_props in self.sheet_properties_list:
                if sheet_props.title == current_sheet_name:
                    sheet_row_count = sheet_props.grid.row_count
                    sheet_col_count = sheet_props.grid.column_count
                    break

        # Only perform bounds check if dimensions are available
        if sheet_row_count > 0 and sheet_col_count > 0:
            if not SheetRangeValidator.is_range_within_bounds(text, sheet_row_count, sheet_col_count):
                self.show_error(
                    f"Range ({text}) outside dimensions (A1:{col_to_letter(sheet_col_count)}{sheet_row_count})."
                )
                self.select_button.setEnabled(False)
                return
            # If bounds are valid, proceed to enable button
            self.details_content.setText(self.details_text)  # Restore original details text
            self.select_button.setEnabled(True)
        else:
            # If dimensions are not available, format is valid, but bounds can't be checked.

            self.details_content.setText("Warning: Cannot validate range bounds (sheet dimensions not available).")
            self.select_button.setEnabled(True)

    def print_spreadsheet_info(self) -> None:
        """
        Log details about the selected spreadsheet, sheet, and range.
        """
        if not self.selected_spreadsheet:
            logger.error("No selected spreadsheet")
            return
        spreadsheet_name = self.selected_spreadsheet.name
        spreadsheet_id = self.selected_spreadsheet.id
        sheet_name = self.sheet_name_combobox.currentText().strip()
        sheet_range = self.sheet_range_input.text().strip()

        logger.info("Selected Google Sheet Information:")
        logger.info(f"Spreadsheet Name: {spreadsheet_name}")
        logger.info(f"Spreadsheet ID: {spreadsheet_id}")
        logger.info(f"Sheet Name: {sheet_name}")
        logger.info(f"Sheet Range: {sheet_range}")

    def user_confirmed_sheet(self) -> None:
        if not self.selected_spreadsheet:
            return

        try:
            spreadsheet_name = self.selected_spreadsheet.name
            spreadsheet_id = self.selected_spreadsheet.id
        except KeyError as e:
            logger.error(f"Missing required data key in selected sheet: {e}")
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

        self.print_spreadsheet_info()

        self.sheet_selected.emit(sheet_info)

    def show_error(self, message: str) -> None:
        """
        Display error message in the dialog.

        Args:
            message (str): The error message to display.
        """
        # Append the error message below the existing text
        current_text = self.details_text
        if not current_text.endswith("<br>"):
            # Add a line break if the current text doesn't end with one
            current_text += "<br>"
        self.details_content.setText(f"{current_text}<br><br><br><span style='color: red;'>{message}</span>")
        logger.error(message)
        logger.error(message)
