"""Dashboard editor view."""

from typing import Optional

from loguru import logger
from PySide6.QtCore import QMimeData, QObject, QSize, Qt, Signal
from PySide6.QtGui import QDrag, QDropEvent, QMouseEvent
from PySide6.QtWidgets import (
    QAbstractItemView,
    QFrame,
    QHBoxLayout,
    QLabel,
    QListView,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QSizePolicy,
    QSplitter,
    QStyle,
    QVBoxLayout,
    QWidget,
)

from ripper.rippergui.dashboard.models import (
    WIDGET_REGISTRY,
    BaseWidget,
    Dashboard,
    WidgetConfig,
)
from ripper.rippergui.dashboard.models.widget_types import WidgetType


class WidgetList(QListWidget):
    """Custom QListWidget that supports drag operations for widget types."""

    def startDrag(self, supportedActions: Qt.DropAction) -> None:
        """Start drag operation with widget type data."""
        item = self.currentItem()
        if not item:
            return

        widget_type = item.data(Qt.ItemDataRole.UserRole)
        if not widget_type:
            return

        # Create drag operation
        drag = QDrag(self)
        mime_data = QMimeData()
        mime_data.setData("application/x-widget-type", widget_type.value.encode())
        drag.setMimeData(mime_data)

        # Set drag pixmap to the item's icon
        icon = item.icon()
        if not icon.isNull():
            drag.setPixmap(icon.pixmap(32, 32))

        # Execute drag
        drag.exec(Qt.DropAction.CopyAction)


