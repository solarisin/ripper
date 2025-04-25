import sys
import logging
from PySide6.QtWidgets import QApplication, QMainWindow, QTableView, QVBoxLayout, QWidget, QMessageBox, QHeaderView, QLineEdit, QHBoxLayout, QPushButton, QComboBox, QLabel
from PySide6.QtCore import Qt, QSortFilterProxyModel
from PySide6.QtGui import QStandardItemModel, QStandardItem
from sheets_backend import fetch_transactions, list_google_sheets, search_google_sheets, filter_google_sheets
import matplotlib.pyplot as plt
from matplotlib.backends.backend_qt5agg import FigureCanvasQTAgg as FigureCanvas
from auth import authenticate
from database import insert_data_source, retrieve_transactions
from google_sheets_selector import GoogleSheetsSelector
from widgets.transaction_table import TransactionTableViewWidget
from widgets.main_window import MainWindow

if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec())
