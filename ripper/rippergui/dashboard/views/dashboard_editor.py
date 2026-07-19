"""Dashboard editor view."""

import uuid
from typing import Any, Callable, Optional

from loguru import logger
from PySide6.QtCore import QMimeData, QObject, QSize, Qt, Signal
from PySide6.QtGui import QDrag, QDropEvent, QMouseEvent
from PySide6.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QDialog,
    QFormLayout,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListView,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QSplitter,
    QStyle,
    QVBoxLayout,
    QWidget,
)

from ripper.rippergui.dashboard.models import (
    Dashboard,
    DataSource,
    DataSourceType,
    DateRange,
    DateRangePreset,
    WidgetConfig,
)
from ripper.rippergui.dashboard.models.widget_types import WidgetType
from ripper.rippergui.dashboard.services import DashboardDataService
from ripper.ripperlib.database import Db


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

        # Add widget items. Only the functional financial widgets are offered; the
        # non-functional placeholder types were removed in #41.
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
            WidgetType.SPENDING_TREND: QStyle.StandardPixmap.SP_FileDialogDetailedView,
            WidgetType.CATEGORY_BREAKDOWN: QStyle.StandardPixmap.SP_DialogYesButton,
            WidgetType.BUDGET_VS_ACTUAL: QStyle.StandardPixmap.SP_DialogApplyButton,
            WidgetType.TOP_EXPENSES: QStyle.StandardPixmap.SP_FileDialogListView,
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
        self.grid_size = dashboard.grid_size  # rows, columns
        self.cell_size = 60  # pixels

        # Calculate size based on grid
        width = self.grid_size[1] * self.cell_size
        height = self.grid_size[0] * self.cell_size
        self.setMinimumSize(width, height)
        self.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)

        # Widget containers
        self.widgets: dict[str, QWidget] = {}
        self.widget_title_labels: dict[str, QLabel] = {}

        # Add existing widgets
        for widget in self.dashboard.widgets.values():
            self._add_widget(widget)

    def _add_widget(self, widget: WidgetConfig) -> None:
        """Add a widget to the canvas."""
        container = QFrame()
        container.setFrameStyle(QFrame.Shape.Box | QFrame.Shadow.Raised)
        container.setStyleSheet(self._widget_style(False))
        container.setProperty("widget_id", widget.id)

        def handle_mouse_press(event: QMouseEvent) -> None:
            self._on_widget_clicked(widget.id, event)

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
        title = QLabel(widget.title or f"Widget {widget.id[:6]}")
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
        close_btn.clicked.connect(lambda: self._remove_widget(widget.id))
        title_layout.addWidget(close_btn)

        layout.addWidget(title_bar)

        # Add content placeholder
        content = QLabel(f"{widget.type.name.replace('_', ' ').title()} Widget")
        content.setAlignment(Qt.AlignmentFlag.AlignCenter)
        content.setStyleSheet("color: #888;")
        layout.addWidget(content, 1)

        # Position and size
        x = widget.position[1] * self.cell_size  # col
        y = widget.position[0] * self.cell_size  # row
        width = widget.size[0] * self.cell_size  # width
        height = widget.size[1] * self.cell_size  # height

        # Set geometry
        container.setParent(self)
        container.setGeometry(int(x), int(y), int(width), int(height))
        container.raise_()
        container.show()

        # Store reference
        self.widgets[widget.id] = container
        self.widget_title_labels[widget.id] = title

    def _widget_style(self, selected: bool) -> str:
        border = "2px solid #2f6fed" if selected else "1px solid #ccc"
        return f"""
            QFrame {{
                background-color: white;
                border: {border};
                border-radius: 4px;
            }}
            QFrame:hover {{
                border: 2px solid #4a90e2;
            }}
        """

    def select_widget(self, widget_id: str) -> None:
        """Update canvas selection styling."""
        for current_id, widget in self.widgets.items():
            widget.setStyleSheet(self._widget_style(current_id == widget_id))

    def set_widget_title(self, widget_id: str, title: str) -> None:
        """Update a widget title shown on the canvas."""
        if widget_id in self.widget_title_labels:
            self.widget_title_labels[widget_id].setText(title)

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
            self.widget_title_labels.pop(widget_id, None)
            widget.deleteLater()
            self.dashboard.remove_widget(widget_id)

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

    def __init__(
        self,
        dashboard: Dashboard,
        parent: Optional[QWidget] = None,
        data_source_provider: Optional[Callable[[], list[dict[str, Any]]]] = None,
    ) -> None:
        """Initialize the dashboard editor.

        Args:
            dashboard: Dashboard to edit
            parent: Parent widget
            data_source_provider: Optional callable returning the loaded data-source records,
                injectable for testing. Defaults to the shared database singleton.
        """
        super().__init__(parent)
        self.dashboard = dashboard
        self.signals = DashboardSignals()
        self._selected_widget_id: Optional[str] = None
        self.data_service = DashboardDataService()
        self._data_source_provider: Callable[[], list[dict[str, Any]]] = (
            data_source_provider if data_source_provider is not None else Db.list_data_sources
        )
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
        save_btn.clicked.connect(self.apply_canvas_state)
        save_btn.setIcon(self.style().standardIcon(QStyle.StandardPixmap.SP_DialogSaveButton))
        toolbar.addWidget(save_btn)

        add_selected_btn = QPushButton("Add Selected Widget")
        add_selected_btn.clicked.connect(self._on_add_selected_widget)
        toolbar.addWidget(add_selected_btn)

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
        splitter.setChildrenCollapsible(False)
        splitter.setHandleWidth(8)

        # Add widget palette
        self.widget_palette = WidgetPalette()
        self.widget_palette.widget_list.itemDoubleClicked.connect(self._on_palette_item_activated)
        splitter.addWidget(self.widget_palette)

        # Add canvas
        self.canvas = DashboardCanvas(self.dashboard)
        self.canvas_scroll = QScrollArea()
        self.canvas_scroll.setWidgetResizable(False)
        self.canvas_scroll.setFrameShape(QFrame.Shape.NoFrame)
        self.canvas_scroll.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop)
        self.canvas_scroll.setWidget(self.canvas)
        self.canvas_scroll.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        splitter.addWidget(self.canvas_scroll)

        # Connect canvas signals
        self.canvas.signals.add_widget_requested.connect(self._on_add_widget_requested)
        self.canvas.signals.widget_selected.connect(self._on_widget_selected)

        self.properties_panel = QFrame()
        self.properties_panel.setFrameStyle(QFrame.Shape.StyledPanel | QFrame.Shadow.Sunken)
        self.properties_panel.setMinimumWidth(300)
        self.properties_panel.setMaximumWidth(520)
        self.properties_panel.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Expanding)

        properties_layout = QVBoxLayout(self.properties_panel)
        self.properties_help_label = QLabel("Select a widget to edit its title and data source.")
        self.properties_help_label.setWordWrap(True)
        self.properties_help_label.setStyleSheet("color: #666;")
        properties_layout.addWidget(self.properties_help_label)
        properties_layout.addWidget(QLabel("Widget Properties"))

        form_layout = QFormLayout()
        self.widget_title_edit = QLineEdit()
        self.widget_title_edit.editingFinished.connect(self._on_title_edited)
        form_layout.addRow("Title:", self.widget_title_edit)

        self.data_source_combo = QComboBox()
        self.data_source_combo.currentIndexChanged.connect(self._on_data_source_changed)
        form_layout.addRow("Data source:", self.data_source_combo)
        properties_layout.addLayout(form_layout)

        add_source_button = QPushButton("Add Transaction Source")
        add_source_button.clicked.connect(self._on_add_transaction_source)
        properties_layout.addWidget(add_source_button)
        self.source_summary_label = QLabel("")
        self.source_summary_label.setWordWrap(True)
        self.source_summary_label.setStyleSheet("color: #666;")
        properties_layout.addWidget(self.source_summary_label)
        properties_layout.addStretch()

        splitter.addWidget(self.properties_panel)
        splitter.setStretchFactor(0, 0)
        splitter.setStretchFactor(1, 1)
        splitter.setStretchFactor(2, 0)
        splitter.setSizes([200, 520, 320])
        layout.addWidget(splitter, 1)
        self._refresh_data_source_combo()
        self._set_properties_enabled(False)
        self._refresh_source_summary()

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
            widget_id = str(uuid.uuid4())

            # Create widget configuration
            config = WidgetConfig(
                id=widget_id,
                type=widget_type,
                position=(row, col),
                size=(width, height),
                title=widget_type.value.replace("_", " ").title(),
            )

            self.dashboard.add_widget(config)
            self.canvas._add_widget(config)
            self._selected_widget_id = widget_id
            self.canvas.select_widget(widget_id)
            self.delete_btn.setEnabled(True)
            self._load_selected_widget_properties()
        except Exception as e:
            logger.error(f"Failed to add widget: {e}")
            QMessageBox.critical(self, "Error", f"Failed to add widget: {e}")

    def _on_widget_selected(self, widget_id: str) -> None:
        """Handle widget selection.

        Args:
            widget_id: ID of the selected widget
        """
        self._selected_widget_id = widget_id
        self.canvas.select_widget(widget_id)
        self.delete_btn.setEnabled(True)
        self._load_selected_widget_properties()

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
                self.canvas._remove_widget(self._selected_widget_id)
                self._selected_widget_id = None
                self.delete_btn.setEnabled(False)
                self._set_properties_enabled(False)
                self._refresh_data_source_combo()
            except Exception as e:
                logger.error(f"Failed to delete widget: {e}")
                QMessageBox.critical(
                    self,
                    "Error",
                    f"Failed to delete widget: {e}",
                    QMessageBox.StandardButton.Ok,
                )

    def apply_canvas_state(self) -> None:
        """Apply canvas widget positions/sizes to the in-memory dashboard model.

        This method reads the current geometry of each widget on the canvas and
        writes the derived grid position and size back into the corresponding
        ``WidgetConfig`` objects. It then emits ``signals.dashboard_saved`` so
        that callers (e.g. ``DashboardView._on_edit_dashboard``) know the model
        is up to date and can persist it to disk.
        """
        try:
            # Update widget positions and sizes from canvas
            for widget_id, widget in self.dashboard.widgets.items():
                if widget_id in self.canvas.widgets:
                    # Update widget position and size from canvas
                    widget.position = self.canvas.get_widget_position(widget_id)
                    widget.size = self.canvas.get_widget_size(widget_id)

            # Emit signal so the caller knows the model is up to date
            self.signals.dashboard_saved.emit()
            self.source_summary_label.setStyleSheet("color: #1b5e20;")
            self.source_summary_label.setText("Canvas state applied.")
        except Exception as e:
            logger.error(f"Failed to apply canvas state: {e}")
            QMessageBox.critical(
                self,
                "Error",
                f"Failed to apply canvas state: {e}",
                QMessageBox.StandardButton.Ok,
            )

    def _set_properties_enabled(self, enabled: bool) -> None:
        self.widget_title_edit.setEnabled(enabled)
        self.data_source_combo.setEnabled(enabled)

    def _load_selected_widget_properties(self) -> None:
        if not self._selected_widget_id:
            self._set_properties_enabled(False)
            return
        widget = self.dashboard.get_widget(self._selected_widget_id)
        if not widget:
            self._set_properties_enabled(False)
            return
        self._set_properties_enabled(True)
        self.widget_title_edit.blockSignals(True)
        self.widget_title_edit.setText(widget.title)
        self.widget_title_edit.blockSignals(False)
        self._refresh_data_source_combo(widget.data_source_id)

    def _refresh_data_source_combo(self, selected_id: Optional[str] = None) -> None:
        self.data_source_combo.blockSignals(True)
        self.data_source_combo.clear()
        self.data_source_combo.addItem("No data source", None)
        for data_source in self.dashboard.data_sources.values():
            self.data_source_combo.addItem(data_source.name, data_source.id)
        if selected_id:
            index = self.data_source_combo.findData(selected_id)
            if index >= 0:
                self.data_source_combo.setCurrentIndex(index)
        self.data_source_combo.blockSignals(False)
        self._refresh_source_summary()

    def _refresh_source_summary(self) -> None:
        count = len(self.dashboard.data_sources)
        self.source_summary_label.setStyleSheet("color: #666;")
        if count == 0:
            self.source_summary_label.setText("No data sources configured yet.")
        else:
            self.source_summary_label.setText(f"{count} data source(s) configured.")

    def _on_title_edited(self) -> None:
        if not self._selected_widget_id:
            return
        widget = self.dashboard.get_widget(self._selected_widget_id)
        if widget:
            widget.title = self.widget_title_edit.text().strip() or widget.type.value.replace("_", " ").title()
            self.canvas.set_widget_title(widget.id, widget.title)

    def _on_data_source_changed(self, index: int) -> None:
        if not self._selected_widget_id:
            return
        widget = self.dashboard.get_widget(self._selected_widget_id)
        if widget:
            widget.data_source_id = self.data_source_combo.itemData(index)

    def _on_add_selected_widget(self) -> None:
        selected_items = self.widget_palette.widget_list.selectedItems()
        if not selected_items:
            QMessageBox.information(self, "Add Widget", "Select a widget from the palette first.")
            return
        self._add_widget_from_palette_item(selected_items[0])

    def _on_palette_item_activated(self, item: QListWidgetItem) -> None:
        self._add_widget_from_palette_item(item)

    def _add_widget_from_palette_item(self, item: QListWidgetItem) -> None:
        widget_type = item.data(Qt.ItemDataRole.UserRole)
        if not isinstance(widget_type, WidgetType):
            return
        row, col = self._next_widget_position()
        self._on_add_widget_requested(widget_type, row, col, 3, 3)

    def _next_widget_position(self) -> tuple[int, int]:
        """Return the next available grid position, clamped to the canvas grid."""
        count = len(self.dashboard.widgets)
        default_widget_size = 3
        max_row = max(0, self.dashboard.grid_size[0] - default_widget_size)
        max_col = max(0, self.dashboard.grid_size[1] - default_widget_size)
        row = min((count // 3) * default_widget_size, max_row)
        col = min((count % 3) * default_widget_size, max_col)
        return (row, col)

    def _on_add_transaction_source(self) -> None:
        """
        Open a picker over already-loaded Db data sources and attach the
        selection as a dashboard data source.

        Shows a warning if no data sources have been loaded yet (direct the user
        to load one via the main window's "New Source" action first).
        """
        records = self._data_source_provider()
        if not records:
            QMessageBox.information(
                self,
                "No Data Sources",
                "No data sources have been loaded yet.\n\n"
                'Use "New Source" in the main window to load a Google Sheet first,'
                " then come back here to attach it to a dashboard widget.",
            )
            return

        # Build a simple picker dialog
        picker = QDialog(self)
        picker.setWindowTitle("Select Data Source")
        picker.setMinimumWidth(360)
        picker_layout = QVBoxLayout(picker)
        picker_layout.addWidget(QLabel("Choose a loaded data source:"))

        list_widget = QListWidget(picker)
        for rec in records:
            label = rec["name"]
            spreadsheet_name = rec.get("spreadsheet_name") or rec["spreadsheet_id"]
            item = QListWidgetItem(f"{label}  ({spreadsheet_name} › {rec['sheet_name']})")
            item.setData(Qt.ItemDataRole.UserRole, rec)
            list_widget.addItem(item)
        list_widget.setCurrentRow(0)
        picker_layout.addWidget(list_widget)

        btn_row = QHBoxLayout()
        ok_btn = QPushButton("Add")
        ok_btn.setDefault(True)
        cancel_btn = QPushButton("Cancel")
        ok_btn.clicked.connect(picker.accept)
        cancel_btn.clicked.connect(picker.reject)
        btn_row.addStretch()
        btn_row.addWidget(ok_btn)
        btn_row.addWidget(cancel_btn)
        picker_layout.addLayout(btn_row)

        if picker.exec() != QDialog.DialogCode.Accepted:
            return

        selected_item = list_widget.currentItem()
        # Qt stubs type currentItem() as non-optional, but it returns None when nothing is selected.
        if selected_item is None:
            return  # type: ignore[unreachable]
        rec = selected_item.data(Qt.ItemDataRole.UserRole)

        data_source = DataSource(
            id=str(uuid.uuid4()),
            type=DataSourceType.TILLER_TRANSACTIONS,
            name=rec["name"],
            spreadsheet_id=rec["spreadsheet_id"],
            sheet_name=rec["sheet_name"],
            range_a1=rec["range_a1"],
            date_range=DateRange(DateRangePreset.YEAR_TO_DATE),
        )
        self.dashboard.add_data_source(data_source)
        self._refresh_data_source_combo(data_source.id)
        self.source_summary_label.setStyleSheet("color: #1b5e20;")
        self.source_summary_label.setText(f"Added data source '{data_source.name}'.")
        if self._selected_widget_id:
            widget = self.dashboard.get_widget(self._selected_widget_id)
            if widget:
                widget.data_source_id = data_source.id
                self._refresh_data_source_combo(data_source.id)
