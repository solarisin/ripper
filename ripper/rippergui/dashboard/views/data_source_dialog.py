"""Data source configuration dialog."""

from __future__ import annotations

import uuid
from datetime import date, datetime
from typing import Dict, Optional, cast

from PySide6.QtCore import QDate, Qt, Signal
from PySide6.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QDateEdit,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QMessageBox,
    QVBoxLayout,
    QWidget,
)

from ripper.rippergui.dashboard.models import (
    DataSource,
    DataSourceType,
    DateRange,
    DateRangePreset,
)

# Type aliases
QItemSelectionMode = QAbstractItemView.SelectionMode
QDialogButtonStandardButton = QDialogButtonBox.StandardButton
QDateEditDate = QDate
QDialogDialogCode = QDialog.DialogCode


class DataSourceDialog(QDialog):
    """Dialog for creating or editing a data source."""

    # Signal emitted when a data source is saved
    data_source_saved = Signal(DataSource)

    def __init__(
        self,
        data_source: Optional[DataSource] = None,
        available_sheets: Optional[Dict[str, str]] = None,
        parent: Optional[QWidget] = None,
    ):
        """Initialize the dialog.

        Args:
            data_source: Existing data source to edit, or None to create a new one
            available_sheets: Dictionary of available spreadsheet IDs and names
            parent: Parent widget
        """
        super().__init__(parent)
        self.data_source = data_source
        self.available_sheets = available_sheets or {}

        self._init_ui()
        self._load_data()

    def _init_ui(self) -> None:
        """Initialize the user interface."""
        self.setWindowTitle("Data Source")
        self.setMinimumWidth(500)

        # Main layout
        layout = QVBoxLayout()
        self.setLayout(layout)

        # Form layout for basic properties
        form_layout = QFormLayout()
        layout.addLayout(form_layout)

        # Name
        self.name_edit = QLineEdit()
        form_layout.addRow("Name:", self.name_edit)

        # Data source type
        self.type_combo = QComboBox()
        for source_type in DataSourceType:
            self.type_combo.addItem(source_type.name.replace("_", " ").title(), source_type)
        self.type_combo.currentIndexChanged.connect(self._on_type_changed)
        form_layout.addRow("Type:", self.type_combo)

        # Spreadsheet selection
        self.sheet_combo = QComboBox()
        self.sheet_combo.addItem("Select a spreadsheet...", None)
        for sheet_id, sheet_name in self.available_sheets.items():
            self.sheet_combo.addItem(sheet_name, sheet_id)
        form_layout.addRow("Spreadsheet:", self.sheet_combo)

        # Date range group
        date_group = QGroupBox("Date Range")
        date_layout = QVBoxLayout()
        date_group.setLayout(date_layout)

        # Preset selection
        self.preset_combo = QComboBox()
        for preset in DateRangePreset:
            self.preset_combo.addItem(preset.name.replace("_", " ").title(), preset)
        self.preset_combo.currentIndexChanged.connect(self._on_preset_changed)
        date_layout.addWidget(self.preset_combo)

        # Custom date range
        self.custom_range_group = QGroupBox("Custom Range")
        self.custom_range_group.setCheckable(True)
        self.custom_range_group.setChecked(False)
        self.custom_range_group.toggled.connect(self._on_custom_range_toggled)

        custom_layout = QHBoxLayout()
        self.custom_range_group.setLayout(custom_layout)

        self.start_date_edit = QDateEdit()
        self.start_date_edit.setCalendarPopup(True)
        self.start_date_edit.setDate(QDate.currentDate().addMonths(-1))
        custom_layout.addWidget(QLabel("From:"))
        custom_layout.addWidget(self.start_date_edit)

        self.end_date_edit = QDateEdit()
        self.end_date_edit.setCalendarPopup(True)
        self.end_date_edit.setDate(QDate.currentDate())
        custom_layout.addWidget(QLabel("To:"))
        custom_layout.addWidget(self.end_date_edit)

        date_layout.addWidget(self.custom_range_group)

        # Filters group
        filters_group = QGroupBox("Filters")
        filters_layout = QVBoxLayout()
        filters_group.setLayout(filters_layout)

        # Set up accounts list
        self.accounts_list = QListWidget()
        self.accounts_list.setSelectionMode(QItemSelectionMode.MultiSelection)
        self.accounts_list.setMinimumHeight(100)
        filters_layout.addWidget(QLabel("Accounts:"))
        filters_layout.addWidget(self.accounts_list)

        # Set up categories list
        self.categories_list = QListWidget()
        self.categories_list.setSelectionMode(QItemSelectionMode.MultiSelection)
        self.categories_list.setMinimumHeight(100)
        filters_layout.addWidget(QLabel("Categories:"))
        filters_layout.addWidget(self.categories_list)

        # Add groups to main layout
        layout.addWidget(date_group)
        layout.addWidget(filters_group)

        # Buttons
        self.button_box = QDialogButtonBox(QDialogButtonStandardButton.Ok | QDialogButtonStandardButton.Cancel)
        self.button_box.accepted.connect(self._on_accept)
        self.button_box.rejected.connect(self.reject)
        layout.addWidget(self.button_box)

        # Update UI based on initial state
        self._update_ui()

    def _load_data(self) -> None:
        """Load data into the form."""
        if self.data_source:
            # Set basic properties
            self.name_edit.setText(self.data_source.name)

            # Set type
            type_index = self.type_combo.findData(self.data_source.type)
            if type_index >= 0:
                self.type_combo.setCurrentIndex(type_index)

            # Set spreadsheet
            sheet_index = self.sheet_combo.findData(self.data_source.spreadsheet_id)
            if sheet_index >= 0:
                self.sheet_combo.setCurrentIndex(sheet_index)

            # Set date range
            date_range = self.data_source.date_range
            preset_index = self.preset_combo.findData(date_range.preset)
            if preset_index >= 0:
                self.preset_combo.setCurrentIndex(preset_index)

            if self.data_source.date_range.start_date:
                qdate = QDate(
                    self.data_source.date_range.start_date.year,
                    self.data_source.date_range.start_date.month,
                    self.data_source.date_range.start_date.day,
                )
                self.start_date_edit.setDate(qdate)
            if self.data_source.date_range.end_date:
                qdate = QDate(
                    self.data_source.date_range.end_date.year,
                    self.data_source.date_range.end_date.month,
                    self.data_source.date_range.end_date.day,
                )
                self.end_date_edit.setDate(qdate)

            # Set filters
            # Note: In a real app, you would load accounts and categories from the selected spreadsheet
            pass

    def _update_ui(self) -> None:
        """Update the UI based on the current state."""
        # Enable/disable filters based on data source type
        source_type = self.type_combo.currentData()
        show_filters = source_type == DataSourceType.TILLER_TRANSACTIONS

        # In a real app, you would enable/disable the appropriate filter widgets here
        self.accounts_list.setEnabled(show_filters)
        self.categories_list.setEnabled(show_filters)

        # Enable date edits only when the CUSTOM preset is active.
        preset = self.preset_combo.currentData()
        is_custom = preset == DateRangePreset.CUSTOM
        self.start_date_edit.setEnabled(is_custom)
        self.end_date_edit.setEnabled(is_custom)

    def _on_type_changed(self, index: int) -> None:
        """Handle data source type change."""
        self._update_ui()

    def _on_preset_changed(self, index: int) -> None:
        """Handle date range preset change."""
        preset = self.preset_combo.currentData()
        is_custom = preset == DateRangePreset.CUSTOM
        self.custom_range_group.setChecked(is_custom)
        # Enable the date edits only for CUSTOM; disable them for all computed presets
        # so that stale values cannot accidentally be read and persisted.
        self.start_date_edit.setEnabled(is_custom)
        self.end_date_edit.setEnabled(is_custom)

    def _on_custom_range_toggled(self, checked: bool) -> None:
        """Handle custom range toggle."""
        if checked:
            self.preset_combo.setCurrentText(DateRangePreset.CUSTOM.name.replace("_", " ").title())

    def _on_accept(self) -> None:
        """Handle OK button click."""
        # Validate input
        name = self.name_edit.text().strip()
        if not name:
            QMessageBox.warning(self, "Validation Error", "Please enter a name for the data source.")
            return

        sheet_id = self.sheet_combo.currentData()
        if not sheet_id:
            QMessageBox.warning(self, "Validation Error", "Please select a spreadsheet.")
            return

        # Get date range
        preset = self.preset_combo.currentData()

        # Only capture explicit dates when the preset is CUSTOM; for all other
        # presets the dates are computed at runtime by DateRange.get_date_range()
        # so we must not persist stale custom values.
        start_date = None
        end_date = None
        if preset == DateRangePreset.CUSTOM:
            qdate = cast(date, self.start_date_edit.date().toPython())
            start_date = datetime.combine(qdate, datetime.min.time())
            qdate = cast(date, self.end_date_edit.date().toPython())
            end_date = datetime.combine(qdate, datetime.max.time())

        # Validate that the custom range is ordered correctly.
        if start_date is not None and end_date is not None and start_date > end_date:
            QMessageBox.warning(
                self,
                "Validation Error",
                "Start date must be on or before the end date.",
            )
            return

        # Create or update data source
        if not self.data_source:
            self.data_source = DataSource(
                id=str(uuid.uuid4()),
                type=self.type_combo.currentData(),
                name=name,
                spreadsheet_id=sheet_id,
                sheet_name="Transactions",
                range_a1="A1:Z1000",
                date_range=DateRange(preset=preset, start_date=start_date, end_date=end_date),
                filters={},
            )
        else:
            self.data_source.name = name
            self.data_source.type = self.type_combo.currentData()
            self.data_source.spreadsheet_id = sheet_id
            if not self.data_source.sheet_name:
                self.data_source.sheet_name = "Transactions"
            if not self.data_source.range_a1:
                self.data_source.range_a1 = "A1:Z1000"
            self.data_source.date_range = DateRange(preset=preset, start_date=start_date, end_date=end_date)

        # Get selected accounts and categories
        if self.data_source.type == DataSourceType.TILLER_TRANSACTIONS:
            selected_accounts = [
                self.accounts_list.item(i).data(int(Qt.ItemDataRole.UserRole))
                for i in range(self.accounts_list.count())
                if self.accounts_list.item(i).isSelected()
            ]
            selected_categories = [
                self.categories_list.item(i).data(int(Qt.ItemDataRole.UserRole))
                for i in range(self.categories_list.count())
                if self.categories_list.item(i).isSelected()
            ]

            self.data_source.filters = {"accounts": selected_accounts, "categories": selected_categories}

        self.accept()
        self.data_source_saved.emit(self.data_source)

    @classmethod
    def get_data_source(
        cls,
        data_source: Optional[DataSource] = None,
        available_sheets: Optional[Dict[str, str]] = None,
        parent: Optional[QWidget] = None,
    ) -> Optional[DataSource]:
        """Show the dialog and return the created/edited data source.

        Args:
            data_source: Existing data source to edit, or None to create a new one
            available_sheets: Dictionary of available spreadsheet IDs and names
            parent: Parent widget

        Returns:
            The created/edited data source, or None if cancelled
        """
        dialog = cls(data_source, available_sheets, parent)
        if dialog.exec() == int(QDialogDialogCode.Accepted):
            return dialog.data_source
        return None
