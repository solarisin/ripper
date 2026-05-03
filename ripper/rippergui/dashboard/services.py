"""Runtime services for dashboard data loading."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Callable

from loguru import logger

from ripper.ripperlib.defs import SheetData, SheetsService
from ripper.rippergui.dashboard.models import Dashboard, DataSource, DataSourceType
from ripper.ripperlib.auth import AuthManager


REQUIRED_TRANSACTION_COLUMNS = frozenset({"date", "description", "category", "amount", "account"})


def normalize_header(header: object) -> str:
    """Normalize a spreadsheet header for matching Tiller columns."""
    return str(header).strip().lower().replace(" ", "_")


def records_from_sheet_data(data: SheetData) -> list[dict[str, Any]]:
    """Convert sheet rows to dictionaries using the first row as headers."""
    if not data or len(data) < 2:
        return []
    headers = [normalize_header(cell) for cell in data[0]]
    records = []
    for row in data[1:]:
        record = {}
        for index, header in enumerate(headers):
            if index < len(row):
                record[header] = row[index]
        records.append(record)
    return records


def validate_transaction_sheet_data(data: SheetData) -> tuple[bool, set[str]]:
    """Validate that sheet data has the required Tiller transaction columns."""
    if not data:
        return False, set(REQUIRED_TRANSACTION_COLUMNS)
    headers = {normalize_header(cell) for cell in data[0]}
    missing = set(REQUIRED_TRANSACTION_COLUMNS - headers)
    return not missing, missing


@dataclass
class DataSourceRefreshStatus:
    """Result of refreshing a single data source."""

    data_source_id: str
    ok: bool
    message: str
    row_count: int = 0
    unsupported: bool = False


@dataclass
class DashboardRefreshResult:
    """Result of refreshing dashboard data sources."""

    data: dict[str, list[dict[str, Any]]] = field(default_factory=dict)
    statuses: dict[str, DataSourceRefreshStatus] = field(default_factory=dict)

    def has_errors(self) -> bool:
        """Return True if any refresh status failed."""
        return any(not status.ok for status in self.statuses.values())


class DashboardDataService:
    """Fetch and validate runtime data for dashboards."""

    def __init__(
        self,
        auth_manager: AuthManager | None = None,
        retrieve_sheet_data_fn: Callable[[SheetsService, str, str], tuple[SheetData, list[tuple[Any, str]]]]
        | None = None,
    ) -> None:
        self._auth_manager = auth_manager or AuthManager()
        self._retrieve_sheet_data_fn = retrieve_sheet_data_fn

    def create_sheets_service(self) -> SheetsService | None:
        """Create an authenticated Sheets service."""
        return self._auth_manager.create_sheets_service()

    def refresh_dashboard(self, dashboard: Dashboard) -> DashboardRefreshResult:
        """Refresh all configured data sources for a dashboard."""
        service = self.create_sheets_service()
        result = DashboardRefreshResult()
        if service is None:
            for data_source_id in dashboard.data_sources:
                result.statuses[data_source_id] = DataSourceRefreshStatus(
                    data_source_id=data_source_id,
                    ok=False,
                    message="Could not authenticate with Google Sheets API.",
                )
            return result

        for data_source in dashboard.data_sources.values():
            status, records = self.refresh_data_source(service, data_source)
            result.statuses[data_source.id] = status
            if records is not None:
                result.data[data_source.id] = records
        return result

    def refresh_data_source(
        self, service: SheetsService, data_source: DataSource
    ) -> tuple[DataSourceRefreshStatus, list[dict[str, Any]] | None]:
        """Refresh one data source."""
        if data_source.type != DataSourceType.TILLER_TRANSACTIONS:
            return (
                DataSourceRefreshStatus(
                    data_source_id=data_source.id,
                    ok=False,
                    message=f"Data source type {data_source.type.value} is not supported yet.",
                    unsupported=True,
                ),
                None,
            )

        range_name = f"{data_source.sheet_name}!{data_source.range_a1}"
        try:
            data, _ = self._retrieve_sheet_data(service, data_source.spreadsheet_id, range_name)
        except Exception as exc:
            logger.error(f"Failed to refresh data source {data_source.id}: {exc}")
            return (
                DataSourceRefreshStatus(
                    data_source_id=data_source.id,
                    ok=False,
                    message=f"Failed to read range {range_name}: {exc}",
                ),
                None,
            )

        valid, missing = validate_transaction_sheet_data(data)
        if not valid:
            missing_text = ", ".join(sorted(missing))
            return (
                DataSourceRefreshStatus(
                    data_source_id=data_source.id,
                    ok=False,
                    message=f"Missing required transaction columns: {missing_text}",
                ),
                None,
            )

        records = self._apply_filters(records_from_sheet_data(data), data_source)
        return (
            DataSourceRefreshStatus(
                data_source_id=data_source.id,
                ok=True,
                message=f"Loaded {len(records)} transaction rows.",
                row_count=len(records),
            ),
            records,
        )

    def validate_transaction_source(
        self, service: SheetsService, spreadsheet_id: str, sheet_name: str, range_a1: str
    ) -> tuple[bool, str]:
        """Validate a selected spreadsheet range as a Tiller transaction source."""
        data, _ = self._retrieve_sheet_data(service, spreadsheet_id, f"{sheet_name}!{range_a1}")
        valid, missing = validate_transaction_sheet_data(data)
        if valid:
            return True, "Transaction source is valid."
        return False, f"Missing required transaction columns: {', '.join(sorted(missing))}"

    def _retrieve_sheet_data(
        self, service: SheetsService, spreadsheet_id: str, range_name: str
    ) -> tuple[SheetData, list[tuple[Any, str]]]:
        if self._retrieve_sheet_data_fn is not None:
            return self._retrieve_sheet_data_fn(service, spreadsheet_id, range_name)
        from ripper.ripperlib.sheets_backend import retrieve_sheet_data

        return retrieve_sheet_data(service, spreadsheet_id, range_name)

    def _apply_filters(self, records: list[dict[str, Any]], data_source: DataSource) -> list[dict[str, Any]]:
        start_date, end_date = data_source.date_range.get_date_range()
        accounts = set(data_source.filters.get("accounts") or [])
        categories = set(data_source.filters.get("categories") or [])
        filtered = []
        for record in records:
            if not self._record_in_date_range(record, start_date, end_date):
                continue
            if accounts and str(record.get("account", "")) not in accounts:
                continue
            if categories and str(record.get("category", "")) not in categories:
                continue
            filtered.append(record)
        return filtered

    def _record_in_date_range(self, record: dict[str, Any], start_date: datetime, end_date: datetime) -> bool:
        raw_date = record.get("date")
        if raw_date is None:
            return False
        try:
            parsed = datetime.fromisoformat(str(raw_date))
        except ValueError:
            try:
                parsed = datetime.strptime(str(raw_date), "%m/%d/%Y")
            except ValueError:
                logger.debug(f"Could not parse transaction date: {raw_date}")
                return False
        return start_date <= parsed <= end_date
