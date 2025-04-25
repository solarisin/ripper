import sys
import pytest
from PySide6.QtWidgets import QApplication, QLabel, QMainWindow, QMessageBox, QComboBox
from src.widgets.main_window import MainWindow
from src.widgets.google_sheets_selector import GoogleSheetsSelector
from src.widgets.transaction_table import TransactionTableViewWidget
from uibot import UIBot
from unittest.mock import patch, MagicMock

@pytest.fixture
def app(qtbot):
    test_app = QApplication(sys.argv)
    window = MainWindow()
    qtbot.addWidget(window)
    return window

@pytest.fixture
def uibot(app):
    return UIBot(app)

def test_display_data(app, uibot):
    transactions = [
        {"date": "2022-01-01", "description": "Test Transaction 1", "amount": 100.0, "category": "Test"},
        {"date": "2022-01-02", "description": "Test Transaction 2", "amount": 200.0, "category": "Test"}
    ]
    app.transaction_table_view_widget.display_data(transactions)
    assert app.transaction_table_view_widget.model.rowCount() == 2
    assert app.transaction_table_view_widget.model.item(0, 0).text() == "2022-01-01"
    assert app.transaction_table_view_widget.model.item(0, 1).text() == "Test Transaction 1"
    assert app.transaction_table_view_widget.model.item(0, 2).text() == "100.0"
    assert app.transaction_table_view_widget.model.item(0, 3).text() == "Test"

def test_advanced_table_features(app, uibot):
    transactions = [
        {"date": "2022-01-01", "description": "Test Transaction 1", "amount": 100.0, "category": "Test"},
        {"date": "2022-01-02", "description": "Test Transaction 2", "amount": 200.0, "category": "Test"}
    ]
    app.transaction_table_view_widget.display_data(transactions)
    uibot.set_text(app.search_bar, "Test Transaction 1")
    assert app.transaction_table_view_widget.proxy_model.rowCount() == 1
    assert app.transaction_table_view_widget.proxy_model.index(0, 1).data() == "Test Transaction 1"

def test_dashboard_view(app, uibot):
    transactions = [
        {"date": "2022-01-01", "description": "Test Transaction 1", "amount": 100.0, "category": "Test"},
        {"date": "2022-01-02", "description": "Test Transaction 2", "amount": 200.0, "category": "Test"}
    ]
    app.transaction_table_view_widget.display_data(transactions)
    uibot.click_button(app.show_charts_button)
    assert app.findChild(QMainWindow, "Charts") is not None

def test_user_notifications_for_errors(app, uibot, mocker):
    mocker.patch("google_sheets_selector.authenticate", side_effect=Exception("Test Error"))
    with uibot.wait_signal(app.load_data, timeout=1000):
        app.load_data()
    assert app.findChild(QMessageBox, "Error") is not None

def test_display_google_sheets(app, uibot):
    google_sheets = [
        {"id": "sheet1", "name": "Test Sheet 1"},
        {"id": "sheet2", "name": "Test Sheet 2"}
    ]
    app.google_sheets_selector.display_google_sheets(google_sheets)
    assert app.google_sheets_selector.google_sheets_combo.count() == 2
    assert app.google_sheets_selector.google_sheets_combo.itemText(0) == "Test Sheet 1"
    assert app.google_sheets_selector.google_sheets_combo.itemText(1) == "Test Sheet 2"

def test_load_selected_google_sheet(app, uibot, mocker):
    google_sheets = [
        {"id": "sheet1", "name": "Test Sheet 1"},
        {"id": "sheet2", "name": "Test Sheet 2"}
    ]
    app.google_sheets_selector.display_google_sheets(google_sheets)
    uibot.set_combobox_index(app.google_sheets_selector.google_sheets_combo, 1)
    assert app.google_sheets_selector.metadata_label.text() == "Selected Google Sheet ID: sheet2"
    # Add additional assertions for metadata such as last modified date and owner

def test_filter_google_sheets(app, uibot, mocker):
    google_sheets = [
        {"id": "sheet1", "name": "Test Sheet 1"},
        {"id": "sheet2", "name": "Test Sheet 2"}
    ]
    app.google_sheets_selector.display_google_sheets(google_sheets)
    assert app.google_sheets_selector.google_sheets_combo.count() == 2
    assert app.google_sheets_selector.google_sheets_combo.itemText(0) == "Test Sheet 1"
    assert app.google_sheets_selector.google_sheets_combo.itemText(1) == "Test Sheet 2"
    # Add additional assertions to ensure only Google Sheets are displayed

def test_maintain_separate_datasets(app, uibot, mocker):
    transactions1 = [
        {"date": "2022-01-01", "description": "Test Transaction 1", "amount": 100.0, "category": "Test"}
    ]
    transactions2 = [
        {"date": "2022-01-02", "description": "Test Transaction 2", "amount": 200.0, "category": "Test"}
    ]
    app.transaction_table_view_widget.display_data(transactions1)
    assert app.transaction_table_view_widget.model.rowCount() == 1
    assert app.transaction_table_view_widget.model.item(0, 0).text() == "2022-01-01"
    app.transaction_table_view_widget.display_data(transactions2)
    assert app.transaction_table_view_widget.model.rowCount() == 1
    assert app.transaction_table_view_widget.model.item(0, 0).text() == "2022-01-02"

