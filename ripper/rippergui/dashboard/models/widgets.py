"""Widget models for dashboards."""

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Dict, Optional

from loguru import logger
from PySide6.QtWidgets import QWidget

# Import the registry functions to maintain backward compatibility
from .registry import WIDGET_REGISTRY, register_widget  # noqa: F401
from .widget_types import WidgetType

if TYPE_CHECKING:
    from .dashboard import Dashboard


@dataclass
class WidgetConfig:
    """Configuration for a dashboard widget."""

    id: str
    type: WidgetType
    title: str
    position: tuple[int, int]  # grid position (row, col)
    size: tuple[int, int]  # size in grid units (rows, cols)
    data_source_id: Optional[str] = None
    properties: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to a dictionary for serialization."""
        return {
            "id": self.id,
            "type": self.type.value,
            "title": self.title,
            "position": list(self.position),
            "size": list(self.size),
            "data_source_id": self.data_source_id,
            "properties": self.properties,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "WidgetConfig":
        """Create from a dictionary."""
        return cls(
            id=data["id"],
            type=WidgetType(data["type"]),
            title=data["title"],
            position=tuple(data["position"]),
            size=tuple(data["size"]),
            data_source_id=data.get("data_source_id"),
            properties=data.get("properties", {}),
        )


class BaseWidget:
    """Base class for all dashboard widgets."""

    def __init__(self, config: WidgetConfig, dashboard: "Dashboard"):
        """Initialize the widget.

        Args:
            config: Widget configuration
            dashboard: Parent dashboard
        """
        self.config = config
        self.dashboard = dashboard

    def create_widget(self, parent: QWidget) -> QWidget:
        """Create and return the Qt widget.

        Args:
            parent: Parent widget

        Returns:
            The created widget
        """
        raise NotImplementedError("Subclasses must implement create_widget")

    def update_data(self, service: Any = None) -> None:
        """Update widget data from its data source.

        Args:
            service: Optional service object for data fetching
        """
        if not self.config.data_source_id:
            return

        data_source = self.dashboard.get_data_source(self.config.data_source_id)
        if not data_source:
            return

        try:
            if service is not None:
                data = data_source.fetch_data(service)
            else:
                # TODO: Get service from dashboard or application context
                logger.warning("No service provided for data fetching")
                return
            self._process_data(data)
        except Exception as e:
            print(f"Error updating widget data: {e}")

    def _process_data(self, data: Any) -> None:
        """Process data from the data source.

        Args:
            data: Data from the data source
        """
        raise NotImplementedError("Subclasses must implement _process_data")

    def to_dict(self) -> Dict[str, Any]:
        """Convert to a dictionary for serialization."""
        return self.config.to_dict()

    @classmethod
    def from_dict(cls, data: Dict[str, Any], dashboard: "Dashboard") -> "BaseWidget":
        """Create from a dictionary."""
        config = WidgetConfig.from_dict(data)
        return cls(config, dashboard)


@register_widget(WidgetType.LINE_CHART)
class LineChartWidget(BaseWidget):
    """Line chart widget."""

    def create_widget(self, parent: QWidget) -> QWidget:
        from PySide6.QtWidgets import QLabel

        return QLabel(f"Line Chart: {self.config.title}", parent)

    def _process_data(self, data: Any) -> None:
        pass


@register_widget(WidgetType.BAR_CHART)
class BarChartWidget(BaseWidget):
    """Bar chart widget."""

    def create_widget(self, parent: QWidget) -> QWidget:
        from PySide6.QtWidgets import QLabel

        return QLabel(f"Bar Chart: {self.config.title}", parent)

    def _process_data(self, data: Any) -> None:
        pass


@register_widget(WidgetType.PIE_CHART)
class PieChartWidget(BaseWidget):
    """Pie chart widget."""

    def create_widget(self, parent: QWidget) -> QWidget:
        from PySide6.QtWidgets import QLabel

        return QLabel(f"Pie Chart: {self.config.title}", parent)

    def _process_data(self, data: Any) -> None:
        pass


@register_widget(WidgetType.DATA_TABLE)
class DataTableWidget(BaseWidget):
    """Data table widget."""

    def create_widget(self, parent: QWidget) -> QWidget:
        from PySide6.QtWidgets import QLabel

        return QLabel(f"Data Table: {self.config.title}", parent)

    def _process_data(self, data: Any) -> None:
        pass


@register_widget(WidgetType.KPI)
class KPIWidget(BaseWidget):
    """KPI (Key Performance Indicator) widget."""

    def create_widget(self, parent: QWidget) -> QWidget:
        from PySide6.QtWidgets import QLabel

        return QLabel(f"KPI: {self.config.title}", parent)

    def _process_data(self, data: Any) -> None:
        pass


@register_widget(WidgetType.GAUGE)
class GaugeWidget(BaseWidget):
    """Gauge widget."""

    def create_widget(self, parent: QWidget) -> QWidget:
        from PySide6.QtWidgets import QLabel

        return QLabel(f"Gauge: {self.config.title}", parent)

    def _process_data(self, data: Any) -> None:
        pass
