import sys
import logging
from PySide6.QtWidgets import QMainWindow, QVBoxLayout, QWidget, QMessageBox, QHBoxLayout, QPushButton, QLineEdit, QComboBox
from widgets.google_sheets_selector import GoogleSheetsSelector
from widgets.transaction_table import TransactionTableViewWidget
from sheets_backend import list_google_sheets, fetch_transactions
from notifications import NotificationSystem

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Ripper")
        self.setGeometry(100, 100, 800, 600)

        self.google_sheets_selector = GoogleSheetsSelector()
        self.transaction_table_view_widget = TransactionTableViewWidget()

        self.search_bar = QLineEdit()
        self.search_bar.setPlaceholderText("Search transactions...")
        self.search_bar.textChanged.connect(self.transaction_table_view_widget.proxy_model.setFilterFixedString)

        self.filter_combo = QComboBox()
        self.filter_combo.addItems(["All", "Date", "Description", "Amount", "Category"])
        self.filter_combo.currentIndexChanged.connect(self.update_filter_column)

        self.refresh_button = QPushButton("Refresh")
        self.refresh_button.clicked.connect(self.load_data)

        search_layout = QHBoxLayout()
        search_layout.addWidget(self.search_bar)
        search_layout.addWidget(self.filter_combo)
        search_layout.addWidget(self.refresh_button)

        layout = QVBoxLayout()
        layout.addLayout(search_layout)
        layout.addWidget(self.transaction_table_view_widget)
        layout.addWidget(self.google_sheets_selector)

        container = QWidget()
        container.setLayout(layout)
        self.setCentralWidget(container)

        self.notification_system = NotificationSystem(self)
        self.load_data()

    def update_filter_column(self, index):
        if index == 0:
            self.transaction_table_view_widget.proxy_model.setFilterKeyColumn(-1)
        else:
            self.transaction_table_view_widget.proxy_model.setFilterKeyColumn(index - 1)

    def load_data(self):
        try:
            google_sheets = list_google_sheets(self.google_sheets_selector.credentials)
            self.google_sheets_selector.display_google_sheets(google_sheets)
            transactions = fetch_transactions(self.google_sheets_selector.credentials)
            self.transaction_table_view_widget.display_data(transactions)
        except Exception as e:
            logging.error(f"Error loading data: {e}")
            self.notification_system.show_notification(f"Failed to load data: {e}")

if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec())
