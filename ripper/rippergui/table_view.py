import logging
import re
from datetime import datetime
from decimal import Decimal, InvalidOperation

from beartype.typing import Any, Dict, List, Optional, Set, cast
from PySide6.QtCore import (
    QAbstractTableModel,
    QDate,
    QModelIndex,
    QObject,
    QPersistentModelIndex,
    QRegularExpression,
    QSortFilterProxyModel,
    Qt,
    Signal,
    Slot,
)
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QDoubleSpinBox,
    QGridLayout,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QPushButton,
    QTableView,
    QVBoxLayout,
    QWidget,
)

log = logging.getLogger("ripper:table_view")
# --- Helper functions for parsing numbers and dates ---
"""
Helper functions for parsing numbers and dates for TransactionModel and sorting.
"""


def parse_number(val: object) -> Optional[float]:
    if isinstance(val, (int, float)):
        return float(val)
    if val is None:
        return None
    s = str(val).replace(",", "").replace("(", "-").replace(")", "")
    s = s.strip()
    s = re.sub(r"[^0-9.\-]", "", s)
    s = re.sub(r"(?<!^)-", "", s)
    try:
        return float(s)
    except Exception:
        return None


def is_number(val: object) -> bool:
    return parse_number(val) is not None


def parse_date(val: object) -> Optional[QDate]:
    if val is None:
        return None
    if isinstance(val, QDate):
        return val if val.isValid() else None
    s = str(val).strip()
    d = QDate.fromString(s, "yyyy-MM-dd")
    if d.isValid():
        return d
    try:
        dt = datetime.strptime(s, "%m/%d/%Y")
        return QDate(dt.year, dt.month, dt.day)
    except Exception:
        pass
    try:
        dt = datetime.strptime(s, "%d/%m/%Y")
        return QDate(dt.year, dt.month, dt.day)
    except Exception:
        pass
    return None


def is_date(val: object) -> bool:
    return parse_date(val) is not None


