from PySide6.QtWidgets import QWidget, QVBoxLayout, QTableView, QHeaderView
from PySide6.QtCore import Qt, QSortFilterProxyModel
from PySide6.QtGui import QStandardItemModel, QStandardItem

class TransactionTableViewWidget(QWidget):
    def __init__(self):
        super().__init__()
        self.model = QStandardItemModel()
        self.proxy_model = QSortFilterProxyModel()
        self.proxy_model.setSourceModel(self.model)
        self.proxy_model.setFilterKeyColumn(-1)
        self.proxy_model.setFilterCaseSensitivity(Qt.CaseInsensitive)

        self.table_view = QTableView()
        self.table_view.setModel(self.proxy_model)
        self.table_view.setSortingEnabled(True)
        self.table_view.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)

        layout = QVBoxLayout()
        layout.addWidget(self.table_view)
        self.setLayout(layout)

    def display_data(self, transactions):
        self.model.clear()
        self.model.setHorizontalHeaderLabels(["Date", "Description", "Amount", "Category"])

        for transaction in transactions:
            date_item = QStandardItem(transaction["date"])
            description_item = QStandardItem(transaction["description"])
            amount_item = QStandardItem(str(transaction["amount"]))
            category_item = QStandardItem(transaction["category"])

            self.model.appendRow([date_item, description_item, amount_item, category_item])

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
