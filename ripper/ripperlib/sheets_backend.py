"""
This module provides backend functions for interacting with Google Sheets and Drive APIs,
caching results in a local database, and handling spreadsheet metadata and thumbnails.

Functions include:
- Fetching and retrieving spreadsheet and sheet metadata
- Downloading and caching spreadsheet thumbnails
- Fetching spreadsheet cell data

All API interactions are logged, and errors are handled gracefully.
"""

# Standard library imports
import urllib.request
from urllib.error import URLError

# Third-party imports
from beartype.typing import Any, cast
from googleapiclient.errors import HttpError
from loguru import logger

# Local imports
from ripper.ripperlib.database import Db
from ripper.ripperlib.defs import (
    DriveService,
    LoadSource,
    SheetData,
    SheetProperties,
    SheetsService,
    SpreadsheetProperties,
)
from ripper.ripperlib.range_manager import build_a1_range, split_sheet_and_range


def fetch_sheets_of_spreadsheet(service: SheetsService, spreadsheet_id: str) -> list[SheetProperties]:
    """
    Fetches the list of sheets of a spreadsheet from the Google Sheets API.

    Args:
        service (SheetsService): Authenticated Google Sheets API service.
        spreadsheet_id (str): The ID of the spreadsheet to fetch sheets from.

    Returns:
        list[SheetProperties]: List of sheet properties, or an empty list if an error occurs.

    Raises:
        Any exception raised by the SheetsService if not caught (e.g., authentication errors).
    """
    try:
        # Create a Sheets API instance
        sheets = service.spreadsheets()
        result = sheets.get(spreadsheetId=spreadsheet_id, fields=SheetProperties.api_fields()).execute()
        return SheetProperties.from_api_result(result)

    except HttpError as error:
        logger.error(f"An error occurred reading sheet metadata for spreadsheet {spreadsheet_id}: {error}")
        return []


def retrieve_sheets_of_spreadsheet(service: SheetsService, spreadsheet_id: str) -> list[SheetProperties]:
    """
    Retrieves the list of sheets of a spreadsheet from the database if available,
    otherwise fetches from the API and caches the result.

    Args:
        service (SheetsService): Authenticated Google Sheets API service.
        spreadsheet_id (str): The ID of the spreadsheet to fetch sheets from.

    Returns:
        list[SheetProperties]: List of sheet properties.

    Raises:
        Any exception raised by the database or SheetsService if not caught.
    """
    sheets = Db.get_sheet_properties_of_spreadsheet(spreadsheet_id)
    if len(sheets) > 0:
        for sheet in sheets:
            sheet.load_source = LoadSource.DATABASE
        return sheets
    else:
        sheets = fetch_sheets_of_spreadsheet(service, spreadsheet_id)
        for sheet in sheets:
            sheet.load_source = LoadSource.API
        Db.store_sheet_properties(spreadsheet_id, sheets)
        return sheets


# Google Drive thumbnail downloads are best-effort; cap how long a hung server can block.
THUMBNAIL_TIMEOUT_SECONDS = 10


def fetch_thumbnail(url: str) -> bytes:
    """
    Download thumbnail image data from an HTTPS URL.

    The Drive ``thumbnailLink`` is always HTTPS; other schemes (``file://``, ``http://``) are
    refused. Any failure — non-HTTPS URL, connection/read timeout, HTTP or network error — is
    logged and returns empty ``bytes`` rather than raising, so callers can fall back to a
    default thumbnail.

    Args:
        url (str): HTTPS URL to download the thumbnail from.

    Returns:
        bytes: The thumbnail image data, or an empty bytes object if the download failed.
    """
    if not url.startswith("https://"):
        logger.warning(f"Refusing to fetch thumbnail from non-HTTPS URL '{url}'")
        return b""
    try:
        with urllib.request.urlopen(url, timeout=THUMBNAIL_TIMEOUT_SECONDS) as response:
            return cast(bytes, response.read())
    except (URLError, TimeoutError, ValueError) as e:
        # URLError covers HTTPError and most socket errors; TimeoutError covers a read timeout;
        # ValueError covers an unsupported/malformed URL.
        logger.error(f"Error downloading thumbnail from url '{url}': {e}")
        return b""


