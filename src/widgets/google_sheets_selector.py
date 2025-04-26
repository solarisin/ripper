import sys
import logging
from PySide6.QtWidgets import QApplication, QMainWindow, QTableView, QVBoxLayout, QWidget, QMessageBox, QHBoxLayout, QPushButton, QLabel, QComboBox, QLineEdit
from PySide6.QtCore import Qt, QSortFilterProxyModel
from PySide6.QtGui import QStandardItemModel, QStandardItem
from sheets_backend import list_google_sheets, search_google_sheets, filter_google_sheets, fetch_transactions
from auth import authenticate
from database import retrieve_transactions, insert_data_source
from notifications import NotificationSystem

class GoogleSheetsSelector(QWidget):
    def __init__(self):
        super().__init__()
        self.credentials = None
        self.google_sheets_combo = QComboBox()
        self.google_sheets_combo.currentIndexChanged.connect(self.load_selected_google_sheet)
        self.sheet_name_input = QLineEdit()
        self.sheet_name_input.setPlaceholderText("Enter sheet name")
        self.cell_range_input = QLineEdit()
        self.cell_range_input.setPlaceholderText("Enter cell range (e.g., A1:D10)")
        self.metadata_label = QLabel()
        self.search_bar = QLineEdit()
        self.search_bar.setPlaceholderText("Search Google Sheets...")
        self.search_bar.textChanged.connect(self.filter_google_sheets)
        self.notification_system = NotificationSystem(self)

        layout = QVBoxLayout()
        layout.addWidget(self.search_bar)
        layout.addWidget(self.google_sheets_combo)
        layout.addWidget(self.sheet_name_input)
        layout.addWidget(self.cell_range_input)
        layout.addWidget(self.metadata_label)
        self.setLayout(layout)

    def list_google_sheets(self):
        if not self.credentials:
            try:
                self.credentials = authenticate()
            except Exception as e:
                logging.error(f"Authentication error: {e}")
                self.notification_system.show_notification(f"Authentication error: {e}")
                return []
        return list_google_sheets(self.credentials)

    def search_google_sheets(self, query):
        if not self.credentials:
            try:
                self.credentials = authenticate()
            except Exception as e:
                logging.error(f"Authentication error: {e}")
                self.notification_system.show_notification(f"Authentication error: {e}")
                return []
        return search_google_sheets(self.credentials, query)

    def filter_google_sheets(self, criteria):
        if not self.credentials:
            try:
                self.credentials = authenticate()
            except Exception as e:
                logging.error(f"Authentication error: {e}")
                self.notification_system.show_notification(f"Authentication error: {e}")
                return []
        return filter_google_sheets(self.credentials, criteria)

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
            self.parent().load_data()
