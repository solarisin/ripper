"""Dashboard model and related classes."""

import json
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Type, TypeVar

from loguru import logger

from .data_source import DataSource
from .widgets import WidgetConfig

T = TypeVar("T", bound="Dashboard")


@dataclass
class Dashboard:
    """Represents a dashboard with widgets and data sources."""

    id: str
    name: str
    description: str = ""
    created_at: datetime = field(default_factory=datetime.now)
    updated_at: datetime = field(default_factory=datetime.now)
    data_sources: Dict[str, DataSource] = field(default_factory=dict)
    widgets: Dict[str, WidgetConfig] = field(default_factory=dict)
    grid_size: tuple[int, int] = (12, 12)  # rows, columns
    version: str = "1.0"

    @classmethod
    def create_new(cls: Type[T], name: str, description: str = "") -> T:
        """Create a new dashboard with default settings."""
        dashboard_id = str(uuid.uuid4())
        return cls(
            id=dashboard_id,
            name=name,
            description=description,
        )

    def add_data_source(self, data_source: "DataSource") -> None:
        """Add a data source to the dashboard."""
        self.data_sources[data_source.id] = data_source
        self.updated_at = datetime.now()

    def remove_data_source(self, data_source_id: str) -> bool:
        """Remove a data source from the dashboard."""
        if data_source_id in self.data_sources:
            # Check if any widgets are using this data source
            for widget_config in self.widgets.values():
                if widget_config.data_source_id == data_source_id:
                    raise ValueError(f"Cannot remove data source: used by widget '{widget_config.title}'")
            del self.data_sources[data_source_id]
            self.updated_at = datetime.now()
            return True
        return False

    def add_widget(self, widget: WidgetConfig) -> None:
        """Add a widget to the dashboard."""
        self.widgets[widget.id] = widget
        self.updated_at = datetime.now()

    def remove_widget(self, widget_id: str) -> bool:
        """Remove a widget from the dashboard."""
        if widget_id in self.widgets:
            del self.widgets[widget_id]
            self.updated_at = datetime.now()
            return True
        return False

    def get_widget(self, widget_id: str) -> Optional[WidgetConfig]:
        """Get a widget by ID."""
        return self.widgets.get(widget_id)

    def get_data_source(self, data_source_id: str) -> Optional[DataSource]:
        """Get a data source by ID."""
        return self.data_sources.get(data_source_id)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to a dictionary for serialization."""
        return {
            "id": self.id,
            "name": self.name,
            "description": self.description,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
            "data_sources": {k: v.to_dict() for k, v in self.data_sources.items()},
            "widgets": {k: v.to_dict() for k, v in self.widgets.items()},
            "grid_size": list(self.grid_size),
            "version": self.version,
        }

    @classmethod
    def from_dict(cls: Type[T], data: Dict[str, Any]) -> T:
        """Create a dashboard from a dictionary.

        Args:
            data: Dictionary containing dashboard data

        Returns:
            Dashboard instance
        """
        dashboard = cls(
            id=data.get("id", str(uuid.uuid4())),
            name=data["name"],
            description=data.get("description", ""),
            created_at=datetime.fromisoformat(data.get("created_at", datetime.now().isoformat())),
            updated_at=datetime.fromisoformat(data.get("updated_at", datetime.now().isoformat())),
            grid_size=tuple(data.get("grid_size", [12, 12])),
            version=data.get("version", "1.0"),
        )

        # Add data sources. Malformed items are skipped so one bad entry cannot discard
        # the whole dashboard: KeyError/ValueError for missing fields or bad enum/date
        # values, TypeError for non-string dates, AttributeError for date_range: null.
        for source_data in data.get("data_sources", {}).values():
            try:
                source = DataSource.from_dict(source_data)
                dashboard.data_sources[source.id] = source
            except (KeyError, ValueError, TypeError, AttributeError) as e:
                logger.error(f"Failed to load data source: {e}")
                continue

        # Add widgets. Same per-item recovery; TypeError also covers null/non-iterable
        # position or size values.
        for widget_data in data.get("widgets", {}).values():
            try:
                widget = WidgetConfig.from_dict(widget_data)
                dashboard.widgets[widget.id] = widget
            except (KeyError, ValueError, TypeError, AttributeError) as e:
                logger.error(f"Failed to load widget: {e}")
                continue

        # Prune widgets that reference a data source that failed to load or is missing.
        # Widgets with data_source_id=None are legitimately unbound and are kept.
        dangling_widget_ids = [
            widget_id
            for widget_id, widget in dashboard.widgets.items()
            if widget.data_source_id is not None and widget.data_source_id not in dashboard.data_sources
        ]
        for widget_id in dangling_widget_ids:
            widget = dashboard.widgets.pop(widget_id)
            logger.warning(
                f"Pruning widget '{widget.title}' ({widget_id}): references missing data source {widget.data_source_id}"
            )

        return dashboard

    def save_to_file(self, file_path: Path) -> None:
        """Save dashboard to a file."""
        data = self.to_dict()
        with open(file_path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)

    @classmethod
    def load_from_file(cls: Type[T], file_path: Path) -> T:
        """Load dashboard from a file."""
        with open(file_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return cls.from_dict(data)


class DashboardManager:
    """Manages a collection of dashboards."""

    def __init__(self, storage_dir: Path):
        """Initialize the dashboard manager.

        Args:
            storage_dir: Directory where dashboard files are stored
        """
        self.storage_dir = storage_dir
        self.storage_dir.mkdir(parents=True, exist_ok=True)
        self._dashboards: Dict[str, Dashboard] = {}
        self._load_dashboards()

    def _load_dashboards(self) -> None:
        """Load all dashboards from the storage directory."""
        self._dashboards = {}
        for file_path in self.storage_dir.glob("*.json"):
            try:
                dashboard = Dashboard.load_from_file(file_path)
                self._dashboards[dashboard.id] = dashboard
                logger.info(f"Loaded dashboard: {dashboard.name} ({dashboard.id})")
            except Exception as e:
                logger.error(f"Error loading dashboard from {file_path}: {e}")

    def create_dashboard(self, name: str, description: str = "") -> Dashboard:
        """Create a new dashboard.

        Args:
            name: Dashboard name
            description: Optional description

        Returns:
            The created dashboard
        """
        dashboard = Dashboard.create_new(name, description)
        self._dashboards[dashboard.id] = dashboard
        return dashboard

    def get_dashboard(self, dashboard_id: str) -> Optional[Dashboard]:
        """Get a dashboard by ID.

        Args:
            dashboard_id: Dashboard ID

        Returns:
            The dashboard, or None if not found
        """
        return self._dashboards.get(dashboard_id)

    def get_all_dashboards(self) -> List[Dashboard]:
        """Get all dashboards.

        Returns:
            List of all dashboards
        """
        return list(self._dashboards.values())

    def save_dashboard(self, dashboard: Dashboard) -> Path:
        """Save a dashboard to disk and register it as the in-memory instance.

        Registering keeps the manager's store coherent when the caller saves a
        different object than the one currently held (e.g. the edit dialog's
        working copy, #95): subsequent lookups return the saved instance.
        Registration happens only after the file write succeeds, so a failed
        save leaves the previously held instance in place and memory stays
        consistent with disk.

        Args:
            dashboard: Dashboard to save

        Returns:
            Path to the saved file
        """
        file_path = self.storage_dir / f"{dashboard.id}.json"
        dashboard.save_to_file(file_path)
        self._dashboards[dashboard.id] = dashboard
        return file_path

    def delete_dashboard(self, dashboard_id: str) -> bool:
        """Delete a dashboard.

        Args:
            dashboard_id: ID of the dashboard to delete

        Returns:
            True if deleted, False if not found
        """
        if dashboard_id in self._dashboards:
            file_path = self.storage_dir / f"{dashboard_id}.json"
            if file_path.exists():
                file_path.unlink()
            del self._dashboards[dashboard_id]
            return True
        return False


# widgets.py annotates parameters with "Dashboard" but cannot import this module at top
# level (this module imports WidgetConfig from it). Publish the now-defined Dashboard into
# that module's namespace so runtime type checkers (beartype) can resolve the forward
# reference; static checkers use widgets.py's own TYPE_CHECKING import.
from . import widgets as _widgets  # noqa: E402

_widgets.Dashboard = Dashboard  # type: ignore[misc]
