import sys
import logging

from PySide6.QtCore import QSettings
from PySide6.QtWidgets import QSizePolicy, QApplication, QMainWindow, QMessageBox, QInputDialog
from PySide6.QtGui import QAction

import PySide6QtAds as QtAds

from parametertable import ParameterTableView
from options import OptionsView
from statuslog import StatusLogView
from dockutils import DockableView, create_and_dock_view


# Subclass QMainWindow to customize your application's main window
class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()

        # init vars
        self._store_perspective_act = None
        self._delete_perspective_act = None
        self._quit_act = None
        self._about_act = None
        self._about_qt_act = None

        self._file_menu = None
        self._view_menu = None
        self._windows_menu = None
        self._help_menu = None

        self._table_view = None
        self._log_view = None
        self._options_view = None

        self._global_settings_file = QSettings("cv_settings.cfg", QSettings.Format.IniFormat)

        # setup dock manager
        QtAds.CDockManager.setConfigFlag(QtAds.CDockManager.FocusHighlighting, True)
        QtAds.CDockManager.setConfigFlag(QtAds.CDockManager.DockAreaHasTabsMenuButton, False)
        QtAds.CDockManager.setConfigFlag(QtAds.CDockManager.OpaqueSplitterResize, True)
        QtAds.CDockManager.setAutoHideConfigFlags(QtAds.CDockManager.DefaultAutoHideConfig)
        # QtAds.CDockManager.setAutoHideConfigFlag(QtAds.CDockManager.AutoHideShowOnMouseOver, True)
        QtAds.CDockManager.setAutoHideConfigFlag(QtAds.CDockManager.AutoHideCloseButtonCollapsesDock, True)
        QtAds.CDockManager.setAutoHideConfigFlag(QtAds.CDockManager.AutoHideHasMinimizeButton, False)
        self._dock_mgr = QtAds.CDockManager(self)

        # load perspectives
        self._dock_mgr.loadPerspectives(self._global_settings_file)
        self._current_perspective = ""

        # setup main window
        self.create_actions()
        self.create_menus()
        self.create_status_bar()
        self.create_dock_windows()

        # connect options update to table view
        self._options_view.parameterSelectionChanged.connect(self._table_view.parameters_changed)

        self.setWindowTitle("Consult Viewer")
        self.restore_window_state()

        logging.debug("Main window initialized.")

    # overrides

    def closeEvent(self, event):
        self.save_window_state()

    # methods

    def about(self):
        QMessageBox.about(self, "About Dock Widgets",
                          "The <b>Dock Widgets</b> example demonstrates how to use "
                          "Qt's dock widgets. You can enter your own text, click a "
                          "customer to add a customer name and address, and click "
                          "standard paragraphs to add them.")

    def create_actions(self):
        self._quit_act = QAction("&Quit",
                                 parent=self,
                                 shortcut="Ctrl+Q",
                                 statusTip="Quit the application",
                                 triggered=self.close)

        self._about_act = QAction("&About",
                                  parent=self,
                                  statusTip="Show the application's About box",
                                  triggered=self.about)

        self._about_qt_act = QAction("About &Qt", parent=self,
                                     statusTip="Show the Qt library's About box",
                                     triggered=QApplication.instance().aboutQt)

        self._store_perspective_act = QAction("Save",
                                              parent=self,
                                              statusTip="Save the current perspective",
                                              triggered=self.store_perspective)

        self._delete_perspective_act = QAction("Delete",
                                               parent=self,
                                               statusTip="Remove a perspective",
                                               triggered=self.delete_perspective)

    def create_menus(self):
        self._file_menu = self.menuBar().addMenu("&File")
        self._file_menu.addAction(self._quit_act)
        self._view_menu = self.menuBar().addMenu("&View")
        perspective_menu = self._view_menu.addMenu("Perspectives")

        def refresh_perspective_actions():
            def handle_perspective_selected(name):
                self._current_perspective = name
                logging.info(f"Loading perspective '{name}'")
                self._dock_mgr.openPerspective(name)
            perspective_menu.clear()
            for perspective_name in self._dock_mgr.perspectiveNames():
                action = QAction(perspective_name, self, statusTip=f"Load the '{perspective_name}' perspective")
                action.triggered.connect(lambda checked, n=perspective_name: handle_perspective_selected(n))
                perspective_menu.addAction(action)
            perspective_menu.addSeparator()
            perspective_menu.addAction(self._store_perspective_act)
            perspective_menu.addAction(self._delete_perspective_act)

        perspective_menu.aboutToShow.connect(refresh_perspective_actions)
        self._view_menu.addSeparator()
        self._windows_menu = self._view_menu.addMenu("Windows")

        self.menuBar().addSeparator()

        self._help_menu = self.menuBar().addMenu("&Help")
        self._help_menu.addAction(self._about_act)
        self._help_menu.addAction(self._about_qt_act)

    def create_status_bar(self):
        self.statusBar().showMessage("Ready")

    def save_window_state(self):
        '''
        Saves the dock manager state and the main window geometry
        '''
        self._global_settings_file.setValue("mainview/geometry", self.saveGeometry())
        self._global_settings_file.setValue("mainview/state", self.saveState())
        self._global_settings_file.setValue("mainview/dockingstate", self._dock_mgr.saveState())

    def restore_window_state(self):
        '''
        Restores the dock manager and window geometry states
        '''
        geom = self._global_settings_file.value("mainview/geometry")
        if geom is not None:
            self.restoreGeometry(geom)
        else:
            self.setGeometry(100, 100, 800, 600)

        state = self._global_settings_file.value("mainview/state")
        if state is not None:
            self.restoreState(state)

        state = self._global_settings_file.value("mainview/dockingstate")
        if state is not None:
            self._dock_mgr.restoreState(state)

    def store_perspective(self):
        name, entered = QInputDialog.getText(self, "Save Perspective", "Enter unique name:")
        if not entered or len(name) == 0:
            return

        self._dock_mgr.addPerspective(name)
        logging.info(f"Added perspective '{name}'")
        self._dock_mgr.savePerspectives(self._global_settings_file)

    def delete_perspective(self):
        perspective_names = self._dock_mgr.perspectiveNames()
        if len(perspective_names) <= 1:
            return

        try:
            current = perspective_names.index(self._current_perspective)
        except ValueError:
            current = 0

        selected, ok = QInputDialog.getItem(self, "Delete Perspective", "Select perspective to delete:",
                                            self._dock_mgr.perspectiveNames(),
                                            current=current,
                                            editable=False)
        if ok:
            self._dock_mgr.removePerspective(selected)
            logging.info(f"Removed perspective '{selected}'")
            self._dock_mgr.savePerspectives(self._global_settings_file)

    def create_dock_windows(self):
        # set the table view as the central widget (the main view)
        table_dock = QtAds.CDockWidget("Parameter Table", self)
        self._table_view = ParameterTableView(table_dock)
        table_dock.setWidget(self._table_view)
        table_dock.setMinimumSizeHintMode(QtAds.CDockWidget.MinimumSizeHintFromContent)
        self._dock_mgr.setCentralWidget(table_dock)

        # create the auto-hide dockable views
        self._options_view = OptionsView()
        options_dock_view, options_dock_container = create_and_dock_view(self, self._dock_mgr, "Options",
                                                                         QtAds.SideBarRight,
                                                                         self._options_view)
        self._log_view = StatusLogView()
        statuslog_dock_view, statuslog_dock_container = create_and_dock_view(self, self._dock_mgr, "Status Log",
                                                                             QtAds.BottomDockWidgetArea,
                                                                             self._log_view)
        self._windows_menu.addAction(options_dock_view.toggleViewAction())
        self._windows_menu.addAction(statuslog_dock_view.toggleViewAction())


def main():
    app = QApplication(sys.argv)

    logging.basicConfig(
        format="%(asctime)s %(levelname)s [%(filename)s:%(lineno)s] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
        level=logging.DEBUG)

    def handle_exception(exc_type, exc_value, exc_traceback):
        if issubclass(exc_type, KeyboardInterrupt):
            sys.__excepthook__(exc_type, exc_value, exc_traceback)
            return
        logging.critical("Uncaught exception", exc_info=(exc_type, exc_value, exc_traceback))
    sys.excepthook = handle_exception

    window = MainWindow()
    window.show()

    app.exec()

# Entrypoint
if __name__ == "__main__":
    main()