class TransactionModel(QAbstractTableModel):
    _col_type_cache: Dict[int, str]

    def infer_column_type(self, col: int, sample_size: int = 20) -> str:
        """
        Infer the type of data in a column: 'number', 'date', or 'string'.
        Caches the result for efficiency.
        """
        if not hasattr(self, "_col_type_cache"):
            self._col_type_cache = {}
        if col in self._col_type_cache:
            return self._col_type_cache[col]

        num_count = 0
        date_count = 0
        str_count = 0
        checked = 0
        for row in range(len(self._data)):
            val = self.get_raw_value(row, col)
            if val is None or (isinstance(val, str) and not val.strip()):
                continue
            checked += 1
            if is_date(val):
                date_count += 1
            elif is_number(val):
                num_count += 1
            else:
                str_count += 1
            if checked >= sample_size:
                break
        if num_count >= max(date_count, str_count):
            typ = "number"
        elif date_count >= max(num_count, str_count):
            typ = "date"
        else:
            typ = "string"
        self._col_type_cache[col] = typ
        return typ

    def clear_type_cache(self) -> None:
        if hasattr(self, "_col_type_cache"):
            self._col_type_cache.clear()

    """
    Model for displaying transaction data in a table view.

    This model handles the display and sorting of transaction data, with support
    for different data types (dates, decimal amounts, text) and alignment.
    """

    def __init__(self, data: Optional[List[Dict[str, Any]]] = None) -> None:
        """
        Initialize the transaction model.

        Args:
            data: List of dictionaries containing transaction data
        """
        super().__init__()
        self._data: List[Dict[str, Any]] = data if data is not None else []
        self._headers: List[str] = ["ID", "Date", "Description", "Category", "Amount", "Account"]

    def get_raw_value(self, row: int, col: int) -> Any:
        """
        Return the raw value for a given row and column (for sorting).
        """
        if 0 <= row < len(self._data) and 0 <= col < len(self._headers):
            header = self._headers[col]
            return self._data[row].get(header)
        return None

    def rowCount(self, parent: QModelIndex | QPersistentModelIndex = QModelIndex()) -> int:
        """
        Return the number of rows in the model.
        This method is called by Qt to determine the number of rows to display in the view.

        Args:
            parent: Parent index (unused for list models)

        Returns:
            Number of rows (transactions)
        """
        if parent.isValid():
            return 0
        return len(self._data)

    def columnCount(self, parent: QModelIndex | QPersistentModelIndex = QModelIndex()) -> int:
        """
        Return the number of columns in the model.
        This method is called by Qt to determine the number of columns to display in the view.

        Args:
            parent: Parent index (unused for list models)

        Returns:
            Number of columns
        """
        if parent.isValid():
            return 0
        return len(self._headers)

    def data(self, index: QModelIndex | QPersistentModelIndex, role: int = Qt.ItemDataRole.DisplayRole) -> Any:
        """
        Return the data for a given index and role.
        This method is called by Qt to retrieve the data to display or edit in the view.

        Args:
            index: The model index for which data is requested
            role: The role for which data is requested (display, edit, alignment, etc.)

        Returns:
            The data to be displayed or used by the view
        """
        if not index.isValid():
            return None
        row = index.row()
        col = index.column()
        if role == Qt.ItemDataRole.DisplayRole:
            return self._get_display_data(row, col)
        elif role == Qt.ItemDataRole.TextAlignmentRole:
            return self._get_alignment(col, row)
        elif role == Qt.ItemDataRole.EditRole:
            if 0 <= row < len(self._data) and 0 <= col < len(self._headers):
                header = self._headers[col]
                return self._data[row].get(header)
            return None
        return None

    def _get_display_data(self, row: int, col: int) -> Any:
        if 0 <= row < len(self._data) and 0 <= col < len(self._headers):
            header = self._headers[col]
            value = self._data[row].get(header)
            if isinstance(value, QDate):
                return value.toString("yyyy-MM-dd")
            if isinstance(value, (float, Decimal)):
                return self._format_decimal(value)
            return str(value)
        return None

    def _format_decimal(self, value: float | Decimal) -> str:
        try:
            return f"{Decimal(value):.2f}"
        except Exception:
            return str(value)

    def _get_alignment(self, col: int, row: int) -> int:
        if 0 <= col < len(self._headers):
            header = self._headers[col]
            value = self._data[row].get(header)
            if isinstance(value, (int, float, Decimal)):
                return Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
        return Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter

    def headerData(self, section: int, orientation: Qt.Orientation, role: int = Qt.ItemDataRole.DisplayRole) -> Any:
        """
        Return header data for the given section, orientation and role.
        This method is called by Qt to retrieve the header labels for the table.

        Args:
            section: Column or row number
            orientation: Horizontal or vertical header
            role: Data role

        Returns:
            Header data, or None if not available
        """
        if role == Qt.ItemDataRole.DisplayRole and orientation == Qt.Orientation.Horizontal:
            if 0 <= section < len(self._headers):
                return self._headers[section]
        return None

    def sort(self, column: int, order: Qt.SortOrder = Qt.SortOrder.AscendingOrder) -> None:
        """
        Sort the model by the given column and order.
        This method is called by Qt when the user clicks a column header to sort the table.

        Args:
            column: Column index to sort by
            order: Sort order (ascending or descending)
        """
        self.layoutAboutToBeChanged.emit()
        col_name = self._headers[column]
        try:
            if col_name == "Amount":
                self._data.sort(
                    key=lambda x: Decimal(str(x.get(col_name, 0))), reverse=(order == Qt.SortOrder.DescendingOrder)
                )
            elif col_name == "Date":
                self._data.sort(key=lambda x: x.get(col_name, QDate()), reverse=(order == Qt.SortOrder.DescendingOrder))
            else:
                self._data.sort(
                    key=lambda x: str(x.get(col_name, "")).lower(), reverse=(order == Qt.SortOrder.DescendingOrder)
                )
        except Exception as e:
            log.error(f"Error sorting by {col_name}: {e}")
        self.layoutChanged.emit()


