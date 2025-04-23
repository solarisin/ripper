import sys
import logging
from PySide6.QtWidgets import QApplication, QMainWindow, QTableView, QVBoxLayout, QWidget, QMessageBox, QHeaderView, QLineEdit, QHBoxLayout, QPushButton, QComboBox
from PySide6.QtCore import Qt, QSortFilterProxyModel
from PySide6.QtGui import QStandardItemModel, QStandardItem
from auth import authenticate
from data_fetcher import fetch_transactions
import matplotlib.pyplot as plt
from matplotlib.backends.backend_qt5agg import FigureCanvasQTAgg as FigureCanvas

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Bank Transaction Data Importer")
        self.setGeometry(100, 100, 1200, 800)

        self.model = QStandardItemModel()
        self.proxy_model = QSortFilterProxyModel()
        self.proxy_model.setSourceModel(self.model)
        self.proxy_model.setFilterKeyColumn(-1)
        self.proxy_model.setFilterCaseSensitivity(Qt.CaseInsensitive)

        self.table_view = QTableView()
        self.table_view.setModel(self.proxy_model)
        self.table_view.setSortingEnabled(True)
        self.table_view.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)

        self.search_bar = QLineEdit()
        self.search_bar.setPlaceholderText("Search transactions...")
        self.search_bar.textChanged.connect(self.proxy_model.setFilterFixedString)

        self.filter_combo = QComboBox()
        self.filter_combo.addItems(["All", "Date", "Description", "Amount", "Category"])
        self.filter_combo.currentIndexChanged.connect(self.update_filter_column)

        self.refresh_button = QPushButton("Refresh")
        self.refresh_button.clicked.connect(self.load_data)

        self.chart_button = QPushButton("Show Charts")
        self.chart_button.clicked.connect(self.show_charts)

        search_layout = QHBoxLayout()
        search_layout.addWidget(self.search_bar)
        search_layout.addWidget(self.filter_combo)
        search_layout.addWidget(self.refresh_button)
        search_layout.addWidget(self.chart_button)

        layout = QVBoxLayout()
        layout.addLayout(search_layout)
        layout.addWidget(self.table_view)

        container = QWidget()
        container.setLayout(layout)
        self.setCentralWidget(container)

        self.load_data()

    def update_filter_column(self, index):
        if index == 0:
            self.proxy_model.setFilterKeyColumn(-1)
        else:
            self.proxy_model.setFilterKeyColumn(index - 1)

    def load_data(self):
        try:
            credentials = authenticate()
            transactions = fetch_transactions(credentials)
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

    def show_charts(self):
        transactions = self.get_transactions_from_model()
        if not transactions:
            QMessageBox.warning(self, "No Data", "No transactions available to display charts.")
            return

        categories = {}
        for transaction in transactions:
            category = transaction["category"]
            amount = transaction["amount"]
            if category in categories:
                categories[category] += amount
            else:
                categories[category] = amount

        fig, ax = plt.subplots()
        ax.pie(categories.values(), labels=categories.keys(), autopct='%1.1f%%')
        ax.set_title("Spending by Category")

        canvas = FigureCanvas(fig)
        chart_window = QMainWindow(self)
        chart_window.setWindowTitle("Charts")
        chart_window.setCentralWidget(canvas)
        chart_window.setGeometry(150, 150, 600, 400)
        chart_window.show()

    def get_transactions_from_model(self):
        transactions = []
        for row in range(self.model.rowCount()):
            transaction = {
                "date": self.model.item(row, 0).text(),
                "description": self.model.item(row, 1).text(),
                "amount": float(self.model.item(row, 2).text()),
                "category": self.model.item(row, 3).text()
            }
            transactions.append(transaction)
        return transactions

if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec())