class WidgetPalette(QFrame):
    """Widget palette that displays available widgets to add to the dashboard."""

    def __init__(self, parent: Optional[QWidget] = None):
        """Initialize the widget palette."""
        super().__init__(parent)
        self.setObjectName("widgetPalette")
        self.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Expanding)
        self.setMinimumWidth(200)
        self.setMaximumWidth(300)
        self.setFrameStyle(QFrame.Shape.StyledPanel | QFrame.Shadow.Sunken)

        layout = QVBoxLayout()
        layout.setContentsMargins(5, 5, 5, 5)
        layout.setSpacing(5)
        self.setLayout(layout)

        # Title
        title = QLabel("Widgets")
        title.setStyleSheet("font-weight: bold; font-size: 14px;")
        layout.addWidget(title)

        # Widget list
        self.widget_list = WidgetList()
        self.widget_list.setViewMode(QListWidget.ViewMode.IconMode)
        self.widget_list.setIconSize(QSize(48, 48))
        self.widget_list.setMovement(QListView.Movement.Static)
        self.widget_list.setResizeMode(QListView.ResizeMode.Adjust)
        self.widget_list.setDragDropMode(QAbstractItemView.DragDropMode.DragOnly)
        self.widget_list.setDefaultDropAction(Qt.DropAction.CopyAction)
        self.widget_list.setSpacing(5)

        # Add widget items
        # Basic widgets
        self._add_widget_item("Line Chart", WidgetType.LINE_CHART, "chart-line")
        self._add_widget_item("Bar Chart", WidgetType.BAR_CHART, "chart-bar")
        self._add_widget_item("Pie Chart", WidgetType.PIE_CHART, "chart-pie")
        self._add_widget_item("Data Table", WidgetType.DATA_TABLE, "table")
        self._add_widget_item("KPI", WidgetType.KPI, "chart-gantt")
        self._add_widget_item("Gauge", WidgetType.GAUGE, "tachometer-alt")

        # Add a separator
        separator = QFrame()
        separator.setFrameShape(QFrame.Shape.HLine)
        separator.setFrameShadow(QFrame.Shadow.Sunken)
        widget_layout = self.layout()
        if widget_layout is not None:
            widget_layout.addWidget(separator)

        # Financial widgets section
        finance_label = QLabel("Financial")
        finance_label.setStyleSheet("font-weight: bold; margin-top: 10px;")
        widget_layout = self.layout()
        if widget_layout is not None:
            widget_layout.addWidget(finance_label)

        # Financial widgets
        self._add_widget_item("Spending Trend", WidgetType.SPENDING_TREND, "chart-line")
        self._add_widget_item("Category Breakdown", WidgetType.CATEGORY_BREAKDOWN, "chart-pie")
        self._add_widget_item("Budget vs Actual", WidgetType.BUDGET_VS_ACTUAL, "balance-scale")
        self._add_widget_item("Top Expenses", WidgetType.TOP_EXPENSES, "list-ol")

        layout.addWidget(self.widget_list)

    def _add_widget_item(self, name: str, widget_type: WidgetType, icon_name: str) -> None:
        """Add a widget item to the palette.

        Args:
            name: Display name of the widget
            widget_type: Widget type
            icon_name: Name of the icon to use
        """
        item = QListWidgetItem(name)
        item.setData(Qt.ItemDataRole.UserRole, widget_type)

        # Map widget types to appropriate Qt standard icons
        icon_mapping = {
            WidgetType.LINE_CHART: QStyle.StandardPixmap.SP_FileDialogDetailedView,
            WidgetType.BAR_CHART: QStyle.StandardPixmap.SP_FileDialogListView,
            WidgetType.PIE_CHART: QStyle.StandardPixmap.SP_DialogYesButton,
            WidgetType.DATA_TABLE: QStyle.StandardPixmap.SP_FileDialogInfoView,
            WidgetType.KPI: QStyle.StandardPixmap.SP_DesktopIcon,
            WidgetType.GAUGE: QStyle.StandardPixmap.SP_ComputerIcon,
            WidgetType.SPENDING_TREND: QStyle.StandardPixmap.SP_FileDialogDetailedView,
            WidgetType.CATEGORY_BREAKDOWN: QStyle.StandardPixmap.SP_DialogYesButton,
            WidgetType.BUDGET_VS_ACTUAL: QStyle.StandardPixmap.SP_DialogApplyButton,
            WidgetType.TOP_EXPENSES: QStyle.StandardPixmap.SP_FileDialogListView,
            WidgetType.NET_WORTH: QStyle.StandardPixmap.SP_DriveHDIcon,
            WidgetType.SAVINGS_GOAL: QStyle.StandardPixmap.SP_DialogSaveButton,
            WidgetType.INCOME_VS_EXPENSE: QStyle.StandardPixmap.SP_MediaPlay,
        }

        # Get the appropriate icon
        icon_pixmap = icon_mapping.get(widget_type, QStyle.StandardPixmap.SP_FileIcon)
        icon = self.style().standardIcon(icon_pixmap)
        item.setIcon(icon)

        item.setSizeHint(QSize(80, 80))
        self.widget_list.addItem(item)


