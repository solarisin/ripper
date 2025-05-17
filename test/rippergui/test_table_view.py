import unittest
from decimal import Decimal
import pytest
from PySide6.QtCore import Qt, QDate, QRegularExpression

from rippergui.table_view import (
    TransactionModel,
    TransactionSortFilterProxyModel,
    FilterDialog,
    TransactionTableViewWidget,
    sample_transactions,
)


@pytest.mark.qt
class TestTransactionModel(unittest.TestCase):
    """Test cases for the TransactionModel class."""

    def setUp(self):
        """Set up test fixtures."""
        self.test_data = [
            {
                "ID": "t1",
                "Date": QDate(2025, 5, 1),
                "Description": "Test Transaction 1",
                "Category": "Test Category",
                "Amount": -50.25,
                "Account": "Test Account",
            },
            {
                "ID": "t2",
                "Date": QDate(2025, 5, 2),
                "Description": "Test Transaction 2",
                "Category": "Another Category",
                "Amount": 100.50,
                "Account": "Another Account",
            },
        ]
        self.model = TransactionModel(self.test_data)

    def test_row_count(self):
        """Test that rowCount returns the correct number of rows."""
        self.assertEqual(self.model.rowCount(), 2)

    def test_column_count(self):
        """Test that columnCount returns the correct number of columns."""
        self.assertEqual(self.model.columnCount(), 6)  # ID, Date, Description, Category, Amount, Account

    def test_data_display_role(self):
        """Test that data returns the correct values for DisplayRole."""
        # Test ID column
        index = self.model.index(0, 0)
        self.assertEqual(self.model.data(index, Qt.ItemDataRole.DisplayRole), "t1")

        # Test Date column
        index = self.model.index(0, 1)
        self.assertEqual(self.model.data(index, Qt.ItemDataRole.DisplayRole), "2025-05-01")

        # Test Description column
        index = self.model.index(0, 2)
        self.assertEqual(self.model.data(index, Qt.ItemDataRole.DisplayRole), "Test Transaction 1")

        # Test Category column
        index = self.model.index(0, 3)
        self.assertEqual(self.model.data(index, Qt.ItemDataRole.DisplayRole), "Test Category")

        # Test Amount column
        index = self.model.index(0, 4)
        self.assertEqual(self.model.data(index, Qt.ItemDataRole.DisplayRole), "-50.25")

        # Test Account column
        index = self.model.index(0, 5)
        self.assertEqual(self.model.data(index, Qt.ItemDataRole.DisplayRole), "Test Account")

    def test_data_edit_role(self):
        """Test that data returns the correct values for EditRole."""
        # Test Amount column
        index = self.model.index(0, 4)
        self.assertEqual(self.model.data(index, Qt.ItemDataRole.EditRole), -50.25)

        # Test Date column
        index = self.model.index(0, 1)
        self.assertEqual(self.model.data(index, Qt.ItemDataRole.EditRole), QDate(2025, 5, 1))

    def test_data_alignment_role(self):
        """Test that data returns the correct alignment for TextAlignmentRole."""
        # Test text column (Description)
        index = self.model.index(0, 2)
        alignment = self.model.data(index, Qt.ItemDataRole.TextAlignmentRole)
        self.assertEqual(alignment, Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)

        # Test numeric column (Amount)
        index = self.model.index(0, 4)
        alignment = self.model.data(index, Qt.ItemDataRole.TextAlignmentRole)
        self.assertEqual(alignment, Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)

    def test_header_data(self):
        """Test that headerData returns the correct header labels."""
        self.assertEqual(self.model.headerData(0, Qt.Orientation.Horizontal), "ID")
        self.assertEqual(self.model.headerData(1, Qt.Orientation.Horizontal), "Date")
        self.assertEqual(self.model.headerData(2, Qt.Orientation.Horizontal), "Description")
        self.assertEqual(self.model.headerData(3, Qt.Orientation.Horizontal), "Category")
        self.assertEqual(self.model.headerData(4, Qt.Orientation.Horizontal), "Amount")
        self.assertEqual(self.model.headerData(5, Qt.Orientation.Horizontal), "Account")

    def test_sort_by_amount(self):
        """Test sorting by amount column."""
        # Sort by amount ascending
        self.model.sort(4, Qt.SortOrder.AscendingOrder)
        self.assertEqual(self.model._data[0]["ID"], "t1")  # -50.25 comes before 100.50
        self.assertEqual(self.model._data[1]["ID"], "t2")

        # Sort by amount descending
        self.model.sort(4, Qt.SortOrder.DescendingOrder)
        self.assertEqual(self.model._data[0]["ID"], "t2")  # 100.50 comes before -50.25
        self.assertEqual(self.model._data[1]["ID"], "t1")

    def test_sort_by_date(self):
        """Test sorting by date column."""
        # Sort by date ascending
        self.model.sort(1, Qt.SortOrder.AscendingOrder)
        self.assertEqual(self.model._data[0]["ID"], "t1")  # 2025-05-01 comes before 2025-05-02
        self.assertEqual(self.model._data[1]["ID"], "t2")

        # Sort by date descending
        self.model.sort(1, Qt.SortOrder.DescendingOrder)
        self.assertEqual(self.model._data[0]["ID"], "t2")  # 2025-05-02 comes before 2025-05-01
        self.assertEqual(self.model._data[1]["ID"], "t1")

    def test_sort_by_text(self):
        """Test sorting by text column."""
        # Sort by description ascending
        self.model.sort(2, Qt.SortOrder.AscendingOrder)
        self.assertEqual(self.model._data[0]["ID"], "t1")  # "Test Transaction 1" comes before "Test Transaction 2"
        self.assertEqual(self.model._data[1]["ID"], "t2")

        # Sort by description descending
        self.model.sort(2, Qt.SortOrder.DescendingOrder)
        self.assertEqual(self.model._data[0]["ID"], "t2")  # "Test Transaction 2" comes before "Test Transaction 1"
        self.assertEqual(self.model._data[1]["ID"], "t1")

    def test_set_data_list(self):
        """Test setting a new data list."""
        new_data = [
            {
                "ID": "t3",
                "Date": QDate(2025, 5, 3),
                "Description": "New Transaction",
                "Category": "New Category",
                "Amount": 75.00,
                "Account": "New Account",
            }
        ]
        self.model.setDataList(new_data)
        self.assertEqual(self.model.rowCount(), 1)
        self.assertEqual(self.model.data(self.model.index(0, 0)), "t3")


