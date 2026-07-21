import unittest
import warnings
from decimal import Decimal

import pytest
from PySide6.QtCore import QDate, Qt

from ripper.rippergui.table_view import (
    FilterDialog,
    TransactionModel,
    TransactionSortFilterProxyModel,
    TransactionTableViewWidget,
    is_number,
    parse_decimal,
    parse_number,
)


class TestParseNumericHelpers(unittest.TestCase):
    """Tests for the shared strict numeric parser (no Qt app required)."""

    def test_rejects_malformed_input(self):
        """Malformed input is rejected (None), not silently coerced."""
        bad_inputs = [
            # Original malformed cases.
            "12-34",
            "a1b2",
            "1.2.3",
            "1-2-3",
            "12a",
            "abc",
            "",
            "   ",
            "$",
            "-",
            "(1",
            # Reviewer's reproduced regressions: currency stripped before validating.
            "1$2",  # currency mid-number
            "$$1",  # repeated currency
            "$-5.75",  # currency before sign (sign not in leading slot)
            # Reviewer's reproduced regressions: bad thousands grouping.
            "1,2,3",
            "12,34",
            # Extra thousands-grouping edge cases.
            "1,23",  # group too short
            "1,2345",  # group too long
            ",100",  # leading comma
            "100,",  # trailing comma
            "1,200,",  # trailing comma after a valid group
            "1,200,00",  # final group too short
            # Reviewer's reproduced regressions: signed value inside accounting parens.
            "(-50)",
            "($-50)",
        ]
        for bad in bad_inputs:
            self.assertIsNone(parse_decimal(bad), f"expected None for {bad!r}")
            self.assertIsNone(parse_number(bad), f"expected None for {bad!r}")
            self.assertFalse(is_number(bad), f"expected non-number for {bad!r}")

    def test_accepts_valid_currency_and_numbers(self):
        """Well-formed currency/number strings parse to the expected value."""
        cases = {
            "$1,200.50": Decimal("1200.50"),
            "1200.50": Decimal("1200.50"),
            "100.50": Decimal("100.50"),
            "-50.25": Decimal("-50.25"),
            "-$5.75": Decimal("-5.75"),  # sign in the leading slot, then currency
            "(50.25)": Decimal("-50.25"),
            "($1,200.50)": Decimal("-1200.50"),
            "($50)": Decimal("-50"),
            "2500": Decimal("2500"),
            "1,200": Decimal("1200"),
            "1,200,000.00": Decimal("1200000.00"),
            ".5": Decimal("0.5"),
            "+3": Decimal("3"),
        }
        for text, expected in cases.items():
            self.assertEqual(parse_decimal(text), expected, f"parse_decimal({text!r})")
            self.assertTrue(is_number(text), f"is_number({text!r})")

    def test_accepts_native_numeric_types(self):
        """int/float/Decimal pass through; bool does not."""
        self.assertEqual(parse_decimal(100.5), Decimal("100.5"))
        self.assertEqual(parse_decimal(-7), Decimal("-7"))
        self.assertEqual(parse_decimal(Decimal("3.14")), Decimal("3.14"))
        self.assertEqual(parse_number(-50.25), -50.25)
        self.assertIsNone(parse_decimal(None))
        self.assertIsNone(parse_decimal(True))
        self.assertIsNone(parse_decimal(False))


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

    def _sorted_ids(self, column: int, order: Qt.SortOrder) -> list[str]:
        """Sort through the proxy (the real, single sort path) and return the ID order."""
        proxy = TransactionSortFilterProxyModel()
        proxy.setSourceModel(self.model)
        proxy.sort(column, order)
        return [proxy.data(proxy.index(row, 0), Qt.ItemDataRole.EditRole) for row in range(proxy.rowCount())]

    def test_sort_by_amount(self):
        """Test sorting by amount column through the proxy sort path."""
        # -50.25 comes before 100.50
        self.assertEqual(self._sorted_ids(4, Qt.SortOrder.AscendingOrder), ["t1", "t2"])
        self.assertEqual(self._sorted_ids(4, Qt.SortOrder.DescendingOrder), ["t2", "t1"])

    def test_sort_by_date(self):
        """Test sorting by date column through the proxy sort path."""
        # 2025-05-01 comes before 2025-05-02
        self.assertEqual(self._sorted_ids(1, Qt.SortOrder.AscendingOrder), ["t1", "t2"])
        self.assertEqual(self._sorted_ids(1, Qt.SortOrder.DescendingOrder), ["t2", "t1"])

    def test_sort_by_text(self):
        """Test sorting by text column through the proxy sort path."""
        # "Test Transaction 1" comes before "Test Transaction 2"
        self.assertEqual(self._sorted_ids(2, Qt.SortOrder.AscendingOrder), ["t1", "t2"])
        self.assertEqual(self._sorted_ids(2, Qt.SortOrder.DescendingOrder), ["t2", "t1"])

    def test_infer_column_type_not_confused_by_digit_strings(self):
        """A string column containing digits must not be mis-typed as numeric."""
        data = [
            {"ID": "t1", "Description": "12-34"},
            {"ID": "t2", "Description": "a1b2"},
            {"ID": "t3", "Description": "invoice 7"},
        ]
        model = TransactionModel(data)
        desc_col = model._headers.index("Description")
        self.assertEqual(model.infer_column_type(desc_col), "string")

    def test_infer_column_type_numeric_column(self):
        """A genuinely numeric column is still typed as a number."""
        data = [{"Amount": "$1,200.50"}, {"Amount": "-50.25"}, {"Amount": "(75.00)"}]
        model = TransactionModel(data)
        model._headers = ["Amount"]
        self.assertEqual(model.infer_column_type(0), "number")

    def test_display_data_blank_for_missing_value(self):
        """Missing/absent keys render as an empty string, not the literal 'None'."""
        data = [{"Description": "Only description"}]  # no Account/Category/etc.
        model = TransactionModel(data)
        account_col = model._headers.index("Account")
        category_col = model._headers.index("Category")
        self.assertEqual(model.data(model.index(0, account_col), Qt.ItemDataRole.DisplayRole), "")
        self.assertEqual(model.data(model.index(0, category_col), Qt.ItemDataRole.DisplayRole), "")

    def test_filter_amount_uses_shared_strict_parser(self):
        """The amount filter path parses via the shared strict parser."""
        proxy = TransactionSortFilterProxyModel()
        proxy.setSourceModel(self.model)
        # "$1,200.50" style string values must be parsed, malformed ones rejected.
        self.assertTrue(
            proxy._check_record_against_filter({"Amount": "$1,200.50"}, (Decimal("1000"), Decimal("2000")), "Amount")
        )
        self.assertFalse(
            proxy._check_record_against_filter({"Amount": "12-34"}, (Decimal("0"), Decimal("9999")), "Amount")
        )

    def test_set_data_list(self):
        """Test setting a new data list by directly updating the model's data."""
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
        self.model._data = new_data
        self.model.layoutChanged.emit()
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

    def test_less_than_string_debug_log_interpolates_values(self):
        """The string-comparison debug log must substitute values, not print literal placeholders (#109).

        loguru formats with str.format, not %-style, so the old `log.debug("... %s ...", val)` printed
        the literal template and dropped the args. Capture the emitted record and assert the real
        column/values appear and no %-placeholder survives.
        """
        from loguru import logger

        records: list[str] = []
        sink_id = logger.add(records.append, level="DEBUG", format="{message}")
        try:
            # Column 2 is Description ("Coffee Shop" vs "Grocery Store") — the string path.
            left_index = self.source_model.index(0, 2)
            right_index = self.source_model.index(1, 2)
            self.proxy_model.lessThan(left_index, right_index)
        finally:
            logger.remove(sink_id)

        line = next(m for m in records if m.startswith("String comparison"))
        self.assertIn("Coffee Shop", line)
        self.assertIn("Grocery Store", line)
        self.assertIn("Description", line)  # the resolved header, not a %s
        self.assertNotIn("%s", line)
        self.assertNotIn("%d", line)


