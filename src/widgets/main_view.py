from PySide6.QtWidgets import QMainWindow, QDockWidget, QWidget, QVBoxLayout, QTableWidget, QTableWidgetItem, QToolBar
from PySide6.QtCore import Qt
from PySide6.QtGui import QAction
import PySide6QtAds as QtAds

class MainView(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Ripper - Transaction Viewer")
        self.dock_manager = QtAds.CDockManager(self)

        self.init_ui()

    def init_ui(self):
        self.create_dockable_views()
        self.create_menu()
        self.create_toolbar()

    def create_dockable_views(self):
        self.transaction_tables = []

    def create_transaction_table(self):
        table_widget = QTableWidget()
        table_widget.setColumnCount(4)
        table_widget.setHorizontalHeaderLabels(["Date", "Description", "Amount", "Category"])
        return table_widget

    def create_menu(self):
        menu_bar = self.menuBar()
        file_menu = menu_bar.addMenu("File")

        exit_action = QAction("Exit", self)
        exit_action.triggered.connect(self.close)
        file_menu.addAction(exit_action)

    def create_toolbar(self):
        toolbar = QToolBar("Main Toolbar")
        self.addToolBar(toolbar)

        add_table_action = QAction("Add Transaction Table", self)
        add_table_action.triggered.connect(self.add_transaction_table)
        toolbar.addAction(add_table_action)

    def add_transaction_table(self):
        table_widget = self.create_transaction_table()
        dock_widget = QDockWidget(f"Transaction Table {len(self.transaction_tables) + 1}", self)
        dock_widget.setWidget(table_widget)
        self.addDockWidget(Qt.LeftDockWidgetArea, dock_widget)
        self.transaction_tables.append(table_widget)

    def display_transactions(self, transactions):
        for table_widget in self.transaction_tables:
            table_widget.setRowCount(len(transactions))
            for row, transaction in enumerate(transactions):
                table_widget.setItem(row, 0, QTableWidgetItem(transaction['date']))
                table_widget.setItem(row, 1, QTableWidgetItem(transaction['description']))
                table_widget.setItem(row, 2, QTableWidgetItem(str(transaction['amount'])))
                table_widget.setItem(row, 3, QTableWidgetItem(transaction['category']))