def retrieve_thumbnail(spreadsheet_id: str, thumbnail_link: str) -> tuple[bytes, LoadSource]:
    """
    Retrieves the thumbnail of a spreadsheet from the database if available,
    otherwise downloads it and caches the result.

    A failed download (empty result) is NOT cached: storing ``b""`` would both pollute the DB and,
    because it reads back as falsy, force a re-download on every call anyway. Non-empty results are
    cached as before.

    Args:
        spreadsheet_id (str): The ID of the spreadsheet.
        thumbnail_link (str): The URL to download the thumbnail from if not cached.

    Returns:
        tuple[bytes, LoadSource]: The thumbnail data and the source (DATABASE or API).

    Raises:
        Any exception raised by the database if not caught.
    """
    thumbnail = Db.get_spreadsheet_thumbnail(spreadsheet_id)
    if thumbnail:
        logger.debug(f"Thumbnail for spreadsheet {spreadsheet_id} found in database. Returning cached thumbnail data.")
        return thumbnail, LoadSource.DATABASE

    logger.debug(f"Thumbnail for spreadsheet {spreadsheet_id} not found in database. Downloading from url.")
    thumbnail = fetch_thumbnail(thumbnail_link)
    if thumbnail:
        Db.store_spreadsheet_thumbnail(spreadsheet_id, thumbnail)
    else:
        logger.debug(f"No thumbnail data for spreadsheet {spreadsheet_id}; not caching an empty result.")
    return thumbnail, LoadSource.API


def fetch_spreadsheets(service: DriveService) -> list[SpreadsheetProperties]:
    """
    Fetches the list of spreadsheets from the Google Drive API.

    Args:
        service (DriveService): Authenticated Google Drive API service.

    Returns:
        list[SpreadsheetProperties]: List of spreadsheet properties, or an empty list if an error occurs.

    Raises:
        Any exception raised by the DriveService if not caught (e.g., authentication errors).
    """
    try:
        # Use the Drive API to list files with additional fields
        page_token = None
        files = []

        while True:
            response = (
                service.files()
                .list(
                    q="mimeType='application/vnd.google-apps.spreadsheet'",
                    spaces="drive",
                    fields=f"nextPageToken, {SpreadsheetProperties.api_fields()}",
                    pageToken=page_token,
                )
                .execute()
            )
            files.extend(response.get("files", []))
            page_token = response.get("nextPageToken", None)
            if page_token is None:
                break

        logger.debug(f"Retrieved {len(files)} spreadsheets from Google Drive")
        properties_list = []
        for file in files:
            properties_list.append(SpreadsheetProperties(file))

        return properties_list

    except HttpError as error:
        logger.error(f"An error occurred fetching sheets list: {error}")
        return []


def retrieve_spreadsheets(drive_service: DriveService) -> list[SpreadsheetProperties]:
    """
    Retrieves the list of spreadsheets from the Google Drive API and stores relevant information in the database.

    Args:
        drive_service (DriveService): Authenticated Google Drive API service.

    Returns:
        list[SpreadsheetProperties]: List of spreadsheet properties, or an empty list if an error occurs.

    Raises:
        ValueError: If a spreadsheet property is missing an ID.
        Any exception raised by the database or DriveService if not caught.
    """
    properties_list = fetch_spreadsheets(drive_service)

    if len(properties_list) == 0:
        logger.error("Failed to fetch sheets list.")
        return []

    # Store the spreadsheet properties in the database
    store_count = 0
    for spreadsheet_properties in properties_list:
        logger.debug(f"Storing spreadsheet properties for {spreadsheet_properties.to_dict()}")
        spreadsheet_id = spreadsheet_properties.id
        if not spreadsheet_id:
            raise ValueError(f"No spreadsheet ID found for a spreadsheet. Info: {spreadsheet_properties.to_dict()}")
        Db.store_spreadsheet_properties(spreadsheet_id, spreadsheet_properties)
        store_count += 1
        logger.debug(f"Stored spreadsheet properties for {spreadsheet_id}")

    # Log the number of spreadsheets stored
    if store_count == len(properties_list):
        logger.debug(f"Successfully fetched and stored {store_count} spreadsheets.")
    else:
        logger.error(f"Failed to store {len(properties_list) - store_count}/{len(properties_list)} spreadsheets.")
    return properties_list