@pytest.mark.qt
class TestTransactionSortFilterProxyModel(unittest.TestCase):
    """Test cases for the TransactionSortFilterProxyModel class."""

    def setUp(self):
        """Set up test fixtures."""
        self.test_data = [
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
                "Date": QDate(2025, 5, 2),
                "Description": "Grocery Store",
                "Category": "Groceries",
                "Amount": -75.20,
                "Account": "Credit Card",
            },
            {
                "ID": "t3",
                "Date": QDate(2025, 5, 3),
                "Description": "Salary Deposit",
                "Category": "Income",
                "Amount": 2500.00,
                "Account": "Checking",
            },
        ]
        self.source_model = TransactionModel(self.test_data)
        self.proxy_model = TransactionSortFilterProxyModel()
        self.proxy_model.setSourceModel(self.source_model)

    def test_set_filter_value(self):
        """Test setting a filter value."""
        # Set a filter on the Description column
        self.proxy_model.set_filter_value(2, "Coffee", "Description")

        # Check that the filter was stored
        filters = self.proxy_model.get_active_filters()
        self.assertIn(2, filters)
        self.assertEqual(filters[2]["value"], "Coffee")
        self.assertEqual(filters[2]["header"], "Description")

    def test_clear_all_filters(self):
        """Test clearing all filters."""
        # Set some filters
        self.proxy_model.set_filter_value(2, "Coffee", "Description")
        self.proxy_model.set_filter_value(5, "Checking", "Account")

        # Clear all filters
        result = self.proxy_model.clear_all_filters()

        # Check that the filters were cleared
        self.assertTrue(result)
        self.assertEqual(self.proxy_model.get_active_filters(), {})

    def test_filter_by_description(self):
        """Test filtering by description."""
        # Set a filter on the Description column
        self.proxy_model.set_filter_value(2, "Coffee", "Description")

        # Check that only the Coffee Shop transaction is shown
        self.assertEqual(self.proxy_model.rowCount(), 1)
        self.assertEqual(self.proxy_model.data(self.proxy_model.index(0, 0)), "t1")

    def test_filter_by_account(self):
        """Test filtering by account."""
        # Set a filter on the Account column
        self.proxy_model.set_filter_value(5, "Checking", "Account")

        # Check that only Checking account transactions are shown
        self.assertEqual(self.proxy_model.rowCount(), 2)
        self.assertEqual(self.proxy_model.data(self.proxy_model.index(0, 0)), "t1")
        self.assertEqual(self.proxy_model.data(self.proxy_model.index(1, 0)), "t3")

    def test_filter_by_amount_range(self):
        """Test filtering by amount range."""
        # Set a filter on the Amount column for negative values
        self.proxy_model.set_filter_value(4, (Decimal("-100"), Decimal("0")), "Amount")

        # Check that only negative amount transactions are shown
        self.assertEqual(self.proxy_model.rowCount(), 2)
        self.assertEqual(self.proxy_model.data(self.proxy_model.index(0, 0)), "t1")
        self.assertEqual(self.proxy_model.data(self.proxy_model.index(1, 0)), "t2")

    def test_multiple_filters(self):
        """Test applying multiple filters."""
        # Set filters on Description and Account columns
        self.proxy_model.set_filter_value(2, "Coffee", "Description")
        self.proxy_model.set_filter_value(5, "Checking", "Account")

        # Check that only transactions matching both filters are shown
        self.assertEqual(self.proxy_model.rowCount(), 1)
        self.assertEqual(self.proxy_model.data(self.proxy_model.index(0, 0)), "t1")

    def test_less_than_comparison(self):
        """Test the lessThan method for sorting."""
        # Create model indices for comparison
        left_index = self.source_model.index(0, 4)  # Amount: -5.75
        right_index = self.source_model.index(1, 4)  # Amount: -75.20

        # Check amount comparison
        self.assertFalse(self.proxy_model.lessThan(left_index, right_index))  # -5.75 > -75.20
        self.assertTrue(self.proxy_model.lessThan(right_index, left_index))  # -75.20 < -5.75

        # Check date comparison
        left_index = self.source_model.index(0, 1)  # Date: 2025-05-01
        right_index = self.source_model.index(1, 1)  # Date: 2025-05-02
        self.assertTrue(self.proxy_model.lessThan(left_index, right_index))  # 2025-05-01 < 2025-05-02
        self.assertFalse(self.proxy_model.lessThan(right_index, left_index))  # 2025-05-02 > 2025-05-01


