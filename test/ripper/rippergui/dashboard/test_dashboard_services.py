"""Tests for dashboard data refresh services."""

from datetime import datetime
from unittest.mock import MagicMock

from ripper.rippergui.dashboard.models import Dashboard, DataSource, DataSourceType, DateRange, DateRangePreset
from ripper.rippergui.dashboard.services import DashboardDataService, validate_transaction_sheet_data


class FakeAuthManager:
    def __init__(self, service=None):
        self.service = service

    def create_sheets_service(self):
        return self.service


def _fake_sheets_service():
    """A stand-in Sheets service that satisfies the SheetsService protocol."""
    return MagicMock()


def make_transaction_source(source_id="source-1", spreadsheet_id="spreadsheet-1"):
    return DataSource(
        id=source_id,
        type=DataSourceType.TILLER_TRANSACTIONS,
        name="Transactions",
        spreadsheet_id=spreadsheet_id,
        sheet_name="Transactions",
        range_a1="A1:E10",
        date_range=DateRange(
            DateRangePreset.CUSTOM,
            start_date=datetime(2024, 1, 1),
            end_date=datetime(2024, 12, 31, 23, 59, 59),
        ),
    )


def test_validate_transaction_sheet_data_accepts_required_columns():
    valid, missing = validate_transaction_sheet_data(
        [["Date", "Description", "Category", "Amount", "Account"], ["2024-01-01", "Coffee", "Food", "-5", "Visa"]]
    )

    assert valid
    assert missing == set()


def test_validate_transaction_sheet_data_rejects_missing_columns():
    valid, missing = validate_transaction_sheet_data([["Date", "Description"], ["2024-01-01", "Coffee"]])

    assert not valid
    assert missing == {"account", "amount", "category"}


def test_refresh_dashboard_snapshots_data_sources_against_concurrent_mutation():
    """refresh_dashboard iterates a snapshot so a concurrent add can't corrupt iteration (#96).

    The background refresh worker iterates the dashboard's data sources while the GUI-thread editor
    can mutate the same dict. Iterating a snapshot means a mutation mid-refresh neither raises
    ``RuntimeError: dictionary changed size during iteration`` nor changes what was iterated.
    """
    dashboard = Dashboard.create_new("Finance")
    dashboard.add_data_source(make_transaction_source("source-1"))
    dashboard.add_data_source(make_transaction_source("source-2"))

    seen: list[str] = []

    def records_provider(spreadsheet_id, sheet_name, range_a1):
        seen.append(range_a1)
        # Simulate the editor mutating the live dict while the refresh is iterating it.
        dashboard.add_data_source(make_transaction_source(f"injected-{len(seen)}"))
        return []

    service = DashboardDataService(records_provider=records_provider)

    result = service.refresh_dashboard(dashboard)  # must not raise despite the concurrent adds

    # Exactly the two sources present when the refresh began were iterated; the injected ones were not.
    assert set(result.statuses) == {"source-1", "source-2"}


def test_refresh_dashboard_reports_missing_auth():
    dashboard = Dashboard.create_new("Finance")
    dashboard.add_data_source(make_transaction_source())

    result = DashboardDataService(FakeAuthManager()).refresh_dashboard(dashboard)

    assert result.has_errors()
    assert result.statuses["source-1"].message == "Could not authenticate with Google Sheets API."


def test_refresh_dashboard_fetches_transaction_source_once():
    dashboard = Dashboard.create_new("Finance")
    dashboard.add_data_source(make_transaction_source())
    calls = []

    def fake_retrieve_sheet_data(service, spreadsheet_id, range_name):
        calls.append((spreadsheet_id, range_name))
        return (
            [
                ["Date", "Description", "Category", "Amount", "Account"],
                ["2024-01-01", "Coffee", "Food", "-5", "Visa"],
                ["2025-01-01", "Old", "Food", "-10", "Visa"],
            ],
            [],
        )

    result = DashboardDataService(
        FakeAuthManager(service=_fake_sheets_service()), retrieve_sheet_data_fn=fake_retrieve_sheet_data
    ).refresh_dashboard(dashboard)

    assert calls == [("spreadsheet-1", "Transactions!A1:E10")]
    assert result.statuses["source-1"].ok
    assert result.statuses["source-1"].row_count == 1
    assert result.data["source-1"][0]["description"] == "Coffee"


