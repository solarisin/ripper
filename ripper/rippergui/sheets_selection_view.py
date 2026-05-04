"""
Dialog for creating and configuring a named data source from a Google Sheet range.

This module provides SheetsSelectionDialog, a Qt dialog for browsing, selecting, and validating Google Sheets
and their ranges. It includes input validation, error feedback, and emits a signal when a sheet and range are
selected. Network calls are performed on background threads to keep the UI responsive.
"""

import traceback

from beartype.typing import Optional
from loguru import logger
from PySide6.QtCore import QSize, Qt, QThread, Signal
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QFormLayout,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QProgressDialog,
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


class _SpreadsheetLoader(QThread):
    """
    Background worker that fetches the list of Google Spreadsheets from Drive.

    Signals:
        finished (list): Emitted with the retrieved spreadsheet list on success.
        error (str): Emitted with an error message on failure.
    """

    finished: Signal = Signal(list)  # type: ignore[misc]
    error: Signal = Signal(str)

    def run(self) -> None:  # noqa: D102
        """Fetch spreadsheets in the background."""
        try:
            drive_service = AuthManager().create_drive_service()
            if not drive_service:
                self.error.emit("Not authenticated. Please authenticate with Google first.")
                return
            spreadsheets = sheets_backend.retrieve_spreadsheets(drive_service)
            self.finished.emit(spreadsheets)
        except Exception as e:  # pragma: no cover
            logger.error(f"Error loading spreadsheets: {e}, {traceback.format_exc()}")
            self.error.emit(str(e))


class _SheetMetadataLoader(QThread):
    """
    Background worker that fetches the sheet-tab metadata for a single spreadsheet.

    Signals:
        finished (list): Emitted with the list of SheetProperties on success.
        error (str): Emitted with an error message on failure.
    """

    finished: Signal = Signal(list)  # type: ignore[misc]
    error: Signal = Signal(str)

    def __init__(self, spreadsheet_id: str, parent: Optional[QWidget] = None) -> None:
        """Initialise with the target spreadsheet ID."""
        super().__init__(parent)
        self._spreadsheet_id = spreadsheet_id

    def run(self) -> None:  # noqa: D102
        """Fetch sheet metadata in the background."""
        try:
            sheets_service = AuthManager().create_sheets_service()
            if not sheets_service:
                self.error.emit("Could not create Sheets service.")
                return
            sheet_props = sheets_backend.retrieve_sheets_of_spreadsheet(sheets_service, self._spreadsheet_id)
            self.finished.emit(sheet_props)
        except Exception as e:  # pragma: no cover
            logger.error(f"Error loading sheet metadata: {e}, {traceback.format_exc()}")
            self.error.emit(str(e))


