"""Runtime services for dashboard data loading."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Callable, Protocol, runtime_checkable

from loguru import logger

from ripper.rippergui.dashboard.models import Dashboard, DataSource, DataSourceType
from ripper.rippergui.dashboard.models.tiller_data import parse_transaction_date
from ripper.ripperlib.auth import AuthManager
from ripper.ripperlib.defs import SheetData, SheetsService


@runtime_checkable
class SheetsServiceProvider(Protocol):
    """Structural type for anything that can build a Sheets service (e.g. ``AuthManager``)."""

    def create_sheets_service(self) -> SheetsService | None: ...


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
    # Per-data-source category classification: ``{data_source_id: {category_name: type}}``.
    # Each inner map is the authoritative ``{category: type}`` built from THAT source's own
    # spreadsheet's Tiller Categories "Type" column (keys/values lowercased). Keying by data
    # source keeps metadata scoped to its spreadsheet: two sources on different spreadsheets
    # that define the same category name with different Types must NOT be merged into one
    # global last-wins map, or one source's transactions would be classified using the other
    # spreadsheet's metadata. A source is absent from this dict when its Categories sheet is
    # unavailable/empty, in which case that widget falls back to name-based transfer
    # classification (issue #115).
    category_types: dict[str, dict[str, str]] = field(default_factory=dict)

    def has_errors(self) -> bool:
        """Return True if any refresh status failed."""
        return any(not status.ok for status in self.statuses.values())


class DashboardDataService:
    """Fetch and validate runtime data for dashboards."""

    def __init__(
        self,
        auth_manager: SheetsServiceProvider | None = None,
        retrieve_sheet_data_fn: Callable[[SheetsService, str, str], tuple[SheetData, list[tuple[Any, str]]]]
        | None = None,
        records_provider: Callable[[str, str, str], list[dict[str, Any]] | None] | None = None,
        categories_fetch_fn: Callable[[SheetsService, str], list[dict[str, Any]]] | None = None,
    ) -> None:
        """Initialise the service.

        Args:
            auth_manager: Optional auth manager; defaults to a shared singleton.
            retrieve_sheet_data_fn: Optional override for the sheet data fetch
                function, primarily used in tests.
            records_provider: Optional callable ``(spreadsheet_id, sheet_name,
                range_a1) -> list[dict] | None`` that supplies already-fetched
                records for a specific source range (e.g. from the active table
                view). The ``range_a1`` is part of the identity: two sources on
                the same tab but different ranges must not collide. When the
                provider returns a non-None value the API call is skipped and the
                provided records are used directly before ``DataSource.filters``
                (date-range / accounts / categories) are applied.
            categories_fetch_fn: Optional override for the Tiller Categories fetch,
                a callable ``(service, spreadsheet_id) -> list[dict]`` (defaults to
                :func:`ripper.ripperlib.sheets_backend.get_tiller_categories`).
                Injected/patched in tests so the category->type map is built
                without hitting the network (issue #115).
        """
        self._auth_manager = auth_manager or AuthManager()
        self._retrieve_sheet_data_fn = retrieve_sheet_data_fn
        self._records_provider = records_provider
        self._categories_fetch_fn = categories_fetch_fn

    def create_sheets_service(self) -> SheetsService | None:
        """Create an authenticated Sheets service."""
        return self._auth_manager.create_sheets_service()

    def refresh_dashboard(self, dashboard: Dashboard) -> DashboardRefreshResult:
        """Refresh all configured data sources for a dashboard."""
        result = DashboardRefreshResult()

        # Create/authenticate the Sheets service lazily: sources that can be served from
        # pre-fetched records (the provider fast path) need no auth, so a dashboard backed
        # entirely by already-loaded data refreshes even when auth is unavailable. We only
        # pay for a service on the first genuine cache miss, and reuse it thereafter.
        service_box: list[SheetsService | None] = []

        def get_service() -> SheetsService | None:
            if not service_box:
                service_box.append(self.create_sheets_service())
            return service_box[0]

        # Snapshot the data sources up front: this runs on a background worker thread while the
        # GUI-thread editor may mutate dashboard.data_sources, and iterating the live dict view
        # would risk "dictionary changed size during iteration" or a silently inconsistent result
        # (#96). The snapshot fixes exactly which sources this refresh iterates.
        snapshot = list(dashboard.data_sources.values())
        for data_source in snapshot:
            status, records = self.refresh_data_source(get_service, data_source)
            result.statuses[data_source.id] = status
            if records is not None:
                result.data[data_source.id] = records

        # Build the authoritative category->type map ONLY when a source genuinely needed the
        # API this refresh (``service_box`` populated). A dashboard served entirely from
        # pre-fetched records stays auth-free and degrades to name-based transfer
        # classification -- consulting the Categories sheet must not force authentication or
        # a network call for those (issue #115). ``service_box[0]`` may be None (auth failed);
        # ``_build_category_types`` treats that as "no categories" and returns an empty map.
        if service_box:
            result.category_types = self._build_category_types(service_box[0], snapshot)
        return result

    def _build_category_types(
        self, service: SheetsService | None, data_sources: list[DataSource]
    ) -> dict[str, dict[str, str]]:
        """Build a per-data-source ``{data_source_id: {category: type}}`` classification map.

        Each transaction source is classified using ONLY its own spreadsheet's Tiller
        Categories "Type" column, so two sources on different spreadsheets that define the
        same category name with different Types stay scoped and are never cross-classified
        (issue #115). Each distinct spreadsheet is fetched at most once and its resulting map
        shared by every source referencing it (no duplicate fetch). Keys and values are
        lowercased/stripped for case-insensitive matching in ``TillerDataProcessor``. Any
        failure (missing sheet, API error) or an empty Categories sheet degrades gracefully:
        that source is simply omitted, so its widget falls back to name-based classification --
        never a hard dependency.
        """
        if service is None:
            return {}
        per_source: dict[str, dict[str, str]] = {}
        # Cache each spreadsheet's normalized map (including empty results) so a spreadsheet
        # shared by multiple sources is fetched exactly once.
        spreadsheet_maps: dict[str, dict[str, str]] = {}
        for data_source in data_sources:
            if data_source.type != DataSourceType.TILLER_TRANSACTIONS:
                continue
            spreadsheet_id = data_source.spreadsheet_id
            if spreadsheet_id not in spreadsheet_maps:
                spreadsheet_maps[spreadsheet_id] = self._fetch_spreadsheet_category_types(service, spreadsheet_id)
            category_map = spreadsheet_maps[spreadsheet_id]
            # Omit sources with no usable metadata so the widget falls back to name-based.
            if category_map:
                per_source[data_source.id] = category_map
        return per_source

    def _fetch_spreadsheet_category_types(self, service: SheetsService, spreadsheet_id: str) -> dict[str, str]:
        """Fetch and normalize one spreadsheet's Categories into a ``{category: type}`` map.

        Returns an empty map on any failure (missing sheet, API error) so classification
        degrades to name matching rather than failing the refresh.
        """
        try:
            rows = self._fetch_categories(service, spreadsheet_id)
        except Exception as exc:
            logger.warning(f"Could not fetch Categories for {spreadsheet_id}: {exc}")
            return {}
        category_map: dict[str, str] = {}
        for row in rows or []:
            name = str(row.get("category", "")).strip().lower()
            ctype = str(row.get("type", "")).strip().lower()
            if name and ctype:
                category_map[name] = ctype
        return category_map

    def _fetch_categories(self, service: SheetsService, spreadsheet_id: str) -> list[dict[str, Any]]:
        if self._categories_fetch_fn is not None:
            return self._categories_fetch_fn(service, spreadsheet_id)
        from ripper.ripperlib.sheets_backend import get_tiller_categories

        return get_tiller_categories(service, spreadsheet_id)

    def refresh_data_source(
        self, service_provider: Callable[[], SheetsService | None], data_source: DataSource
    ) -> tuple[DataSourceRefreshStatus, list[dict[str, Any]] | None]:
        """Refresh one data source.

        ``service_provider`` is called only on a cache miss, so a source satisfied by the
        records provider never triggers authentication.
        """
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

        # Use pre-fetched records from the provider when available (e.g. the active filtered
        # table view), falling back to a fresh API call. The range_a1 is part of the identity
        # so two sources on the same tab with different ranges don't collide.
        pre_fetched: list[dict[str, Any]] | None = None
        if self._records_provider is not None:
            pre_fetched = self._records_provider(
                data_source.spreadsheet_id, data_source.sheet_name, data_source.range_a1
            )

        if pre_fetched is not None:
            records = self._apply_filters(pre_fetched, data_source)
            return (
                DataSourceRefreshStatus(
                    data_source_id=data_source.id,
                    ok=True,
                    message=f"Loaded {len(records)} transaction rows (from cache).",
                    row_count=len(records),
                ),
                records,
            )

        # Cache miss: this source genuinely needs the API, so obtain (and authenticate) the
        # service now. A global auth failure only fails the sources that actually need it.
        service = service_provider()
        if service is None:
            return (
                DataSourceRefreshStatus(
                    data_source_id=data_source.id,
                    ok=False,
                    message="Could not authenticate with Google Sheets API.",
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
        try:
            data, _ = self._retrieve_sheet_data(service, spreadsheet_id, f"{sheet_name}!{range_a1}")
        except Exception as exc:
            logger.error(f"Failed to read range for validation: {exc}")
            return False, f"Failed to read range: {exc}"
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
        # Use the single shared parser (pandas ``to_datetime``) so this service-level filter
        # and the widgets' ``TillerDataProcessor`` interpret each row's date identically (#44).
        # The parser already coerces unparseable values to None and strips any timezone.
        parsed = parse_transaction_date(record.get("date"))
        if parsed is None:
            logger.debug(f"Could not parse transaction date: {record.get('date')}")
            return False
        return start_date <= parsed <= end_date
