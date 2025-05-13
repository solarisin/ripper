from decimal import Decimal, InvalidOperation

from PySide6.QtCore import (
    Qt,
    QAbstractTableModel,
    QModelIndex,
    QSortFilterProxyModel,
    QDate,
    Slot,
    Signal,  # Added Signal
    QRegularExpression,
)
from PySide6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QTableView,
    QLineEdit,
    QHeaderView,
    QLabel,
    QDoubleSpinBox,
    QComboBox,
    # QGroupBox, # No longer directly in main widget
    QGridLayout,
    QPushButton,  # Added
    QDialog,  # Added
    QDialogButtonBox,  # Added
)

# --- Sample Data (Simulating Tiller Spreadsheet Data) ---
sample_transactions = [
    {
        "ID": "t1",
        "Date": QDate(2025, 5, 1),
        "Description": "Coffee Shop",
        "Category": "Food & Drink",
        "Amount": -5.75,
        "Account": "Checking",
    },
    {
        "ID": "t2",
        "Date": QDate(2025, 5, 1),
        "Description": "Grocery Store",
        "Category": "Groceries",
        "Amount": -75.20,
        "Account": "Credit Card",
    },
    {
        "ID": "t3",
        "Date": QDate(2025, 5, 2),
        "Description": "Salary Deposit",
        "Category": "Income",
        "Amount": 2500.00,
        "Account": "Checking",
    },
    {
        "ID": "t4",
        "Date": QDate(2025, 5, 3),
        "Description": "Online Subscription",
        "Category": "Software",
        "Amount": -15.00,
        "Account": "Credit Card",
    },
    {
        "ID": "t5",
        "Date": QDate(2025, 5, 4),
        "Description": "Book Purchase",
        "Category": "Shopping",
        "Amount": -25.99,
        "Account": "Checking",
    },
    {
        "ID": "t6",
        "Date": QDate(2025, 5, 5),
        "Description": "Restaurant Dinner",
        "Category": "Food & Drink",
        "Amount": -60.00,
        "Account": "Credit Card",
    },
    {
        "ID": "t7",
        "Date": QDate(2025, 5, 5),
        "Description": "Gasoline",
        "Category": "Transportation",
        "Amount": -45.50,
        "Account": "Credit Card",
    },
    {
        "ID": "t8",
        "Date": QDate(2025, 5, 6),
        "Description": "ATM Withdrawal",
        "Category": "Cash",
        "Amount": -100.00,
        "Account": "Checking",
    },
    {
        "ID": "t9",
        "Date": QDate(2025, 5, 7),
        "Description": "Refund from Store",
        "Category": "Shopping",
        "Amount": 10.50,
        "Account": "Credit Card",
    },
    {
        "ID": "t10",
        "Date": QDate(2025, 5, 8),
        "Description": "Utility Bill",
        "Category": "Bills",
        "Amount": -120.30,
        "Account": "Checking",
    },
]


class TransactionModel(QAbstractTableModel):
    def __init__(self, data=None):
        super().__init__()
        self._data = data or []
        # Define column order and names. Also used as keys for data dictionaries.
        self.column_keys = ["ID", "Date", "Description", "Category", "Amount", "Account"]
        self._headers = ["ID", "Date", "Description", "Category", "Amount", "Account"]

    def rowCount(self, parent=QModelIndex()):
        return len(self._data)

    def columnCount(self, parent=QModelIndex()):
        return len(self._headers)

    def data(self, index, role=Qt.ItemDataRole.DisplayRole):
        if not index.isValid():
            return None

        row = index.row()
        col_name = self._headers[index.column()]
        item = self._data[row]

        if role == Qt.ItemDataRole.DisplayRole:
            value = item.get(col_name)
            if isinstance(value, QDate):
                return value.toString("yyyy-MM-dd")
            if isinstance(value, (float, Decimal)):
                try:
                    return f"{Decimal(value):.2f}"
                except InvalidOperation:
                    return str(value)  # Fallback if not a valid decimal
            return str(value)
        elif role == Qt.ItemDataRole.EditRole:
            return item.get(col_name)
        elif role == Qt.ItemDataRole.TextAlignmentRole:
            value = item.get(col_name)
            if isinstance(value, (int, float, Decimal)):
                return Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
            return Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter
        return None

    def headerData(self, section, orientation, role=Qt.ItemDataRole.DisplayRole):
        if role == Qt.ItemDataRole.DisplayRole:
            if orientation == Qt.Orientation.Horizontal:
                return self._headers[section]
        return None

    def sort(self, column, order=Qt.SortOrder.AscendingOrder):
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
            print(f"Error sorting by {col_name}: {e}")
        self.layoutChanged.emit()

    def setDataList(self, data):
        self.beginResetModel()
        self._data = data
        self.endResetModel()