class TransactionSortFilterProxyModel(QSortFilterProxyModel):
    """
    Custom sort/filter proxy model for transaction data.

    This model provides advanced filtering capabilities for transaction data,
    including text search, range filtering for amounts, and exact matching for accounts.
    """

    def __init__(self, parent: Optional[QObject] = None) -> None:
        """
        Initialize the proxy model.

        Args:
            parent: Parent object
        """
        super().__init__(parent)
        self._filters: Dict[int, Dict[str, Any]] = {}

    def set_filter_value(self, column_index: int, value: Any, header_name: Optional[str] = None) -> None:
        """
        Set a filter value for a specific column.

        Args:
            column_index: Index of the column to filter
            value: Filter value (string, regex, or tuple for range filters)
            header_name: Name of the column header (for type-specific filtering)
        """
        if value is not None and value != "" and value != (None, None):  # Check for meaningful filter
            self._filters[column_index] = {"value": value, "header": header_name}
        elif column_index in self._filters:
            del self._filters[column_index]
        self.invalidateFilter()

    def get_active_filters(self) -> Dict[int, Dict[str, Any]]:
        """
        Get the currently active filters.

        Returns:
            Dictionary mapping column indices to filter information
        """
        return self._filters

    def clear_all_filters(self) -> bool:
        """
        Clear all active filters.

        Returns:
            True if filters were cleared, False if there were no filters
        """
        if not self._filters:
            return False  # No filters to clear
        self._filters.clear()
        self.invalidateFilter()
        return True  # Filters were cleared

    def filterAcceptsRow(self, source_row: int, source_parent: QModelIndex | QPersistentModelIndex) -> bool:
        """
        Determine whether the given row in the source model should be included in the filtered model.
        This method is called by Qt's filtering mechanism for each row.

        Args:
            source_row: Row index in the source model
            source_parent: Parent index in the source model

        Returns:
            True if the row should be included, False otherwise
        """
        if not self._filters:
            return True

        source_model = self.sourceModel()
        if not hasattr(source_model, "_headers"):
            return False
        # Cast to QAbstractTableModel for type checking
        source_model_table = cast(QAbstractTableModel, source_model)
        for column_index, filter_info in self._filters.items():
            filter_value = filter_info["value"]
            header_name = filter_info["header"]  # Get header name from stored info
            if not self._check_row_against_filter(
                source_model_table, source_row, column_index, filter_value, header_name
            ):
                return False
        return True

    def _check_row_against_filter(
        self, model: QAbstractTableModel, source_row: int, column_index: int, filter_value: Any, header_name: str
    ) -> bool:
        """
        Check if a specific cell matches the filter criteria.

        Args:
            model: Source model
            source_row: Row index in the source model
            column_index: Column index in the source model
            filter_value: Filter value to check against
            header_name: Name of the column header

        Returns:
            True if the cell matches the filter, False otherwise
        """
        idx = model.index(source_row, column_index, QModelIndex())
        if not idx.isValid():
            return False

        data_to_check = model.data(idx, Qt.ItemDataRole.DisplayRole)

        if header_name in ["Description", "Category", "ID"]:
            if isinstance(filter_value, QRegularExpression):
                return filter_value.match(str(data_to_check)).hasMatch()
            return str(filter_value).lower() in str(data_to_check).lower()
        elif header_name == "Account":  # Account is usually an exact match from ComboBox
            return str(filter_value) == str(data_to_check)
        elif header_name == "Amount":
            min_val, max_val = filter_value
            try:
                # Ensure data_to_check is cleaned (e.g. remove currency symbols if any from displayrole)
                # However, our display role already formats it as a plain number string.
                amount = Decimal(data_to_check)
                passes_min = min_val is None or amount >= min_val
                passes_max = max_val is None or amount <= max_val
                return passes_min and passes_max
            except (InvalidOperation, ValueError):
                return False
        return True

    def lessThan(self, left: QModelIndex | QPersistentModelIndex, right: QModelIndex | QPersistentModelIndex) -> bool:
        """
        Compare two items in the model for sorting purposes, inferring type by column content.
        """
        source_model = self.sourceModel()
        if not isinstance(source_model, TransactionModel):
            return super().lessThan(left, right)

        col = left.column()
        left_raw = source_model.get_raw_value(left.row(), col)
        right_raw = source_model.get_raw_value(right.row(), col)

        # Handle None values
        if left_raw is None and right_raw is not None:
            return True
        if left_raw is None or right_raw is None:
            return False

        col_type = source_model.infer_column_type(col)
        log.debug(
            "Comparing column %d (%s) of type '%s' between '%s' and '%s'",
            col,
            source_model.headerData(col, Qt.Orientation.Horizontal),
            col_type,
            left_raw,
            right_raw,
        )
        if col_type == "number":
            left_num = parse_number(left_raw)
            right_num = parse_number(right_raw)
            # None values are treated as less
            if left_num is None and right_num is not None:
                return True
            if left_num is None or right_num is None:
                return False
            return left_num < right_num
        if col_type == "date":
            ldate = parse_date(left_raw)
            rdate = parse_date(right_raw)
            if ldate is None and rdate is not None:
                return True
            if ldate is None or rdate is None:
                return False
            return ldate < rdate
        # Default: string comparison (case-insensitive)
        is_less: bool = str(left_raw).lower() < str(right_raw).lower()
        log.debug(
            "String comparison for column %d (%s): '%s' < '%s' = %s",
            col,
            source_model.headerData(col, Qt.Orientation.Horizontal),
            left_raw,
            right_raw,
            is_less,
        )
        return is_less


