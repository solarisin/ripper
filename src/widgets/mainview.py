import logging
import sys

from PySide6.QtCore import QFile, Qt, QTextStream, QSize
from PySide6.QtGui import QAction, QFont, QIcon, QKeySequence
from PySide6.QtPrintSupport import QPrintDialog, QPrinter
from PySide6.QtWidgets import (QApplication, QDialog, QDockWidget,
                               QFileDialog, QMainWindow,
                               QMessageBox, QWidget, QGridLayout)

import res.images.tools
from src.widgets.auth_view import AuthView


class MainView(QMainWindow):
    def __init__(self):
        super().__init__()

        self.log = logging.getLogger('mainview')

        self._file_menu = None
        self._edit_menu = None
        self._view_menu = None
        self._oauth_menu = None
        self._help_menu = None

        self._file_tool_bar = None
        self._edit_tool_bar = None

        self._register_oauth_act = None
        self._new_source_act = None
        self._save_act = None
        self._print_act = None
        self._undo_act = None
        self._quit_act = None
        self._about_act = None
        self._about_qt_act = None

        self.setWindowTitle("ripper")
        self.dockNestingEnabled = True
        self.resize(QSize(640, 480))

        self.create_actions()
        self.create_menus()
        self.create_tool_bars()
        self.create_status_bar()

        # Ensure we have a central widget, then hide it
        grid_layout = QGridLayout()
        widget = QWidget()
        widget.setLayout(grid_layout)
        self.setCentralWidget(widget)
        self.centralWidget().hide()

    def create_menus(self):
        self._file_menu = self.menuBar().addMenu("&File")
        self._file_menu.addAction(self._new_source_act)
        self._file_menu.addAction(self._save_act)
        self._file_menu.addAction(self._print_act)
        self._file_menu.addSeparator()
        self._file_menu.addAction(self._quit_act)

        self._edit_menu = self.menuBar().addMenu("&Edit")
        self._edit_menu.addAction(self._undo_act)

        self._view_menu = self.menuBar().addMenu("&View")

        self._oauth_menu = self.menuBar().addMenu("&OAuth")
        self._oauth_menu.addAction(self._register_oauth_act)

        self.menuBar().addSeparator()

        self._help_menu = self.menuBar().addMenu("&Help")
        self._help_menu.addAction(self._about_act)
        self._help_menu.addAction(self._about_qt_act)

    def create_tool_bars(self):
        self._file_tool_bar = self.addToolBar("File")
        self._file_tool_bar.addAction(self._new_source_act)
        self._file_tool_bar.addAction(self._save_act)
        self._file_tool_bar.addAction(self._print_act)

        self._edit_tool_bar = self.addToolBar("Edit")
        self._edit_tool_bar.addAction(self._undo_act)

    def create_status_bar(self):
        self.statusBar().showMessage("Ready")


    ####### Actions #####################################################################

    # noinspection PyArgumentList
    def create_actions(self):
        # TODO add google oauth-specific icon
        icon = QIcon.fromTheme('document-new', QIcon(':/res/new.png'))
        self._register_oauth_act = QAction(icon, "Register/Update OAuth Client",
                                           self, statusTip="Register or update the target Google OAuth Client",
                                           triggered=self.register_oauth)

        icon = QIcon.fromTheme('document-new', QIcon(':/res/new.png'))
        self._new_source_act = QAction(icon, "&New Source",
                                       self, shortcut=QKeySequence.New,
                                       statusTip="Import a new source sheet",
                                       triggered=self.new_source)


        icon = QIcon.fromTheme('document-save', QIcon(':/res/save.png'))
        self._save_act = QAction(icon, "&Save...", self,
                                 shortcut=QKeySequence.Save,
                                 statusTip="Save the current spreadsheet", triggered=self.save)

        icon = QIcon.fromTheme('document-print', QIcon(':/res/print.png'))
        self._print_act = QAction(icon, "&Print...", self,
                                  shortcut=QKeySequence.Print,
                                  statusTip="Print the current spreadsheet",
                                  triggered=self.print_)

        icon = QIcon.fromTheme('edit-undo', QIcon(':/res/undo.png'))
        self._undo_act = QAction(icon, "&Undo", self,
                                 shortcut=QKeySequence.Undo,
                                 statusTip="Undo the last editing action", triggered=self.undo)

        self._quit_act = QAction("&Quit", self, shortcut="Ctrl+Q",
                                 statusTip="Quit the application", triggered=self.close)

        self._about_act = QAction("&About", self,
                                  statusTip="About ripper",
                                  triggered=self.about)

        self._about_qt_act = QAction("About &Qt", self,
                                     statusTip="About Qt",
                                     triggered=QApplication.instance().aboutQt)

    # User is prompted to supply an OAuth client and authenticate with Google API
    def register_oauth(self):
        self.log.debug("Register OAuth selected")
        self.show_auth_view()

    def new_source(self):
        self.log.debug("New source selected")

    def show_auth_view(self):
        """Show the authentication view as a dialog"""
        self.auth_dialog = QDialog(self)
        self.auth_dialog.setWindowTitle("Google API Authentication")
        self.auth_dialog.setMinimumWidth(500)

        # Create auth view
        auth_view = AuthView(self.auth_dialog)
        auth_view.oauth_client_registered.connect(self.on_oauth_client_registered)

        # Set layout
        layout = QGridLayout(self.auth_dialog)
        layout.addWidget(auth_view)
        self.auth_dialog.setLayout(layout)

        # Show dialog
        self.auth_dialog.exec()

    def print_(self):
        document = self._text_edit.document()
        printer = QPrinter()

        dlg = QPrintDialog(printer, self)
        if dlg.exec() != QDialog.Accepted:
            return

        document.print_(printer)

        self.statusBar().showMessage("Ready", 2000)

    def save(self):
        dialog = QFileDialog(self, "Choose a file name")
        dialog.setMimeTypeFilters(['text/html'])
        dialog.setAcceptMode(QFileDialog.AcceptSave)
        dialog.setDefaultSuffix('csv')
        if dialog.exec() != QDialog.Accepted:
            return

        filename = dialog.selectedFiles()[0]
        file = QFile(filename)
        if not file.open(QFile.WriteOnly | QFile.Text):
            reason = file.errorString()
            QMessageBox.warning(self, "Dock Widgets",
                                f"Cannot write file {filename}:\n{reason}.")
            return

        out = QTextStream(file)
        with QApplication.setOverrideCursor(Qt.WaitCursor):
            out << self._text_edit.toPlainText()

        self.statusBar().showMessage(f"Saved '{filename}'", 2000)

    def undo(self):
        self.log.debug("Undo selected")


    def about(self):
        QMessageBox.about(self, "About ripper",
                          "This is ripper")


    ####### Slots #######################################################################

    # Slot to be called when the user successfully selects or updates the target OAuth client
    def on_oauth_client_registered(self):
        """Handle user update of target oauth client"""
        self.log.debug("User configured OAuth client credentials")

        # Close the auth dialog
        if hasattr(self, 'auth_dialog') and self.auth_dialog:
            self.auth_dialog.accept()

        # TODO: Update Toolbar/Menu to enable options only available after an OAuth client is configured

        # For now, just show a message that authentication was successful
        QMessageBox.information(self, "OAuth Client Update Successful",
                               "OAuth Client credentials successfully updated and stored securely")
