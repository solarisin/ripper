import sys
import pytest
from PySide6.QtWidgets import QApplication
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
