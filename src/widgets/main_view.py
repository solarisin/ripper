import logging
import sys

from PySide6.QtCore import QDate, QFile, Qt, QTextStream, QSize
from PySide6.QtGui import (QAction, QFont, QIcon, QKeySequence,
                           QTextCharFormat, QTextCursor, QTextTableFormat)
from PySide6.QtPrintSupport import QPrintDialog, QPrinter
from PySide6.QtWidgets import (QApplication, QDialog, QDockWidget,
                               QFileDialog, QListWidget, QMainWindow,
                               QMessageBox, QTextEdit, QWidget, QGridLayout, QSizePolicy)

import res.images.tools


class MainView(QMainWindow):
    def __init__(self):
        super().__init__()

        self.log = logging.getLogger('mainview')

        self._file_menu = None
        self._edit_menu = None
        self._view_menu = None
        self._help_menu = None

        self._file_tool_bar = None
        self._edit_tool_bar = None

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

    # TODO action to be taken upon clicking 'New source'
    # User should be prompted to select a google sheet from their google drive
    def new_source(self):
        self.log.debug("New source selected")

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

    # TODO slot to be called when the user successfully selects a new datasource
    def source_selected(self):
        self.blockSignals(True)
        self.centralWidget().hide()
        self.create_dock_windows()
        # self.new_sheet()
        self.blockSignals(False)