def fetch_data_from_spreadsheet(service: SheetsService, spreadsheet_id: str, range_name: str) -> SheetData:
    """
    Fetches data from specific cells in the spreadsheet.

    Args:
        service (SheetsService): Authenticated Google Sheets API service.
        spreadsheet_id (str): The ID of the spreadsheet to read from.
        range_name (str): The A1 notation of the range to read (includes sheet name and cell range).

    Returns:
        SheetData: A list of lists containing the values, or an empty list if no data was found or an error occurred.

    Raises:
        Any exception raised by the SheetsService if not caught (e.g., authentication errors).
    """
    try:
        # Create a Sheets API instance
        sheets = service.spreadsheets()

        # Request to get values from the specified range (includes sheet name and cell range) in the Google Sheet
        result: dict[str, Any] = sheets.values().get(spreadsheetId=spreadsheet_id, range=range_name).execute()

        # Extract the values from the response
        values = cast(SheetData, result.get("values", []))

        # If the spreadsheet is empty, log an info message and return an empty list
        if not values:
            logger.warning(f"No data found in spreadsheet {spreadsheet_id} for range '{range_name}'.")
            return []

        # Log the number of rows found
        logger.debug(f"Found {len(values)} rows of data in spreadsheet {spreadsheet_id} for range '{range_name}'")
        return values

    except HttpError as error:
        logger.error(
            f"""An error occurred reading spreadsheet data for spreadsheet {spreadsheet_id} and range '{range_name}':
            {error}"""
        )
        return []


def retrieve_sheet_data_for(
    service: SheetsService, spreadsheet_id: str, sheet_name: str, range_a1: str | None = None
) -> tuple[SheetData, list[tuple[LoadSource, str]]]:
    """
    Retrieve sheet data for a sheet name and optional cell range supplied SEPARATELY.

    This is the preferred entry point. Passing the title and range separately preserves
    whether a range was supplied, so a whole-sheet load of a title that itself contains
    ``!`` (e.g. ``Q1!Actuals``) is treated as the whole-sheet reference ``'Q1!Actuals'``
    rather than being misparsed as sheet ``Q1`` + range ``Actuals``. The title is quoted at
    the API boundary (see :func:`ripper.ripperlib.range_manager.build_a1_range`).

    Args:
        service: Authenticated Google Sheets API service
        spreadsheet_id: The ID of the spreadsheet to read from
        sheet_name: The (unquoted) sheet title
        range_a1: The cell-range portion (e.g. ``A1:E10``); falsy means the whole sheet

    Returns:
        Tuple of (sheet_data, range_sources); see the caching logic in
        :class:`ripper.ripperlib.sheet_data_cache.SheetDataCache`.
    """
    if not range_a1:
        try:
            # Whole-sheet read: route through the cache so repeated Tiller reads are cached (#144).
            # When the sheet's grid width is known, the cache expresses this as a concrete
            # full-width open-ended range and reuses #68's store+reuse without reintroducing the
            # #104 column truncation; otherwise it falls back to a direct unbounded read.
            from ripper.ripperlib.sheet_data_cache import SheetDataCache

            return SheetDataCache().get_whole_sheet_data(service, spreadsheet_id, sheet_name)

        except Exception as e:
            logger.error(f"Error retrieving whole sheet {sheet_name!r}: {e}; falling back to a direct read")
            # Fallback: direct unbounded whole-sheet reference (quoted title cannot truncate).
            whole_sheet = build_a1_range(sheet_name, None)
            return fetch_data_from_spreadsheet(service, spreadsheet_id, whole_sheet), [(LoadSource.API, whole_sheet)]

    try:
        # Use the sheet data cache (it quotes the title at the API boundary).
        from ripper.ripperlib.sheet_data_cache import SheetDataCache

        cache = SheetDataCache()

        return cache.get_sheet_data(service, spreadsheet_id, sheet_name, range_a1)

    except Exception as e:
        logger.error(f"Error in retrieve_sheet_data for {sheet_name!r}!{range_a1!r}: {e}")
        # Fallback to a direct API call, quoting the title so special-character names resolve.
        fallback_range = build_a1_range(sheet_name, range_a1)
        return fetch_data_from_spreadsheet(service, spreadsheet_id, fallback_range), [(LoadSource.API, fallback_range)]


