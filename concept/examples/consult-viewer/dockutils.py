from abc import ABC, ABCMeta, abstractmethod
from PySide6.QtWidgets import QWidget
from PySide6.QtWidgets import QSizePolicy
import PySide6QtAds as QtAds
from typing import Callable


class QABCMeta(ABCMeta, type(QWidget)):
    pass


class DockableView(ABC, metaclass=QABCMeta):
    @abstractmethod
    def initial_expanded_size(self) -> int:
        pass


def create_and_dock_view(parent: QWidget,
                         dockmgr: QtAds.CDockManager,
                         title: str,
                         area: QtAds.DockWidgetArea | QtAds.ads.SideBarLocation,
                         view: (QWidget, DockableView)) -> (
        QtAds.CDockWidget,
        QtAds.CDockContainerWidget):
    dock = QtAds.CDockWidget(title, parent)
    view.setParent(dock)
    dock.setWidget(view)
    # dock.setMinimumSizeHintMode(QtAds.CDockWidget.MinimumSizeHintFromDockWidget)
    dock.setMinimumSizeHintMode(QtAds.CDockWidget.MinimumSizeHintFromContent)
    if isinstance(area, QtAds.DockWidgetArea):
        container = dockmgr.addDockWidget(area, dock)
    else:
        container = dockmgr.addAutoHideDockWidget(area, dock)
        container.setSize(view.initial_expanded_size())
        container.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
    return dock, container