# --- Filter Dialog ---
class FilterDialog(QDialog):
    """
    Dialog for setting transaction filters.

    This dialog allows the user to set filters for transaction data,
    including text filters for description and category, account selection,
    and amount range filters.
    """

    # Signal emitted when filters are applied
    filters_applied = Signal(dict)

    def __init__(
        self,
        unique_accounts: Set[str],
        current_filters: Optional[Dict[int, Dict[str, Any]]] = None,
        parent: Optional[QWidget] = None,
    ):
        """
        Initialize the filter dialog.

        Args:
            unique_accounts: Set of unique account names to populate the account filter
            current_filters: Dictionary of currently active filters
            parent: Parent widget
        """
        super().__init__(parent)
        self.setWindowTitle("Set Transaction Filters")
        self.setMinimumWidth(400)

        self._unique_accounts: List[str] = ["All Accounts"] + sorted(list(unique_accounts))
        self._current_filters: Dict[int, Dict[str, Any]] = current_filters if current_filters else {}
        self._source_model_headers: List[str] = [
            "ID",
            "Date",
            "Description",
            "Category",
            "Amount",
            "Account",
        ]  # To map display names to column indices

        layout = QVBoxLayout(self)
        form_layout = QGridLayout()

        # Description Filter
        self.description_filter_input = QLineEdit()
        form_layout.addWidget(QLabel("Description contains:"), 0, 0)
        form_layout.addWidget(self.description_filter_input, 0, 1)

        # Category Filter
        self.category_filter_input = QLineEdit()
        form_layout.addWidget(QLabel("Category contains:"), 1, 0)
        form_layout.addWidget(self.category_filter_input, 1, 1)

        # Account Filter
        self.account_filter_combo = QComboBox()
        self.account_filter_combo.addItems(self._unique_accounts)
        form_layout.addWidget(QLabel("Account is:"), 2, 0)
        form_layout.addWidget(self.account_filter_combo, 2, 1)

        # Amount Filter
        self.amount_min_input = QDoubleSpinBox()
        self.amount_min_input.setRange(-1_000_000_000, 1_000_000_000)
        self.amount_min_input.setDecimals(2)
        self.amount_min_input.setPrefix("$ ")
        self.amount_min_input.setSpecialValueText("Min")
        self.amount_min_input.setValue(self.amount_min_input.minimum())

        self.amount_max_input = QDoubleSpinBox()
        self.amount_max_input.setRange(-1_000_000_000, 1_000_000_000)
        self.amount_max_input.setDecimals(2)
        self.amount_max_input.setPrefix("$ ")
        self.amount_max_input.setSpecialValueText("Max")
        self.amount_max_input.setValue(self.amount_max_input.maximum())

        amount_filter_layout = QHBoxLayout()
        amount_filter_layout.addWidget(self.amount_min_input)
        amount_filter_layout.addWidget(QLabel("to"))
        amount_filter_layout.addWidget(self.amount_max_input)
        form_layout.addWidget(QLabel("Amount range:"), 3, 0)
        form_layout.addLayout(amount_filter_layout, 3, 1)

        layout.addLayout(form_layout)

        # Buttons
        self.button_box = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Apply
            | QDialogButtonBox.StandardButton.Reset
            | QDialogButtonBox.StandardButton.Cancel
        )
        self.button_box.button(QDialogButtonBox.StandardButton.Apply).clicked.connect(self.apply_and_accept)
        self.button_box.button(QDialogButtonBox.StandardButton.Reset).clicked.connect(self.reset_fields)
        self.button_box.button(QDialogButtonBox.StandardButton.Cancel).clicked.connect(self.reject)
        layout.addWidget(self.button_box)

        self.populate_fields()  # Populate with current filters

    def populate_fields(self) -> None:
        """
        Populate dialog fields with current filters.

        Fills in the filter input fields with values from the currently active filters.
        """
        desc_filter = self._current_filters.get(self._source_model_headers.index("Description"))
        if desc_filter and isinstance(desc_filter["value"], QRegularExpression):
            self.description_filter_input.setText(desc_filter["value"].pattern())
        elif desc_filter:  # Should not happen if we always use regex
            self.description_filter_input.setText(str(desc_filter.get("value", "")))
        else:
            self.description_filter_input.clear()

        cat_filter = self._current_filters.get(self._source_model_headers.index("Category"))
        if cat_filter and isinstance(cat_filter["value"], QRegularExpression):
            self.category_filter_input.setText(cat_filter["value"].pattern())
        elif cat_filter:
            self.category_filter_input.setText(str(cat_filter.get("value", "")))
        else:
            self.category_filter_input.clear()

        acc_filter = self._current_filters.get(self._source_model_headers.index("Account"))
        if acc_filter and acc_filter.get("value") in self._unique_accounts:
            self.account_filter_combo.setCurrentText(acc_filter["value"])
        else:
            self.account_filter_combo.setCurrentText("All Accounts")

        amount_filter_info = self._current_filters.get(self._source_model_headers.index("Amount"))
        if amount_filter_info:
            min_val, max_val = amount_filter_info["value"]
            self.amount_min_input.setValue(float(min_val) if min_val is not None else self.amount_min_input.minimum())
            self.amount_max_input.setValue(float(max_val) if max_val is not None else self.amount_max_input.maximum())
        else:
            self.amount_min_input.setValue(self.amount_min_input.minimum())
            self.amount_max_input.setValue(self.amount_max_input.maximum())

    def reset_fields(self) -> None:
        """
        Reset dialog fields to their default/empty state.

        Clears all filter inputs and sets them back to their default values.
        """
        self.description_filter_input.clear()
        self.category_filter_input.clear()
        self.account_filter_combo.setCurrentText("All Accounts")
        self.amount_min_input.setValue(self.amount_min_input.minimum())
        self.amount_max_input.setValue(self.amount_max_input.maximum())

    def get_filters(self) -> Dict[str, Any]:
        """
        Collect filter values from the dialog's input fields.

        Returns:
            Dictionary mapping column names to filter values
        """
        filters: Dict[str, Any] = {}

        # Description
        desc_text = self.description_filter_input.text().strip()
        if desc_text:
            filters["Description"] = QRegularExpression(
                desc_text, QRegularExpression.PatternOption.CaseInsensitiveOption
            )

        # Category
        cat_text = self.category_filter_input.text().strip()
        if cat_text:
            filters["Category"] = QRegularExpression(cat_text, QRegularExpression.PatternOption.CaseInsensitiveOption)

        # Account
        acc_text = self.account_filter_combo.currentText()
        if acc_text != "All Accounts":
            filters["Account"] = acc_text

        # Amount
        min_val = self.amount_min_input.value()
        max_val = self.amount_max_input.value()
        actual_min = (
            None if self.amount_min_input.text() == self.amount_min_input.specialValueText() else Decimal(str(min_val))
        )
        actual_max = (
            None if self.amount_max_input.text() == self.amount_max_input.specialValueText() else Decimal(str(max_val))
        )

        if actual_min is not None or actual_max is not None:
            filters["Amount"] = (actual_min, actual_max)

        return filters

    def apply_and_accept(self) -> None:
        """
        Emit collected filters and accept the dialog.

        Collects filter values, emits the filters_applied signal, and closes the dialog.
        """
        self.filters_applied.emit(self.get_filters())
        self.accept()


