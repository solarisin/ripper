import sys
import logging
from PySide6.QtWidgets import QApplication, QMainWindow, QTableView, QVBoxLayout, QWidget, QMessageBox, QHBoxLayout, QPushButton, QLabel, QComboBox
from PySide6.QtCore import Qt, QSortFilterProxyModel
from PySide6.QtGui import QStandardItemModel, QStandardItem
from auth import authenticate, list_google_sheets, prompt_data_source_configuration
from data_fetcher import fetch_transactions
from database import retrieve_transactions, insert_data_source

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Ripper")
        self.setGeometry(100, 100, 800, 600)

        self.model = QStandardItemModel()
        self.proxy_model = QSortFilterProxyModel()
        self.proxy_model.setSourceModel(self.model)
        self.proxy_model.setFilterKeyColumn(-1)
        self.proxy_model.setFilterCaseSensitivity(Qt.CaseInsensitive)

        self.table_view = QTableView()
        self.table_view.setModel(self.proxy_model)
        self.table_view.setSortingEnabled(True)

        self.metadata_label = QLabel()

        self.google_sheets_combo = QComboBox()
        self.google_sheets_combo.currentIndexChanged.connect(self.load_selected_google_sheet)

        layout = QVBoxLayout()
        layout.addWidget(self.google_sheets_combo)
        layout.addWidget(self.metadata_label)
        layout.addWidget(self.table_view)

        container = QWidget()
        container.setLayout(layout)
        self.setCentralWidget(container)

        self.load_data()

    def load_data(self):
        try:
            credentials = authenticate()
            google_sheets = list_google_sheets(credentials)
            self.display_google_sheets(google_sheets)
            transactions = retrieve_transactions()
            if not transactions:
                prompt_data_source_configuration()
            self.display_data(transactions)
        except Exception as e:
            logging.error(f"Error loading data: {e}")
            QMessageBox.critical(self, "Error", f"Failed to load data: {e}")

    def display_data(self, transactions):
        self.model.clear()
        self.model.setHorizontalHeaderLabels(["Date", "Description", "Amount", "Category"])

        for transaction in transactions:
            date_item = QStandardItem(transaction["date"])
            description_item = QStandardItem(transaction["description"])
            amount_item = QStandardItem(str(transaction["amount"]))
            category_item = QStandardItem(transaction["category"])

            self.model.appendRow([date_item, description_item, amount_item, category_item])

    def display_google_sheets(self, google_sheets):
        self.google_sheets_combo.clear()
        for sheet in google_sheets:
            self.google_sheets_combo.addItem(sheet["name"], sheet)

    def load_selected_google_sheet(self, index):
        selected_sheet = self.google_sheets_combo.itemData(index)
        if selected_sheet:
            self.metadata_label.setText(f"Selected Google Sheet ID: {selected_sheet['id']}\nLast Modified: {selected_sheet.get('last_modified', 'N/A')}\nOwner: {selected_sheet.get('owner', 'N/A')}")
            insert_data_source(selected_sheet['id'], "Transactions!A:D")
            self.load_data()

if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec())
