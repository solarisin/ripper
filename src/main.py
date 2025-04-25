import sys
import logging
from PySide6.QtWidgets import QApplication, QMainWindow, QVBoxLayout, QWidget, QMessageBox, QHBoxLayout, QPushButton, QLineEdit, QComboBox
from google_sheets_selector import GoogleSheetsSelector
from widgets.transaction_table import TransactionTableViewWidget
from widgets.main_window import MainWindow
from database import retrieve_transactions
from sheets_backend import list_google_sheets, fetch_transactions

if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec())