def test_load_data_displays_google_sheets(app, uibot, mocker):
    mocker.patch("google_sheets_selector.authenticate", return_value="mock_credentials")
    mocker.patch("google_sheets_selector.list_google_sheets", return_value=[
        {"id": "sheet1", "name": "Test Sheet 1"},
        {"id": "sheet2", "name": "Test Sheet 2"}
    ])
    mocker.patch("google_sheets_selector.retrieve_transactions", return_value=[])

    app.load_data()
    assert app.google_sheets_selector.google_sheets_combo.count() == 2
    assert app.google_sheets_selector.google_sheets_combo.itemText(0) == "Test Sheet 1"
    assert app.google_sheets_selector.google_sheets_combo.itemText(1) == "Test Sheet 2"

def test_open_file_picker_allows_selecting_google_sheet(app, uibot, mocker):
    google_sheets = [
        {"id": "sheet1", "name": "Test Sheet 1"},
        {"id": "sheet2", "name": "Test Sheet 2"}
    ]
    app.google_sheets_selector.display_google_sheets(google_sheets)
    uibot.set_combobox_index(app.google_sheets_selector.google_sheets_combo, 1)
    assert app.google_sheets_selector.metadata_label.text() == "Selected Google Sheet ID: sheet2"
    # Add additional assertions for metadata such as last modified date and owner

def test_fetch_and_display_metadata(app, uibot, mocker):
    google_sheets = [
        {"id": "sheet1", "name": "Test Sheet 1", "last_modified": "2022-01-01", "owner": "User1"},
        {"id": "sheet2", "name": "Test Sheet 2", "last_modified": "2022-01-02", "owner": "User2"}
    ]
    app.google_sheets_selector.display_google_sheets(google_sheets)
    uibot.set_combobox_index(app.google_sheets_selector.google_sheets_combo, 1)
    assert app.google_sheets_selector.metadata_label.text() == "Selected Google Sheet ID: sheet2\nLast Modified: 2022-01-02\nOwner: User2"

def test_search_google_sheets(app, uibot, mocker):
    google_sheets = [
        {"id": "sheet1", "name": "Test Sheet 1"},
        {"id": "sheet2", "name": "Test Sheet 2"},
        {"id": "sheet3", "name": "Another Sheet"}
    ]
    app.google_sheets_selector.display_google_sheets(google_sheets)
    uibot.set_text(app.google_sheets_selector.search_bar, "Test")
    assert app.google_sheets_selector.google_sheets_combo.count() == 2
    assert app.google_sheets_selector.google_sheets_combo.itemText(0) == "Test Sheet 1"
    assert app.google_sheets_selector.google_sheets_combo.itemText(1) == "Test Sheet 2"
    uibot.set_text(app.google_sheets_selector.search_bar, "Another")
    assert app.google_sheets_selector.google_sheets_combo.count() == 1
    assert app.google_sheets_selector.google_sheets_combo.itemText(0) == "Another Sheet"

def test_filter_google_sheets_by_criteria(app, uibot, mocker):
    google_sheets = [
        {"id": "sheet1", "name": "Test Sheet 1", "modifiedTime": "2022-01-01T00:00:00Z", "owner": "user1@example.com"},
        {"id": "sheet2", "name": "Test Sheet 2", "modifiedTime": "2022-02-01T00:00:00Z", "owner": "user2@example.com"},
        {"id": "sheet3", "name": "Another Sheet", "modifiedTime": "2022-03-01T00:00:00Z", "owner": "user1@example.com"}
    ]
    app.google_sheets_selector.display_google_sheets(google_sheets)
    app.google_sheets_selector.filter_google_sheets("user1@example.com")
    assert app.google_sheets_selector.google_sheets_combo.count() == 2
    assert app.google_sheets_selector.google_sheets_combo.itemText(0) == "Test Sheet 1"
    assert app.google_sheets_selector.google_sheets_combo.itemText(1) == "Another Sheet"
    app.google_sheets_selector.filter_google_sheets("2022-02-01")
    assert app.google_sheets_selector.google_sheets_combo.count() == 1
    assert app.google_sheets_selector.google_sheets_combo.itemText(0) == "Test Sheet 2"

def test_google_sheets_selector_list_google_sheets(mocker):
    mocker.patch("google_sheets_selector.authenticate", return_value="mock_credentials")
    mocker.patch("google_sheets_selector.list_google_sheets", return_value=[
        {"id": "sheet1", "name": "Test Sheet 1"},
        {"id": "sheet2", "name": "Test Sheet 2"}
    ])
    selector = GoogleSheetsSelector()
    sheets = selector.list_google_sheets()
    assert len(sheets) == 2
    assert sheets[0]["name"] == "Test Sheet 1"
    assert sheets[1]["name"] == "Test Sheet 2"