def test_refresh_distinguishes_sources_on_same_tab_by_range():
    """Two sources on the same tab but different ranges must get their own records (#73, bug A)."""
    dashboard = Dashboard.create_new("Finance")
    ds_a = make_transaction_source("source-a")
    ds_b = make_transaction_source("source-b")
    ds_b.range_a1 = "G1:K10"
    dashboard.add_data_source(ds_a)
    dashboard.add_data_source(ds_b)

    records_by_range = {
        "A1:E10": [
            {"date": "2024-06-01", "description": "A-coffee", "category": "Food", "amount": "-5", "account": "Visa"}
        ],
        "G1:K10": [
            {"date": "2024-06-02", "description": "B-lunch", "category": "Food", "amount": "-9", "account": "Visa"}
        ],
    }
    seen_args = []

    def provider(spreadsheet_id, sheet_name, range_a1):
        seen_args.append((spreadsheet_id, sheet_name, range_a1))
        return records_by_range[range_a1]

    result = DashboardDataService(
        FakeAuthManager(service=_fake_sheets_service()), records_provider=provider
    ).refresh_dashboard(dashboard)

    assert ("spreadsheet-1", "Transactions", "A1:E10") in seen_args
    assert ("spreadsheet-1", "Transactions", "G1:K10") in seen_args
    assert result.data["source-a"][0]["description"] == "A-coffee"
    assert result.data["source-b"][0]["description"] == "B-lunch"


def test_refresh_succeeds_from_provider_without_creating_service():
    """Sources satisfiable from pre-fetched records refresh without authenticating (#73, bug B)."""
    dashboard = Dashboard.create_new("Finance")
    dashboard.add_data_source(make_transaction_source())

    class CountingAuth:
        def __init__(self):
            self.calls = 0

        def create_sheets_service(self):
            self.calls += 1
            return None

    auth = CountingAuth()
    records = [{"date": "2024-06-01", "description": "Coffee", "category": "Food", "amount": "-5", "account": "Visa"}]

    result = DashboardDataService(auth, records_provider=lambda s, sh, r: records).refresh_dashboard(dashboard)

    assert result.statuses["source-1"].ok
    assert result.statuses["source-1"].row_count == 1
    # No service was created because the provider satisfied the source.
    assert auth.calls == 0


# --------------------------------------------------------------------------- #
# Category Type metadata classifier wiring (issue #115)
# --------------------------------------------------------------------------- #
def _fake_retrieve_transactions(service, spreadsheet_id, range_name):
    return (
        [
            ["Date", "Description", "Category", "Amount", "Account"],
            ["2024-01-01", "Coffee", "Food", "-5", "Visa"],
        ],
        [],
    )


def test_refresh_dashboard_builds_category_types_from_injected_fetch():
    """The service builds a normalized {category: type} map keyed by data-source id."""
    dashboard = Dashboard.create_new("Finance")
    dashboard.add_data_source(make_transaction_source())

    categories_calls = []

    def fake_categories_fetch(service, spreadsheet_id):
        categories_calls.append(spreadsheet_id)
        return [
            {"category": "Food", "type": "Expense"},
            {"category": "Move Money", "type": "Transfer"},
            {"category": "Paycheck", "type": "Income"},
        ]

    result = DashboardDataService(
        FakeAuthManager(service=_fake_sheets_service()),
        retrieve_sheet_data_fn=_fake_retrieve_transactions,
        categories_fetch_fn=fake_categories_fetch,
    ).refresh_dashboard(dashboard)

    assert categories_calls == ["spreadsheet-1"]
    # Maps are keyed by data-source id; keys/values normalized to lowercase.
    assert result.category_types == {"source-1": {"food": "expense", "move money": "transfer", "paycheck": "income"}}


