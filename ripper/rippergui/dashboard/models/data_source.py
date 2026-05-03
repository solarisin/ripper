"""Data source models for dashboards."""

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from typing import Any, Dict, Optional


class DataSourceType(Enum):
    """Types of data sources."""

    TILLER_TRANSACTIONS = "tiller_transactions"
    TILLER_CATEGORIES = "tiller_categories"
    TILLER_BUDGET = "tiller_budget"


class DateRangePreset(Enum):
    """Preset date ranges for data sources."""

    CURRENT_MONTH = "current_month"
    LAST_30_DAYS = "last_30_days"
    LAST_90_DAYS = "last_90_days"
    YEAR_TO_DATE = "year_to_date"
    LAST_YEAR = "last_year"
    CUSTOM = "custom"


@dataclass
class DateRange:
    """Represents a date range for filtering data."""

    preset: DateRangePreset
    start_date: Optional[datetime] = None
    end_date: Optional[datetime] = None

    def get_date_range(self) -> tuple[datetime, datetime]:
        """Get the start and end dates for this range."""
        now = datetime.now()
        if self.preset == DateRangePreset.CURRENT_MONTH:
            start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
            next_month = start.replace(day=28) + timedelta(days=4)  # Move to next month
            end = (next_month - timedelta(days=next_month.day)).replace(hour=23, minute=59, second=59)
            return start, end
        elif self.preset == DateRangePreset.LAST_30_DAYS:
            return now - timedelta(days=30), now
        elif self.preset == DateRangePreset.LAST_90_DAYS:
            return now - timedelta(days=90), now
        elif self.preset == DateRangePreset.YEAR_TO_DATE:
            return now.replace(month=1, day=1, hour=0, minute=0, second=0, microsecond=0), now
        elif self.preset == DateRangePreset.LAST_YEAR:
            last_year = now.year - 1
            return (datetime(last_year, 1, 1), datetime(last_year, 12, 31, 23, 59, 59))
        elif self.preset == DateRangePreset.CUSTOM and self.start_date and self.end_date:
            return self.start_date, self.end_date
        else:
            # Default to last 30 days
            return now - timedelta(days=30), now


@dataclass
class DataSource:
    """Represents a data source for a dashboard."""

    id: str
    type: DataSourceType
    name: str
    spreadsheet_id: str
    sheet_name: str
    range_a1: str
    date_range: DateRange
    filters: Dict[str, Any] = field(default_factory=dict)
    data: Any = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert to a dictionary for serialization."""
        return {
            "id": self.id,
            "type": self.type.value,
            "name": self.name,
            "spreadsheet_id": self.spreadsheet_id,
            "sheet_name": self.sheet_name,
            "range_a1": self.range_a1,
            "date_range": {
                "preset": self.date_range.preset.value,
                "start_date": self.date_range.start_date.isoformat() if self.date_range.start_date else None,
                "end_date": self.date_range.end_date.isoformat() if self.date_range.end_date else None,
            },
            "filters": self.filters,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "DataSource":
        """Create from a dictionary."""
        date_range_data = data.get("date_range", {})
        date_range = DateRange(
            preset=DateRangePreset(date_range_data.get("preset", DateRangePreset.LAST_30_DAYS.value)),
            start_date=(
                datetime.fromisoformat(date_range_data["start_date"]) if date_range_data.get("start_date") else None
            ),
            end_date=datetime.fromisoformat(date_range_data["end_date"]) if date_range_data.get("end_date") else None,
        )
        return cls(
            id=data["id"],
            type=DataSourceType(data["type"]),
            name=data["name"],
            spreadsheet_id=data["spreadsheet_id"],
            sheet_name=data["sheet_name"],
            range_a1=data["range_a1"],
            date_range=date_range,
            filters=data.get("filters", {}),
        )

    def fetch_data(self, service: Any) -> Any:
        """Fetch data for this data source.

        Args:
            service: The service object to use for fetching data

        Returns:
            The fetched data

        Raises:
            ValueError: If the data source type is unknown
        """
        from ripper.ripperlib.sheets_backend import retrieve_sheet_data

        if self.type == DataSourceType.TILLER_TRANSACTIONS:
            data, _ = retrieve_sheet_data(service, self.spreadsheet_id, f"{self.sheet_name}!{self.range_a1}")
            if not data or len(data) < 2:
                return []
            headers = [str(cell).strip().lower().replace(" ", "_") for cell in data[0]]
            return [
                {headers[index]: cell for index, cell in enumerate(row) if index < len(headers)} for row in data[1:]
            ]

        raise ValueError(f"Unknown data source type: {self.type}")