def test_google_sheets_selector_search_google_sheets(mocker):
    mocker.patch("google_sheets_selector.authenticate", return_value="mock_credentials")
    mocker.patch("google_sheets_selector.search_google_sheets", return_value[
        {"id": "sheet1", "name": "Test Sheet 1"}
    ])
    selector = GoogleSheetsSelector()
    sheets = selector.search_google_sheets("Test")
    assert len(sheets) == 1
    assert sheets[0]["name"] == "Test Sheet 1"

def test_google_sheets_selector_filter_google_sheets(mocker):
    mocker.patch("google_sheets_selector.authenticate", return_value="mock_credentials")
    mocker.patch("google_sheets_selector.filter_google_sheets", return_value[
        {"id": "sheet1", "name": "Test Sheet 1"}
    ])
    selector = GoogleSheetsSelector()
    sheets = selector.filter_google_sheets({"owner": "user1@example.com"})
    assert len(sheets) == 1
    assert sheets[0]["name"] == "Test Sheet 1"

def test_transaction_table_view_widget_display_data(qtbot):
    widget = TransactionTableViewWidget()
    qtbot.addWidget(widget)
    transactions = [
        {"date": "2022-01-01", "description": "Test Transaction 1", "amount": 100.0, "category": "Test"},
        {"date": "2022-01-02", "description": "Test Transaction 2", "amount": 200.0, "category": "Test"}
    ]
    widget.display_data(transactions)
    assert widget.model.rowCount() == 2
    assert widget.model.item(0, 0).text() == "2022-01-01"
    assert widget.model.item(0, 1).text() == "Test Transaction 1"
    assert widget.model.item(0, 2).text() == "100.0"
    assert widget.model.item(0, 3).text() == "Test"

def test_transaction_table_view_widget_sorting(qtbot):
    widget = TransactionTableViewWidget()
    qtbot.addWidget(widget)
    transactions = [
        {"date": "2022-01-01", "description": "Test Transaction 1", "amount": 100.0, "category": "Test"},
        {"date": "2022-01-02", "description": "Test Transaction 2", "amount": 200.0, "category": "Test"}
    ]
    widget.display_data(transactions)
    widget.table_view.sortByColumn(2, Qt.AscendingOrder)
    assert widget.model.item(0, 2).text() == "100.0"
    assert widget.model.item(1, 2).text() == "200.0"

def test_transaction_table_view_widget_filtering(qtbot):
    widget = TransactionTableViewWidget()
    qtbot.addWidget(widget)
    transactions = [
        {"date": "2022-01-01", "description": "Test Transaction 1", "amount": 100.0, "category": "Test"},
        {"date": "2022-01-02", "description": "Test Transaction 2", "amount": 200.0, "category": "Test"}
    ]
    widget.display_data(transactions)
    widget.proxy_model.setFilterFixedString("Test Transaction 1")
    assert widget.proxy_model.rowCount() == 1
    assert widget.proxy_model.index(0, 1).data() == "Test Transaction 1"

# Add test for end-to-end testing using pytest-qt and uibot
def test_end_to_end(app, uibot):
    transactions = [
        {"date": "2022-01-01", "description": "Test Transaction 1", "amount": 100.0, "category": "Test"},
        {"date": "2022-01-02", "description": "Test Transaction 2", "amount": 200.0, "category": "Test"}
    ]
    app.transaction_table_view_widget.display_data(transactions)
    uibot.set_text(app.search_bar, "Test Transaction 1")
    assert app.transaction_table_view_widget.proxy_model.rowCount() == 1
    assert app.transaction_table_view_widget.proxy_model.index(0, 1).data() == "Test Transaction 1"
    uibot.click_button(app.refresh_button)
    assert app.transaction_table_view_widget.model.rowCount() == 2

# Add test for mocking and patching capabilities using pytest
def test_mocking_and_patching(app, mocker):
    mocker.patch("src.widgets.google_sheets_selector.authenticate", return_value="mock_credentials")
    mocker.patch("src.widgets.google_sheets_selector.list_google_sheets", return_value=[
        {"id": "sheet1", "name": "Test Sheet 1"},
        {"id": "sheet2", "name": "Test Sheet 2"}
    ])
    app.load_data()
    assert app.google_sheets_selector.google_sheets_combo.count() == 2
    assert app.google_sheets_selector.google_sheets_combo.itemText(0) == "Test Sheet 1"
    assert app.google_sheets_selector.google_sheets_combo.itemText(1) == "Test Sheet 2"

# Add test for data-driven tests by parameterizing test functions
@pytest.mark.parametrize("search_text, expected_count", [
    ("Test Transaction 1", 1),
    ("Test Transaction 2", 1),
    ("Nonexistent Transaction", 0)
])
def test_data_driven(app, uibot, search_text, expected_count):
    transactions = [
        {"date": "2022-01-01", "description": "Test Transaction 1", "amount": 100.0, "category": "Test"},
        {"date": "2022-01-02", "description": "Test Transaction 2", "amount": 200.0, "category": "Test"}
    ]
    app.transaction_table_view_widget.display_data(transactions)
    uibot.set_text(app.search_bar, search_text)
    assert app.transaction_table_view_widget.proxy_model.rowCount() == expected_count