@pytest.mark.qt
class TestTransactionTableViewWidget:
    """Test cases for the TransactionTableViewWidget class."""

    @pytest.fixture(autouse=True)
    def setup_sample_transactions(self):
        self.sample_transactions = [
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
        ]

    def test_initialization(self, qtbot):
        """Test that the widget initializes correctly."""
        # Create sample transactions to pass into the view

        # Create the widget with sample data
        widget = TransactionTableViewWidget(self.sample_transactions)
        qtbot.addWidget(widget)

        # Check that the model was initialized with sample data
        assert widget.source_model.rowCount() == len(self.sample_transactions)

        # Check that the table view was set up correctly
        assert widget.table_view.isSortingEnabled()
        assert widget.table_view.alternatingRowColors()

    def test_clear_all_filters(self, qtbot):
        """Test clearing all filters."""
        # Create the widget with sample data
        widget = TransactionTableViewWidget(self.sample_transactions)
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
        assert isinstance(filters["Description"], str)
        assert filters["Description"] == "Coffee"

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
        with warnings.catch_warnings():
            warnings.filterwarnings("ignore", category=RuntimeWarning)
            with qtbot.waitSignal(dialog.filters_applied, timeout=1000) as blocker:
                # Set some values
                dialog.description_filter_input.setText("Coffee")

                # Apply and accept
                dialog.apply_and_accept()

        # Check that the signal was emitted with the correct filters
        filters = blocker.args[0]
        assert "Description" in filters
        assert isinstance(filters["Description"], str)
        assert filters["Description"] == "Coffee"
