import sys
import logging
from PySide6.QtWidgets import QApplication, QMainWindow, QTableView, QVBoxLayout, QWidget, QMessageBox, QHBoxLayout, QPushButton, QLabel, QComboBox, QLineEdit
from PySide6.QtCore import Qt, QSortFilterProxyModel
from PySide6.QtGui import QStandardItemModel, QStandardItem
from google_sheets_selector import GoogleSheetsSelector
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

        self.sheet_name_input = QLineEdit()
        self.sheet_name_input.setPlaceholderText("Enter sheet name")

        self.cell_range_input = QLineEdit()
        self.cell_range_input.setPlaceholderText("Enter cell range (e.g., A1:D10)")

        self.search_bar = QLineEdit()
        self.search_bar.setPlaceholderText("Search Google Sheets...")
        self.search_bar.textChanged.connect(self.filter_google_sheets)

        layout = QVBoxLayout()
        layout.addWidget(self.search_bar)
        layout.addWidget(self.google_sheets_combo)
        layout.addWidget(self.sheet_name_input)
        layout.addWidget(self.cell_range_input)
        layout.addWidget(self.metadata_label)
        layout.addWidget(self.table_view)

        container = QWidget()
        container.setLayout(layout)
        self.setCentralWidget(container)

        self.load_data()

    def load_data(self):
        try:
            google_sheets_selector = GoogleSheetsSelector()
            google_sheets = google_sheets_selector.list_google_sheets()
            self.display_google_sheets(google_sheets)
            transactions = retrieve_transactions()
            if not transactions:
                google_sheets_selector.prompt_data_source_configuration()
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
            sheet_name = self.sheet_name_input.text() or "Transactions"
            cell_range = self.cell_range_input.text() or "A:D"
            insert_data_source(selected_sheet['id'], f"{sheet_name}!{cell_range}")
            self.load_data()

    def filter_google_sheets(self, text):
        for i in range(self.google_sheets_combo.count()):
            item_text = self.google_sheets_combo.itemText(i)
            self.google_sheets_combo.setItemHidden(i, text.lower() not in item_text.lower())

if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec())