def test_refresh_dashboard_keeps_same_category_name_scoped_per_spreadsheet():
    """Reviewer scenario (a): two sources on DIFFERENT spreadsheets both define 'Adjustment'
    with different Types. The result must carry SEPARATE per-source maps, never a merged
    last-wins entry (#115 regression)."""
    dashboard = Dashboard.create_new("Finance")
    dashboard.add_data_source(make_transaction_source("source-a", spreadsheet_id="spreadsheet-a"))
    dashboard.add_data_source(make_transaction_source("source-b", spreadsheet_id="spreadsheet-b"))

    categories_by_spreadsheet = {
        "spreadsheet-a": [{"category": "Adjustment", "type": "Expense"}],
        "spreadsheet-b": [{"category": "Adjustment", "type": "Income"}],
    }

    def fake_categories_fetch(service, spreadsheet_id):
        return categories_by_spreadsheet[spreadsheet_id]

    result = DashboardDataService(
        FakeAuthManager(service=_fake_sheets_service()),
        retrieve_sheet_data_fn=_fake_retrieve_transactions,
        categories_fetch_fn=fake_categories_fetch,
    ).refresh_dashboard(dashboard)

    # Each source keeps its OWN spreadsheet's Type for the shared category name.
    assert result.category_types["source-a"] == {"adjustment": "expense"}
    assert result.category_types["source-b"] == {"adjustment": "income"}


def test_per_source_maps_classify_shared_category_name_independently():
    """Reviewer scenario (b): an 'Adjustment' transaction under source A (Type=Expense) counts
    as spending, while the same-named category under source B (Type=Income) is excluded from
    spending -- because each is classified by ITS OWN spreadsheet's map."""
    from ripper.rippergui.dashboard.models.tiller_data import TillerDataProcessor

    dashboard = Dashboard.create_new("Finance")
    dashboard.add_data_source(make_transaction_source("source-a", spreadsheet_id="spreadsheet-a"))
    dashboard.add_data_source(make_transaction_source("source-b", spreadsheet_id="spreadsheet-b"))

    categories_by_spreadsheet = {
        "spreadsheet-a": [{"category": "Adjustment", "type": "Expense"}],
        "spreadsheet-b": [{"category": "Adjustment", "type": "Income"}],
    }

    result = DashboardDataService(
        FakeAuthManager(service=_fake_sheets_service()),
        retrieve_sheet_data_fn=_fake_retrieve_transactions,
        categories_fetch_fn=lambda service, spreadsheet_id: categories_by_spreadsheet[spreadsheet_id],
    ).refresh_dashboard(dashboard)

    txn = [{"date": "2024-06-01", "description": "Adj", "category": "Adjustment", "amount": -20.0, "account": "Visa"}]

    # Source A: Adjustment is an Expense -> counted as spending.
    proc_a = TillerDataProcessor(txn, category_types=result.category_types["source-a"])
    assert proc_a.get_category_breakdown() == [{"category": "Adjustment", "amount": 20.0}]

    # Source B: Adjustment is Income -> excluded from spending.
    proc_b = TillerDataProcessor(txn, category_types=result.category_types["source-b"])
    assert proc_b.get_category_breakdown() == []


def test_refresh_dashboard_mixed_sources_one_without_categories_falls_back():
    """Reviewer scenario (c): a source whose spreadsheet has no/empty Categories is simply
    absent from the per-source map (widget falls back to name-based), while a sibling source
    with categories still gets its map -- no crash."""
    dashboard = Dashboard.create_new("Finance")
    dashboard.add_data_source(make_transaction_source("source-a", spreadsheet_id="spreadsheet-a"))
    dashboard.add_data_source(make_transaction_source("source-b", spreadsheet_id="spreadsheet-b"))

    categories_by_spreadsheet = {
        "spreadsheet-a": [{"category": "Food", "type": "Expense"}],
        "spreadsheet-b": [],  # no Categories sheet content
    }

    result = DashboardDataService(
        FakeAuthManager(service=_fake_sheets_service()),
        retrieve_sheet_data_fn=_fake_retrieve_transactions,
        categories_fetch_fn=lambda service, spreadsheet_id: categories_by_spreadsheet[spreadsheet_id],
    ).refresh_dashboard(dashboard)

    assert result.category_types == {"source-a": {"food": "expense"}}
    assert "source-b" not in result.category_types  # falls back to name-based
    assert result.statuses["source-a"].ok
    assert result.statuses["source-b"].ok