# --- Custom SortFilterProxyModel (Unchanged from previous version) ---
class TransactionSortFilterProxyModel(QSortFilterProxyModel):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._filters = {}

    def set_filter_value(self, column_index, value, header_name=None):  # Added header_name for clarity
        if value is not None and value != "" and value != (None, None):  # Check for meaningful filter
            self._filters[column_index] = {"value": value, "header": header_name}
        elif column_index in self._filters:
            del self._filters[column_index]
        self.invalidateFilter()

    def get_active_filters(self):
        return self._filters

    def clear_all_filters(self):
        if not self._filters:
            return False  # No filters to clear
        self._filters.clear()
        self.invalidateFilter()
        return True  # Filters were cleared

    def filterAcceptsRow(self, source_row, source_parent):
        if not self._filters:
            return True

        model = self.sourceModel()
        for column_index, filter_info in self._filters.items():
            filter_value = filter_info["value"]
            header_name = filter_info["header"]  # Get header name from stored info
            if not self._check_row_against_filter(model, source_row, column_index, filter_value, header_name):
                return False
        return True

    def _check_row_against_filter(self, model, source_row, column_index, filter_value, header_name):
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

    def lessThan(self, left, right):
        left_data = self.sourceModel().data(left, Qt.ItemDataRole.EditRole)
        right_data = self.sourceModel().data(right, Qt.ItemDataRole.EditRole)

        if left.column() == self.sourceModel()._headers.index("Amount"):
            try:
                return Decimal(str(left_data)) < Decimal(str(right_data))
            except (InvalidOperation, TypeError):  # Added TypeError for None comparison
                pass
        if left.column() == self.sourceModel()._headers.index("Date"):
            if isinstance(left_data, QDate) and isinstance(right_data, QDate):
                return left_data < right_data

        try:
            return str(left_data).lower() < str(right_data).lower()
        except TypeError:
            if left_data is None and right_data is not None:
                return True
            if left_data is not None and right_data is None:
                return False
            return False


# --- Filter Dialog ---
class FilterDialog(QDialog):
    filters_applied = Signal(dict)

    def __init__(self, unique_accounts, current_filters=None, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Set Transaction Filters")
        self.setMinimumWidth(400)

        self._unique_accounts = ["All Accounts"] + sorted(list(unique_accounts))
        self._current_filters = current_filters if current_filters else {}
        self._source_model_headers = [
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

    def populate_fields(self):
        """Populate dialog fields with current_filters."""
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

    def reset_fields(self):
        """Reset dialog fields to their default/empty state."""
        self.description_filter_input.clear()
        self.category_filter_input.clear()
        self.account_filter_combo.setCurrentText("All Accounts")
        self.amount_min_input.setValue(self.amount_min_input.minimum())
        self.amount_max_input.setValue(self.amount_max_input.maximum())

    def get_filters(self):
        """Collect filter values from the dialog's input fields."""
        filters = {}

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

    def apply_and_accept(self):
        """Emit collected filters and accept the dialog."""
        self.filters_applied.emit(self.get_filters())
        self.accept()


# --- Main Application Window ---
class TransactionTableViewWidget(QWidget):
    def __init__(self, transactions_data, *, simulate=False):
        super().__init__()
        self.setWindowTitle("Tiller Transaction Viewer")
        self.setGeometry(100, 100, 1000, 600)

        if not transactions_data and simulate:
            transactions_data = sample_transactions
        self._unique_accounts = sorted(list(set(t.get("Account", "") for t in transactions_data if t.get("Account"))))

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
    def open_filter_dialog(self):
        current_proxy_filters = self.proxy_model.get_active_filters()
        dialog = FilterDialog(self._unique_accounts, current_proxy_filters, self)
        dialog.filters_applied.connect(self.apply_filters_from_dialog)
        dialog.exec()  # Show as modal

    @Slot(dict)
    def apply_filters_from_dialog(self, new_filters_dict):
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
                print(f"Warning: Header '{header_name}' not found in model headers.")

    @Slot()
    def clear_all_table_filters(self):
        if self.proxy_model.clear_all_filters():
            print("All filters cleared from table.")
        else:
            print("No active filters to clear.")
