"""Widget models for dashboards."""

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Dict, Optional

from loguru import logger
from PySide6.QtWidgets import QWidget

# Import the registry functions to maintain backward compatibility
from .registry import register_widget  # noqa: F401
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
    size: tuple[int, int]  # size in grid units (width=cols, height=rows)
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

    def update_data(self, data_cache: Any = None, category_types: dict[str, str] | None = None) -> None:
        """Update widget data from the runtime data cache.

        The dashboard's refresh service populates ``data_cache`` as a mapping of
        ``data_source_id -> records`` and passes it here; this dict is the only
        supported contract. The former legacy branch that synchronously fetched
        via a "service" object has been removed (#62).

        Args:
            data_cache: Mapping of data source id to already-refreshed records.
            category_types: Optional authoritative ``{category_name: type}`` map
                from the Tiller Categories sheet, forwarded to
                ``TillerDataProcessor`` for Type-based transfer/income
                classification (issue #115). Ignored by widgets that don't
                process transactions.
        """
        if not self.config.data_source_id:
            return

        data_source = self.dashboard.get_data_source(self.config.data_source_id)
        if not data_source:
            return

        if not isinstance(data_cache, dict):
            # No runtime cache provided (or a legacy non-dict argument): nothing to render.
            return

        data = data_cache.get(self.config.data_source_id)
        if data is None:
            # The dashboard may not have been refreshed yet; this is normal on
            # first render and should not produce noisy logs.
            logger.debug(f"No refreshed data yet for data source {self.config.data_source_id}")
            return

        self._process_data(data)

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