def test_refresh_dashboard_shared_spreadsheet_fetches_once_and_shares_map():
    """Reviewer scenario (d): two sources on the SAME spreadsheet each get that spreadsheet's
    map, fetched only once (no duplicate-fetch)."""
    dashboard = Dashboard.create_new("Finance")
    dashboard.add_data_source(make_transaction_source("source-a", spreadsheet_id="spreadsheet-shared"))
    dashboard.add_data_source(make_transaction_source("source-b", spreadsheet_id="spreadsheet-shared"))

    categories_calls = []

    def fake_categories_fetch(service, spreadsheet_id):
        categories_calls.append(spreadsheet_id)
        return [{"category": "Food", "type": "Expense"}]

    result = DashboardDataService(
        FakeAuthManager(service=_fake_sheets_service()),
        retrieve_sheet_data_fn=_fake_retrieve_transactions,
        categories_fetch_fn=fake_categories_fetch,
    ).refresh_dashboard(dashboard)

    # Fetched once for the shared spreadsheet, but both sources carry the map.
    assert categories_calls == ["spreadsheet-shared"]
    assert result.category_types["source-a"] == {"food": "expense"}
    assert result.category_types["source-b"] == {"food": "expense"}


def test_refresh_dashboard_degrades_to_empty_map_on_missing_categories_sheet():
    """A missing/empty Categories sheet degrades gracefully to name-based (no crash)."""
    dashboard = Dashboard.create_new("Finance")
    dashboard.add_data_source(make_transaction_source())

    result = DashboardDataService(
        FakeAuthManager(service=_fake_sheets_service()),
        retrieve_sheet_data_fn=_fake_retrieve_transactions,
        categories_fetch_fn=lambda service, spreadsheet_id: [],
    ).refresh_dashboard(dashboard)

    assert result.category_types == {}
    assert result.statuses["source-1"].ok  # transactions still refreshed fine


def test_refresh_dashboard_tolerates_categories_fetch_errors():
    """An exception fetching the Categories sheet must not fail the whole refresh."""
    dashboard = Dashboard.create_new("Finance")
    dashboard.add_data_source(make_transaction_source())

    def boom(service, spreadsheet_id):
        raise RuntimeError("categories unavailable")

    result = DashboardDataService(
        FakeAuthManager(service=_fake_sheets_service()),
        retrieve_sheet_data_fn=_fake_retrieve_transactions,
        categories_fetch_fn=boom,
    ).refresh_dashboard(dashboard)

    assert result.category_types == {}
    assert result.statuses["source-1"].ok


def test_refresh_from_provider_does_not_fetch_categories_or_authenticate():
    """A fully-cached dashboard stays auth-free: no service, no Categories fetch (#115 guard)."""
    dashboard = Dashboard.create_new("Finance")
    dashboard.add_data_source(make_transaction_source())

    class CountingAuth:
        def __init__(self):
            self.calls = 0

        def create_sheets_service(self):
            self.calls += 1
            return None

    auth = CountingAuth()
    categories_calls = []
    records = [{"date": "2024-06-01", "description": "Coffee", "category": "Food", "amount": "-5", "account": "Visa"}]

    result = DashboardDataService(
        auth,
        records_provider=lambda s, sh, r: records,
        categories_fetch_fn=lambda service, spreadsheet_id: categories_calls.append(spreadsheet_id) or [],
    ).refresh_dashboard(dashboard)

    assert result.statuses["source-1"].ok
    assert auth.calls == 0  # provider satisfied the source; no auth
    assert categories_calls == []  # and no Categories fetch was attempted
    assert result.category_types == {}


