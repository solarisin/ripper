from PySide6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton
from PySide6.QtCore import Qt, QTimer

class NotificationSystem(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setStyleSheet("""
            QWidget {
                background-color: #333;
                color: #fff;
                border-radius: 10px;
                padding: 10px;
            }
            QLabel {
                font-size: 14px;
            }
            QPushButton {
                background-color: #555;
                color: #fff;
                border: none;
                padding: 5px 10px;
                border-radius: 5px;
            }
            QPushButton:hover {
                background-color: #777;
            }
        """)

        self.layout = QVBoxLayout()
        self.setLayout(self.layout)

        self.timer = QTimer(self)
        self.timer.timeout.connect(self.hide_notification)

    def show_notification(self, message, duration=5000):
        self.clear_layout()

        label = QLabel(message)
        self.layout.addWidget(label)

        button_layout = QHBoxLayout()
        dismiss_button = QPushButton("Dismiss")
        dismiss_button.clicked.connect(self.hide_notification)
        button_layout.addWidget(dismiss_button)
        self.layout.addLayout(button_layout)

        self.adjustSize()
        self.show()

        self.timer.start(duration)

    def hide_notification(self):
        self.hide()
        self.timer.stop()

    def clear_layout(self):
        while self.layout.count():
            child = self.layout.takeAt(0)
            if child.widget():
                child.widget().deleteLater()