class DashboardCanvas(QFrame):
    """Canvas for arranging dashboard widgets."""

    def __init__(self, dashboard: Dashboard, parent: Optional[QWidget] = None):
        """Initialize the dashboard canvas.

        Args:
            dashboard: Dashboard model
            parent: Parent widget
        """
        super().__init__(parent)
        self.dashboard = dashboard
        self.signals = DashboardSignals()
        self.setAcceptDrops(True)
        self.setFrameStyle(QFrame.Shape.StyledPanel | QFrame.Shadow.Sunken)
        self.setStyleSheet("background-color: #f0f0f0;")

        # Grid layout for widgets
        self.grid_size = (12, 12)  # rows, columns
        self.cell_size = 60  # pixels

        # Calculate size based on grid
        width = self.grid_size[1] * self.cell_size
        height = self.grid_size[0] * self.cell_size
        self.setMinimumSize(width, height)

        # Widget containers
        self.widgets: dict[str, QWidget] = {}

        # Add existing widgets
        for widget_id, widget in self.dashboard.widgets.items():
            self._add_widget(widget_id, widget)

    def _add_widget(self, widget_id: str, widget: BaseWidget) -> None:
        """Add a widget to the canvas.

        Args:
            widget_id: Widget ID
            widget: Widget to add
        """
        # Create container
        container = QFrame()
        container.setFrameStyle(QFrame.Shape.Box | QFrame.Shadow.Raised)
        container.setStyleSheet(
            """
            QFrame {
                background-color: white;
                border: 1px solid #ccc;
                border-radius: 4px;
            }
            QFrame:hover {
                border: 2px solid #4a90e2;
            }
        """
        )
        # Make container selectable - create a method to handle the click
        container.setProperty("widget_id", widget_id)

        def handle_mouse_press(event: QMouseEvent) -> None:
            self._on_widget_clicked(widget_id, event)

        container.mousePressEvent = handle_mouse_press  # type: ignore[method-assign]
        # Create layout
        layout = QVBoxLayout()
        layout.setContentsMargins(2, 2, 2, 2)
        layout.setSpacing(2)
        container.setLayout(layout)

        # Add title bar
        title_bar = QFrame()
        title_bar.setStyleSheet(
            """
            QFrame {
                background-color: #f0f0f0;
                border-bottom: 1px solid #ddd;
                border-top-left-radius: 4px;
                border-top-right-radius: 4px;
                padding: 2px;
            }
            """
        )
        title_layout = QHBoxLayout(title_bar)
        title_layout.setContentsMargins(4, 2, 4, 2)

        # Add title
        title = QLabel(widget.config.title or f"Widget {widget_id[:6]}")
        title.setStyleSheet("font-weight: bold;")
        title_layout.addWidget(title)
        # Add close button
        close_btn = QPushButton("×")
        close_btn.setFixedSize(16, 16)
        close_btn.setStyleSheet(
            """
            QPushButton {
                border: none;
                background: transparent;
                font-weight: bold;
                font-size: 14px;
                padding: 0;
                margin: 0;
            }
            QPushButton:hover {
                color: #ff4444;
            }
        """
        )
        close_btn.clicked.connect(lambda: self._remove_widget(widget_id))
        title_layout.addWidget(close_btn)

        layout.addWidget(title_bar)

        # Add content placeholder
        content = QLabel(f"{widget.config.type.name.replace('_', ' ').title()} Widget")
        content.setAlignment(Qt.AlignmentFlag.AlignCenter)
        content.setStyleSheet("color: #888;")
        layout.addWidget(content, 1)

        # Position and size
        x = widget.config.position[1] * self.cell_size  # col
        y = widget.config.position[0] * self.cell_size  # row
        width = widget.config.size[0] * self.cell_size  # width
        height = widget.config.size[1] * self.cell_size  # height

        # Set geometry
        container.setGeometry(int(x), int(y), int(width), int(height))
        container.raise_()
        container.show()

        # Store reference
        self.widgets[widget_id] = container
        container.setParent(self)

    def _on_widget_clicked(self, widget_id: str, event: QMouseEvent) -> None:  # noqa: N805
        """Handle widget click event.

        Args:
            widget_id: ID of the clicked widget
            event: Mouse event
        """
        self.signals.widget_selected.emit(widget_id)
        event.accept()

    def _remove_widget(self, widget_id: str) -> None:
        """Remove a widget from the canvas.

        Args:
            widget_id: ID of the widget to remove
        """
        if widget_id in self.widgets:
            widget = self.widgets.pop(widget_id)
            widget.deleteLater()
            # Remove from dashboard model if it exists
            if hasattr(self, "dashboard") and widget_id in self.dashboard.widgets:
                del self.dashboard.widgets[widget_id]

    def dropEvent(self, event: QDropEvent) -> None:
        """Handle drop event."""
        if not event.mimeData().hasFormat("application/x-widget-type"):
            event.ignore()
            return

        # Get widget type from mime data
        widget_type_data = event.mimeData().data("application/x-widget-type")
        widget_type_str = widget_type_data.toStdString()
        widget_type = WidgetType(widget_type_str)

        # Calculate grid position
        pos = event.position().toPoint()
        col = max(0, min(self.grid_size[1] - 1, pos.x() // self.cell_size))
        row = max(0, min(self.grid_size[0] - 1, pos.y() // self.cell_size))

        # Default size (2x2 grid cells)
        width, height = 2, 2

        # Emit signal to add widget
        self.signals.add_widget_requested.emit(widget_type, row, col, width, height)
        event.acceptProposedAction()

    def dragEnterEvent(self, event: QDropEvent) -> None:
        """Handle drag enter event."""
        if event.mimeData().hasFormat("application/x-widget-type"):
            event.acceptProposedAction()
        else:
            event.ignore()

    def dragMoveEvent(self, event: QDropEvent) -> None:
        """Handle drag move event."""
        if event.mimeData().hasFormat("application/x-widget-type"):
            event.acceptProposedAction()
        else:
            event.ignore()

    def get_widget_position(self, widget_id: str) -> tuple[int, int]:
        """Get widget position in grid coordinates.

        Args:
            widget_id: Widget ID

        Returns:
            Tuple of (row, col)
        """
        if widget_id not in self.widgets:
            return (0, 0)

        widget = self.widgets[widget_id]
        row = widget.geometry().y() // self.cell_size
        col = widget.geometry().x() // self.cell_size
        return (row, col)

    def get_widget_size(self, widget_id: str) -> tuple[int, int]:
        """Get widget size in grid cells.

        Args:
            widget_id: Widget ID

        Returns:
            Tuple of (width, height) in grid cells
        """
        if widget_id not in self.widgets:
            return (2, 2)

        widget = self.widgets[widget_id]
        width = widget.geometry().width() // self.cell_size
        height = widget.geometry().height() // self.cell_size
        return (width, height)


class DashboardSignals(QObject):
    """Signals for the DashboardEditor."""

    add_widget_requested = Signal(WidgetType, int, int, int, int)  # type, row, col, width, height
    widget_selected = Signal(str)  # widget_id
    dashboard_saved = Signal()  # dashboard saved signal


class DashboardEditor(QWidget):
    """Dashboard editor widget.

    Provides a visual interface for editing dashboards, including adding, removing,
    and configuring widgets.
    """

    def __init__(self, dashboard: Dashboard, parent: Optional[QWidget] = None) -> None:
        """Initialize the dashboard editor.

        Args:
            dashboard: Dashboard to edit
            parent: Parent widget
        """
        super().__init__(parent)
        self.dashboard = dashboard
        self.signals = DashboardSignals()
        self._selected_widget_id: Optional[str] = None
        self._init_ui()

        # Connect signals
        self.signals.add_widget_requested.connect(self._on_add_widget_requested)
        self.signals.widget_selected.connect(self._on_widget_selected)

    def _init_ui(self) -> None:
        """Initialize the user interface."""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(10)

        # Toolbar
        toolbar = QHBoxLayout()

        # Save button
        save_btn = QPushButton("Save Dashboard")
        save_btn.clicked.connect(self.save_dashboard)
        save_btn.setIcon(self.style().standardIcon(QStyle.StandardPixmap.SP_DialogSaveButton))
        toolbar.addWidget(save_btn)

        # Add stretch to push buttons to the right
        toolbar.addStretch()

        # Add delete button (disabled by default)
        self.delete_btn = QPushButton("Delete Widget")
        self.delete_btn.setEnabled(False)
        self.delete_btn.clicked.connect(self._on_delete_widget)
        self.delete_btn.setIcon(self.style().standardIcon(QStyle.StandardPixmap.SP_TrashIcon))
        toolbar.addWidget(self.delete_btn)

        layout.addLayout(toolbar)

        # Create splitter for resizable panels
        splitter = QSplitter(Qt.Orientation.Horizontal)

        # Add widget palette
        self.widget_palette = WidgetPalette()
        splitter.addWidget(self.widget_palette)

        # Add canvas
        self.canvas = DashboardCanvas(self.dashboard)
        splitter.addWidget(self.canvas)

        # Connect canvas signals
        self.canvas.signals.add_widget_requested.connect(self._on_add_widget_requested)
        self.canvas.signals.widget_selected.connect(self._on_widget_selected)

        # Set initial sizes
        splitter.setSizes([200, 600])
        layout.addWidget(splitter, 1)  # Add stretch factor to make it expand

        # Add properties panel (placeholder for now)
        properties_panel = QFrame()
        properties_panel.setFrameStyle(QFrame.Shape.StyledPanel | QFrame.Shadow.Sunken)
        properties_panel.setMinimumWidth(250)
        properties_panel.setMaximumWidth(350)

        properties_layout = QVBoxLayout(properties_panel)
        properties_layout.addWidget(QLabel("Widget Properties"))
        properties_layout.addStretch()

        splitter.addWidget(properties_panel)

    def _on_add_widget_requested(
        self,
        widget_type: WidgetType,
        row: int,
        col: int,
        width: int,
        height: int,
    ) -> None:
        """Handle add widget request.

        Args:
            widget_type: Type of widget to add
            row: Grid row position
            col: Grid column position
            width: Width in grid cells
            height: Height in grid cells
        """
        try:
            # Create unique widget ID
            import uuid

            widget_id = str(uuid.uuid4())

            # Create widget configuration
            config = WidgetConfig(
                id=widget_id,
                type=widget_type,
                position=(row, col),
                size=(width, height),
                title=widget_type.value.replace("_", " ").title(),
            )

            # Create widget instance
            widget_cls = WIDGET_REGISTRY.get(widget_type)
            if widget_cls:
                widget = widget_cls(config=config, dashboard=self.dashboard)
                self.dashboard.add_widget(widget)
                self.canvas._add_widget(widget_id, widget)
                self._selected_widget_id = widget_id
                self.delete_btn.setEnabled(True)
        except Exception as e:
            logger.error(f"Failed to add widget: {e}")
            QMessageBox.critical(self, "Error", f"Failed to add widget: {e}")

    def _on_widget_selected(self, widget_id: str) -> None:
        """Handle widget selection.

        Args:
            widget_id: ID of the selected widget
        """
        self._selected_widget_id = widget_id
        self.delete_btn.setEnabled(True)

    def _on_delete_widget(self) -> None:
        """Handle delete widget button click."""
        if not self._selected_widget_id:
            return

        reply = QMessageBox.question(
            self,
            "Delete Widget",
            "Are you sure you want to delete the selected widget?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )

        if reply == QMessageBox.StandardButton.Yes:
            try:
                self.dashboard.remove_widget(self._selected_widget_id)
                self.canvas._remove_widget(self._selected_widget_id)
                self._selected_widget_id = None
                self.delete_btn.setEnabled(False)
            except Exception as e:
                logger.error(f"Failed to delete widget: {e}")
                QMessageBox.critical(
                    self,
                    "Error",
                    f"Failed to delete widget: {e}",
                    QMessageBox.StandardButton.Ok,
                )

    def save_dashboard(self) -> None:
        """Save the dashboard."""
        try:
            # Update widget positions and sizes from canvas
            for widget_id, widget in self.dashboard.widgets.items():
                if widget_id in self.canvas.widgets:
                    # Update widget position and size from canvas
                    widget.config.position = self.canvas.get_widget_position(widget_id)
                    widget.config.size = self.canvas.get_widget_size(widget_id)

            # Emit signal to notify that dashboard was saved
            self.signals.dashboard_saved.emit()
            QMessageBox.information(
                self,
                "Success",
                "Dashboard saved successfully",
                QMessageBox.StandardButton.Ok,
            )
        except Exception as e:
            logger.error(f"Failed to save dashboard: {e}")
            QMessageBox.critical(
                self,
                "Error",
                f"Failed to save dashboard: {e}",
                QMessageBox.StandardButton.Ok,
            )