@pytest.mark.qt
class TestTransactionTableViewWidget:
    """Test cases for the TransactionTableViewWidget class."""

    def test_initialization(self, qtbot):
        """Test that the widget initializes correctly."""
        # Create the widget with sample data
        widget = TransactionTableViewWidget(simulate=True)
        qtbot.addWidget(widget)

        # Check that the model was initialized with sample data
        assert widget.source_model.rowCount() == len(sample_transactions)

        # Check that the table view was set up correctly
        assert widget.table_view.isSortingEnabled()
        assert widget.table_view.alternatingRowColors()

    def test_clear_all_filters(self, qtbot):
        """Test clearing all filters."""
        # Create the widget with sample data
        widget = TransactionTableViewWidget(simulate=True)
        qtbot.addWidget(widget)

        # Set a filter
        widget.proxy_model.set_filter_value(2, "Coffee", "Description")

        # Clear all filters
        widget.clear_all_table_filters()

        # Check that the filters were cleared
        assert widget.proxy_model.get_active_filters() == {}


@pytest.mark.qt
class TestFilterDialog:
    """Test cases for the FilterDialog class."""

    def test_initialization(self, qtbot):
        """Test that the dialog initializes correctly."""
        # Create the dialog
        unique_accounts = {"Checking", "Credit Card"}
        dialog = FilterDialog(unique_accounts)
        qtbot.addWidget(dialog)

        # Check that the account combo box was populated correctly
        assert dialog.account_filter_combo.count() == 3  # All Accounts + 2 unique accounts
        assert dialog.account_filter_combo.itemText(0) == "All Accounts"
        assert dialog.account_filter_combo.itemText(1) == "Checking"
        assert dialog.account_filter_combo.itemText(2) == "Credit Card"

    def test_reset_fields(self, qtbot):
        """Test resetting fields."""
        # Create the dialog
        unique_accounts = {"Checking", "Credit Card"}
        dialog = FilterDialog(unique_accounts)
        qtbot.addWidget(dialog)

        # Set some values
        dialog.description_filter_input.setText("Test")
        dialog.category_filter_input.setText("Test")
        dialog.account_filter_combo.setCurrentText("Checking")
        dialog.amount_min_input.setValue(10.0)
        dialog.amount_max_input.setValue(100.0)

        # Reset fields
        dialog.reset_fields()

        # Check that the fields were reset
        assert dialog.description_filter_input.text() == ""
        assert dialog.category_filter_input.text() == ""
        assert dialog.account_filter_combo.currentText() == "All Accounts"
        assert dialog.amount_min_input.value() == dialog.amount_min_input.minimum()
        assert dialog.amount_max_input.value() == dialog.amount_max_input.maximum()

    def test_get_filters(self, qtbot):
        """Test getting filters from the dialog."""
        # Create the dialog
        unique_accounts = {"Checking", "Credit Card"}
        dialog = FilterDialog(unique_accounts)
        qtbot.addWidget(dialog)

        # Set some values
        dialog.description_filter_input.setText("Coffee")
        dialog.account_filter_combo.setCurrentText("Checking")
        dialog.amount_min_input.setValue(-100.0)
        dialog.amount_max_input.setValue(0.0)

        # Get filters
        filters = dialog.get_filters()

        # Check that the filters were collected correctly
        assert "Description" in filters
        assert isinstance(filters["Description"], QRegularExpression)
        assert filters["Description"].pattern() == "Coffee"

        assert "Account" in filters
        assert filters["Account"] == "Checking"

        assert "Amount" in filters
        assert filters["Amount"][0] == Decimal("-100.0")
        assert filters["Amount"][1] == Decimal("0.0")

    def test_apply_and_accept(self, qtbot):
        """Test applying filters and accepting the dialog."""
        # Create the dialog
        unique_accounts = {"Checking", "Credit Card"}
        dialog = FilterDialog(unique_accounts)
        qtbot.addWidget(dialog)

        # Set up a signal spy
        with qtbot.waitSignal(dialog.filters_applied, timeout=1000) as blocker:
            # Set some values
            dialog.description_filter_input.setText("Coffee")

            # Apply and accept
            dialog.apply_and_accept()

        # Check that the signal was emitted with the correct filters
        filters = blocker.args[0]
        assert "Description" in filters
        assert isinstance(filters["Description"], QRegularExpression)
        assert filters["Description"].pattern() == "Coffee"