class TransactionTableViewWidget(QWidget):
    """
    Widget for displaying and filtering transaction data in a table view.

    This widget provides a table view for transaction data with sorting and filtering
    capabilities, along with controls for managing filters.
    """

    def __init__(self, transactions_data: list[dict[str, Any]]):
        """
        Initialize the transaction table view widget.

        Args:
            transactions_data: List of dictionaries containing transaction data
        """
        super().__init__()
        self.setWindowTitle("Tiller Transaction Viewer")
        self.setGeometry(100, 100, 1000, 600)

        self._unique_accounts: List[str] = sorted(
            list(set(t.get("Account", "") for t in transactions_data if t.get("Account")))
        )

        layout = QVBoxLayout(self)

        # --- Control Buttons ---
        controls_layout = QHBoxLayout()
        self.filter_button = QPushButton("Edit Filters...")
        self.filter_button.clicked.connect(self.open_filter_dialog)
        controls_layout.addWidget(self.filter_button)

        self.clear_filters_button = QPushButton("Clear All Filters")
        self.clear_filters_button.clicked.connect(self.clear_all_table_filters)
        controls_layout.addWidget(self.clear_filters_button)
        controls_layout.addStretch()  # Push buttons to the left
        layout.addLayout(controls_layout)

        # --- Table View ---
        self.table_view = QTableView()
        layout.addWidget(self.table_view)

        # --- Model Setup ---
        self.source_model = TransactionModel(transactions_data)
        self.proxy_model = TransactionSortFilterProxyModel()
        self.proxy_model.setSourceModel(self.source_model)

        self.table_view.setModel(self.proxy_model)

        # --- Table View Configuration ---
        self.table_view.setSortingEnabled(True)
        self.table_view.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        self.table_view.horizontalHeader().setStretchLastSection(True)
        self.table_view.setAlternatingRowColors(True)
        self.table_view.setSelectionBehavior(QTableView.SelectionBehavior.SelectRows)

        date_col_index = self.source_model._headers.index("Date")
        if date_col_index != -1:
            self.table_view.sortByColumn(date_col_index, Qt.SortOrder.DescendingOrder)

    @Slot()
    def open_filter_dialog(self) -> None:
        """
        Open the filter dialog to set transaction filters.

        Shows a modal dialog where the user can set filters for the transaction data.
        """
        current_proxy_filters = self.proxy_model.get_active_filters()
        dialog = FilterDialog(set(self._unique_accounts), current_proxy_filters, self)
        dialog.filters_applied.connect(self.apply_filters_from_dialog)
        dialog.exec()  # Show as modal

    @Slot(dict)
    def apply_filters_from_dialog(self, new_filters_dict: Dict[str, Any]) -> None:
        """
        Apply filters from the filter dialog to the proxy model.

        Args:
            new_filters_dict: Dictionary mapping column names to filter values
        """
        # First, clear any existing filters in the proxy model that are not in the new dict
        # This is important if a filter was previously set but now is cleared in the dialog
        all_column_indices = range(self.source_model.columnCount())
        current_proxy_filters = self.proxy_model.get_active_filters()

        for col_idx in all_column_indices:
            header_name = self.source_model.headerData(col_idx, Qt.Orientation.Horizontal)
            if header_name not in new_filters_dict and col_idx in current_proxy_filters:
                # This filter was active but is no longer, so clear it
                self.proxy_model.set_filter_value(col_idx, None, header_name)  # Pass None to clear

        # Now apply the new/updated filters
        for header_name, filter_value in new_filters_dict.items():
            try:
                col_idx = self.source_model._headers.index(header_name)
                self.proxy_model.set_filter_value(col_idx, filter_value, header_name)
            except ValueError:
                log.warning(f"Header '{header_name}' not found in model headers.")

    @Slot()
    def clear_all_table_filters(self) -> None:
        """
        Clear all active filters from the table.

        Removes all filters from the proxy model and updates the view.
        """
        if self.proxy_model.clear_all_filters():
            log.debug("All filters cleared from table.")
        else:
            log.debug("No active filters to clear.")
