import sys
import pytest
from PySide6.QtWidgets import QApplication, QFileDialog, QLabel, QMainWindow, QMessageBox
from ui import MainWindow

@pytest.fixture
def app(qtbot):
    test_app = QApplication(sys.argv)
    window = MainWindow()
    qtbot.addWidget(window)
    return window

def test_display_data(app, qtbot):
    transactions = [
        {"date": "2022-01-01", "description": "Test Transaction 1", "amount": 100.0, "category": "Test"},
        {"date": "2022-01-02", "description": "Test Transaction 2", "amount": 200.0, "category": "Test"}
    ]
    app.display_data(transactions)
    assert app.model.rowCount() == 2
    assert app.model.item(0, 0).text() == "2022-01-01"
    assert app.model.item(0, 1).text() == "Test Transaction 1"
    assert app.model.item(0, 2).text() == "100.0"
    assert app.model.item(0, 3).text() == "Test"

def test_advanced_table_features(app, qtbot):
    transactions = [
        {"date": "2022-01-01", "description": "Test Transaction 1", "amount": 100.0, "category": "Test"},
        {"date": "2022-01-02", "description": "Test Transaction 2", "amount": 200.0, "category": "Test"}
    ]
    app.display_data(transactions)
    app.search_bar.setText("Test Transaction 1")
    assert app.proxy_model.rowCount() == 1
    assert app.proxy_model.index(0, 1).data() == "Test Transaction 1"

def test_dashboard_view(app, qtbot):
    transactions = [
        {"date": "2022-01-01", "description": "Test Transaction 1", "amount": 100.0, "category": "Test"},
        {"date": "2022-01-02", "description": "Test Transaction 2", "amount": 200.0, "category": "Test"}
    ]
    app.display_data(transactions)
    app.show_charts()
    assert app.findChild(QMainWindow, "Charts") is not None

def test_user_notifications_for_errors(app, qtbot, mocker):
    mocker.patch("ui.authenticate", side_effect=Exception("Test Error"))
    with qtbot.waitSignal(app.load_data, timeout=1000):
        app.load_data()
    assert app.findChild(QMessageBox, "Error") is not None

def test_file_picker_dialog(app, qtbot, mocker):
    mocker.patch("ui.QFileDialog.getOpenFileName", return_value=("test_sheet.gsheet", None))
    app.open_file_picker()
    assert app.metadata_label.text() == "Selected file: test_sheet.gsheet"

def test_display_metadata(app, qtbot, mocker):
    mocker.patch("ui.QFileDialog.getOpenFileName", return_value=("test_sheet.gsheet", None))
    app.open_file_picker()
    assert app.metadata_label.text() == "Selected file: test_sheet.gsheet"
    # Add additional assertions for metadata such as last modified date and owner

def test_filter_google_sheets(app, qtbot, mocker):
    mocker.patch("ui.QFileDialog.getOpenFileName", return_value=("test_sheet.gsheet", None))
    app.open_file_picker()
    assert app.metadata_label.text() == "Selected file: test_sheet.gsheet"
    # Add additional assertions to ensure only Google Sheets are displayed

def test_maintain_separate_datasets(app, qtbot, mocker):
    transactions1 = [
        {"date": "2022-01-01", "description": "Test Transaction 1", "amount": 100.0, "category": "Test"}
    ]
    transactions2 = [
        {"date": "2022-01-02", "description": "Test Transaction 2", "amount": 200.0, "category": "Test"}
    ]
    app.display_data(transactions1)
    assert app.model.rowCount() == 1
    assert app.model.item(0, 0).text() == "2022-01-01"
    app.display_data(transactions2)
    assert app.model.rowCount() == 1
    assert app.model.item(0, 0).text() == "2022-01-02"