def test_refresh_dashboard_reports_unsupported_source():
    dashboard = Dashboard.create_new("Finance")
    dashboard.add_data_source(
        DataSource(
            id="budget-1",
            type=DataSourceType.TILLER_BUDGET,
            name="Budget",
            spreadsheet_id="spreadsheet-1",
            sheet_name="Budget",
            range_a1="A1:E10",
            date_range=DateRange(DateRangePreset.YEAR_TO_DATE),
        )
    )

    result = DashboardDataService(FakeAuthManager(service=_fake_sheets_service())).refresh_dashboard(dashboard)

    assert result.statuses["budget-1"].unsupported
    assert not result.statuses["budget-1"].ok


# --------------------------------------------------------------------------- #
# Date-range filtering (single, shared parser) -- issue #44
# --------------------------------------------------------------------------- #
def _service() -> DashboardDataService:
    return DashboardDataService(FakeAuthManager())


def test_record_in_date_range_includes_transaction_on_custom_end_day():
    """A transaction dated on the CUSTOM end date is included (end-of-day fix, #44).

    The stored ``end_date`` is a bare date (midnight). Because ``get_date_range``
    now extends CUSTOM to end-of-day, a same-day transaction with any time-of-day
    falls inside the range.
    """
    start, end = DateRange(
        DateRangePreset.CUSTOM,
        start_date=datetime(2024, 1, 1),
        end_date=datetime(2024, 3, 31),
    ).get_date_range()

    record = {"date": "2024-03-31", "amount": "-5", "account": "Visa", "category": "Food"}
    assert _service()._record_in_date_range(record, start, end) is True


def test_record_in_date_range_accepts_lenient_formats_the_old_parser_dropped():
    """The service now parses date formats the old strict parser silently dropped (#44).

    ``2024/01/15`` is neither ISO (``fromisoformat``) nor ``%m/%d/%Y``, so the
    previous hand-rolled parser dropped it while the widgets' pandas parser kept
    it -- the two layers disagreed on the same row. With a single shared pandas
    parser both agree, and the row is included when it is in range.
    """
    start = datetime(2024, 1, 1)
    end = datetime(2024, 12, 31, 23, 59, 59)
    record = {"date": "2024/01/15", "amount": "-5", "account": "Visa", "category": "Food"}

    assert _service()._record_in_date_range(record, start, end) is True


def test_record_in_date_range_and_processor_agree_on_boundary_row():
    """The service filter and the widgets' processor parse the same row identically (#44)."""
    from ripper.rippergui.dashboard.models.tiller_data import TillerDataProcessor, parse_transaction_date

    raw = "2024/01/15"
    parsed = parse_transaction_date(raw)
    assert parsed == datetime(2024, 1, 15)

    processed = TillerDataProcessor([{"date": raw, "amount": -5.0, "category": "Food", "account": "Visa"}])
    assert processed.df["date"].iloc[0].to_pydatetime() == datetime(2024, 1, 15)


def test_record_in_date_range_drops_unparseable_and_missing_dates():
    start = datetime(2024, 1, 1)
    end = datetime(2024, 12, 31, 23, 59, 59)
    service = _service()

    assert service._record_in_date_range({"date": "not-a-date"}, start, end) is False
    assert service._record_in_date_range({"date": ""}, start, end) is False
    assert service._record_in_date_range({"date": None}, start, end) is False
    assert service._record_in_date_range({}, start, end) is False


def test_record_in_date_range_coerces_timezone_aware_dates():
    start = datetime(2024, 1, 1)
    end = datetime(2024, 12, 31, 23, 59, 59)
    record = {"date": "2024-06-01T12:00:00+05:00"}
    assert _service()._record_in_date_range(record, start, end) is True