def retrieve_sheet_data(
    service: SheetsService, spreadsheet_id: str, range_name: str
) -> tuple[SheetData, list[tuple[LoadSource, str]]]:
    """
    Retrieve sheet data from a combined ``Sheet!Range`` string.

    Convenience wrapper around :func:`retrieve_sheet_data_for` for callers that already hold a
    combined range string (e.g. dashboard/Tiller fetches). The string is parsed by
    :func:`ripper.ripperlib.range_manager.split_sheet_and_range`, which handles single-quoted
    titles (including titles that contain ``!``) and dequotes the title so it is quoted exactly
    once at the API boundary. The one still-ambiguous case is an *unquoted, whole-sheet* title
    that contains ``!`` (no range to anchor the split); such callers should use
    :func:`retrieve_sheet_data_for` with the title and range separately.

    Args:
        service: Authenticated Google Sheets API service
        spreadsheet_id: The ID of the spreadsheet to read from
        range_name: The A1 notation of the range to read (includes sheet name and cell range)

    Returns:
        Tuple of (sheet_data, range_sources).
    """
    # Parse into an unquoted title + optional range. Handles single-quoted titles (which may
    # already appear in valid A1, e.g. "'Monthly Budget'!A1:B2") so the title is not double-quoted
    # when retrieve_sheet_data_for re-quotes it at the API boundary.
    sheet_name, range_part = split_sheet_and_range(range_name)
    return retrieve_sheet_data_for(service, spreadsheet_id, sheet_name, range_part)


def _read_tiller_rows(service: Any, spreadsheet_id: str, sheet_name: str, description: str) -> list[dict[str, Any]]:
    """Read a whole Tiller sheet and map each data row onto its normalized header keys.

    The sheet is requested WITHOUT a cell range, so the API returns every populated column.
    A bounded range (the former ``A:Z``) silently dropped column 27 onwards — routine for
    Tiller sheets customized with tags, splits, notes, or per-month budget columns — with no
    header, no cell, and no log line to show it had happened (#104).

    Args:
        service: Google Sheets API service instance
        spreadsheet_id: The ID of the spreadsheet
        sheet_name: The (unquoted) sheet title to read in full
        description: Human-readable label for this sheet, used in error logs

    Returns:
        One dictionary per data row, keyed by normalized header; empty if the sheet has no
        data rows or the read failed.
    """
    try:
        # No range: a whole-sheet reference cannot truncate wide sheets. retrieve_sheet_data_for
        # quotes the title at the API boundary, so titles containing '!' stay unambiguous.
        data, _ = retrieve_sheet_data_for(service, spreadsheet_id, sheet_name)
        if not data or len(data) < 2:
            return []

        headers = [str(cell).strip().lower().replace(" ", "_") for cell in data[0]]
        rows: list[dict[str, Any]] = []

        for row in data[1:]:
            entry = {}
            for i, header in enumerate(headers):
                if i < len(row):
                    entry[header] = row[i]
            rows.append(entry)

        return rows
    except Exception as e:
        logger.error(f"Error getting Tiller {description}: {e}")
        return []


def get_tiller_transactions(
    service: Any,
    spreadsheet_id: str,
    sheet_name: str = "Transactions",
) -> list[dict[str, Any]]:
    """Get transaction data from Tiller spreadsheet.

    Retrieves all rows and all columns from the configured sheet and returns them as a list
    of dictionaries with normalized header keys. Date range and account/category filtering is
    handled by the caller (e.g. ``DashboardDataService._apply_filters``).

    Args:
        service: Google Sheets API service instance
        spreadsheet_id: The ID of the spreadsheet
        sheet_name: Name of the transactions sheet (default: "Transactions")

    Returns:
        List of transaction dictionaries
    """
    return _read_tiller_rows(service, spreadsheet_id, sheet_name, "transactions")


def get_tiller_categories(service: Any, spreadsheet_id: str, sheet_name: str = "Categories") -> list[dict[str, Any]]:
    """Get category data from Tiller spreadsheet.

    Args:
        service: Google Sheets API service instance
        spreadsheet_id: The ID of the spreadsheet
        sheet_name: Name of the categories sheet (default: "Categories")

    Returns:
        List of category dictionaries
    """
    return _read_tiller_rows(service, spreadsheet_id, sheet_name, "categories")


def get_tiller_budget(service: Any, spreadsheet_id: str, sheet_name: str = "Budget") -> list[dict[str, Any]]:
    """Get budget data from Tiller spreadsheet.

    Args:
        service: Google Sheets API service instance
        spreadsheet_id: The ID of the spreadsheet
        sheet_name: Name of the budget sheet (default: "Budget")

    Returns:
        List of budget dictionaries
    """
    return _read_tiller_rows(service, spreadsheet_id, sheet_name, "budget")