class SheetsSelectionDialog(QDialog):
    """
    Dialog for creating a named data source from a Google Sheet range.

    The dialog lets the user browse their Google Drive for spreadsheets, select one,
    choose a sheet tab and range, and give the resulting data source a human-readable
    name.  Network I/O (spreadsheet list, sheet metadata) is performed on background
    threads so the main UI stays responsive.

    Signals:
        sheet_selected (dict): Emitted when the user confirms the selection.  Dict keys:
            ``spreadsheet_name``, ``spreadsheet_id``, ``sheet_name``, ``sheet_range``,
            ``data_source_name``.
    """

    # Signal emitted when the user saves a data source
    sheet_selected = Signal(dict)

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        """
        Initialize the data source creation dialog.

        Args:
            parent: Parent widget.
        """
        super().__init__(parent)
        self.setWindowTitle("Create Data Source")
        self.setMinimumWidth(600)
        self.setMinimumHeight(400)
        self.resize(1600, 900)

        self.selected_spreadsheet: SpreadsheetProperties | None = None
        self.sheet_properties_list: list[SheetProperties] = []
        self._loader: Optional[_SpreadsheetLoader] = None
        self._sheet_loader: Optional[_SheetMetadataLoader] = None

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

        # Sheet name, range, and data source name fields
        options_layout = QFormLayout()

        # Data source name (the human-readable label the user gives this source)
        self.data_source_name_input = QLineEdit()
        self.data_source_name_input.setPlaceholderText("e.g. Tiller Transactions 2024")
        options_layout.addRow("Data Source Name:", self.data_source_name_input)

        # Sheet name combobox
        self.sheet_name_combobox = QComboBox()
        options_layout.addRow("Sheet Name:", self.sheet_name_combobox)

        # Sheet range input
        self.sheet_range_input = QLineEdit()
        options_layout.addRow("Sheet Range:", self.sheet_range_input)
        self.sheet_range_input.textChanged.connect(lambda text: self._validate_sheet_range(text) if text else None)

        # Wire name auto-population: update when sheet tab selection changes
        self.sheet_name_combobox.currentTextChanged.connect(self._auto_populate_name)
        # Connect sheet-name selection once here so callbacks never create duplicates
        self.sheet_name_combobox.currentIndexChanged.connect(lambda idx: self._sheet_name_selected(idx))

        details_layout.addLayout(options_layout)

        # Add widgets to splitter
        splitter.addWidget(thumbnails_widget)
        splitter.addWidget(details_widget)
        splitter.setSizes([650, 250])  # Give more space to thumbnails grid to show all 3 columns

        main_layout.addWidget(splitter)

        # Buttons
        buttons_layout = QHBoxLayout()

        self.select_button = QPushButton("Save Data Source")
        self.select_button.setEnabled(False)
        self.select_button.clicked.connect(self.user_confirmed_sheet)

        close_button = QPushButton("Close")
        close_button.clicked.connect(self.reject)

        buttons_layout.addWidget(self.select_button)
        buttons_layout.addWidget(close_button)

        main_layout.addLayout(buttons_layout)

        # Load spreadsheets on a background thread
        self.load_spreadsheets()

    def load_spreadsheets(self) -> None:
        """
        Kick off a background fetch of Google Spreadsheets from Drive.

        Results are delivered via :py:meth:`_on_spreadsheets_loaded`.  An
        indeterminate progress dialog is shown while the fetch is in flight.
        Any previously-running loader is stopped before starting a new one.
        """
        # Disconnect any in-flight loader so its results are silently discarded;
        # don't quit()/wait() — that would block the UI while the network call runs.
        if self._loader is not None and self._loader.isRunning():
            self._loader.finished.disconnect()
            self._loader.error.disconnect()

        self._progress = QProgressDialog("Loading spreadsheets…", "", 0, 0, self)
        self._progress.setWindowModality(Qt.WindowModality.WindowModal)
        self._progress.setMinimumDuration(300)
        self._progress.setValue(0)

        self._loader = _SpreadsheetLoader(self)
        self._loader.finished.connect(self._on_spreadsheets_loaded)
        self._loader.error.connect(self._on_load_error)
        self._loader.finished.connect(self._progress.reset)
        self._loader.error.connect(self._progress.reset)
        self._loader.finished.connect(self._loader.deleteLater)
        self._loader.start()

    def _on_spreadsheets_loaded(self, spreadsheets: list) -> None:
        """
        Receive the spreadsheet list from the background loader and populate the grid.

        Args:
            spreadsheets: List of SpreadsheetProperties returned by the loader.
        """
        self.spreadsheets_list = spreadsheets
        self.display_spreadsheets()

    def _on_load_error(self, message: str) -> None:
        """
        Show a load error in the details panel.

        Args:
            message: Human-readable error description.
        """
        logger.error(f"Spreadsheet load error: {message}")
        self.show_error(f"Error loading sheets: {message}")

    def display_spreadsheets(self) -> None:
        """
        Display spreadsheets in the grid layout.

        Clears any existing widgets in the grid and adds thumbnails for each spreadsheet.
        If no spreadsheets are found, displays a message.
        """
        # Clear existing items
        while self.grid_layout.count():
            item = self.grid_layout.takeAt(0)
            if item is not None:
                widget = item.widget()
                if widget is not None:
                    widget.deleteLater()

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

        # Disconnect any in-flight metadata loader so its stale results are silently
        # discarded.  Don't quit()/wait() — that would block the UI during a slow
        # network call.  Stale results are also guarded by the loaded_for_id check.
        if self._sheet_loader is not None and self._sheet_loader.isRunning():
            self._sheet_loader.finished.disconnect()
            self._sheet_loader.error.disconnect()

        # Fetch sheet metadata on a background thread
        self._sheet_progress = QProgressDialog("Loading sheet details…", "", 0, 0, self)
        self._sheet_progress.setWindowModality(Qt.WindowModality.WindowModal)
        self._sheet_progress.setMinimumDuration(300)
        self._sheet_progress.setValue(0)

        # Capture the ID so stale results can be discarded in the callback
        loading_for_id = spreadsheet_properties.id
        self._sheet_loader = _SheetMetadataLoader(loading_for_id, self)
        self._sheet_loader.finished.connect(
            lambda props, _id=loading_for_id: self._on_sheet_metadata_loaded(props, _id)
        )
        self._sheet_loader.error.connect(self._on_sheet_metadata_error)
        self._sheet_loader.finished.connect(self._sheet_progress.reset)
        self._sheet_loader.error.connect(self._sheet_progress.reset)
        self._sheet_loader.finished.connect(self._sheet_loader.deleteLater)
        self._sheet_loader.start()

    def _on_sheet_metadata_loaded(self, sheet_props: list, loaded_for_id: str) -> None:
        """
        Populate the sheet combobox after background metadata fetch completes.

        Discards results if the user has already selected a different spreadsheet
        since the load was kicked off.

        Args:
            sheet_props: List of SheetProperties for the selected spreadsheet.
            loaded_for_id: The spreadsheet id that was being fetched.
        """
        # Discard stale results if the user selected a different spreadsheet
        if self.selected_spreadsheet is None or self.selected_spreadsheet.id != loaded_for_id:
            logger.debug(f"Discarding stale metadata for spreadsheet id '{loaded_for_id}'")
            return

        self.sheet_properties_list = sheet_props
        logger.debug(f"Spreadsheet contains {len(self.sheet_properties_list)} sheets")

        # Block signals while repopulating to avoid spurious callbacks
        old_state = self.sheet_name_combobox.blockSignals(True)
        self.sheet_name_combobox.clear()
        self.sheet_range_input.clear()

        if self.sheet_properties_list:
            sheet_names = [sheet.title for sheet in self.sheet_properties_list]
            self.sheet_name_combobox.addItems(sheet_names)
            # currentIndexChanged is already connected once in __init__; no reconnect here
            self.sheet_name_combobox.setCurrentIndex(0)
            self._sheet_name_selected(0)

        self.sheet_name_combobox.blockSignals(old_state)

    def _on_sheet_metadata_error(self, message: str) -> None:
        """
        Show a sheet metadata load error in the details panel.

        Args:
            message: Human-readable error description.
        """
        logger.error(f"Sheet metadata load error: {message}")
        self.show_error(f"Error loading sheet details: {message}")

    def _sheet_name_selected(self, index: int) -> None:
        """
        Handle sheet name selection from the combobox and update the range input.

        Args:
            index: Index of the selected sheet in the combobox.
        """
        if 0 <= index < len(self.sheet_properties_list) and self.selected_spreadsheet:
            selected_sheet_props = self.sheet_properties_list[index]

            row_count = selected_sheet_props.grid.row_count
            col_count = selected_sheet_props.grid.column_count
            end_column_letter = col_to_letter(col_count)

            sheet_range = f"A1:{end_column_letter}{row_count}"
            self.sheet_range_input.setText(sheet_range)
            self._current_full_range = sheet_range
            self._validate_sheet_range(sheet_range)
        else:
            self.sheet_range_input.clear()
            self.select_button.setEnabled(False)
            return

    def _auto_populate_name(self, sheet_tab_name: str) -> None:
        """
        Auto-populate the data source name field when the sheet selection changes.

        Only updates the field when it is empty or still contains a previously
        auto-generated value so that a user-typed name is never overwritten.

        Args:
            sheet_tab_name: The newly selected sheet tab name.
        """
        if not self.selected_spreadsheet or not sheet_tab_name:
            return

        proposed = f"{self.selected_spreadsheet.name} – {sheet_tab_name}"

        current = self.data_source_name_input.text()
        # Overwrite only if the field is empty or already an auto-generated value
        if not current or current.startswith(self.selected_spreadsheet.name):
            self.data_source_name_input.setText(proposed)

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

        data_source_name = self.data_source_name_input.text().strip()
        if not data_source_name:
            # Fall back to an auto-generated name if the user left the field blank
            data_source_name = f"{spreadsheet_name} – {sheet_name}"
            self.data_source_name_input.setText(data_source_name)

        sheet_info = {
            "spreadsheet_name": spreadsheet_name,
            "spreadsheet_id": spreadsheet_id,
            "sheet_name": sheet_name,
            "sheet_range": sheet_range,
            "data_source_name": data_source_name,
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
