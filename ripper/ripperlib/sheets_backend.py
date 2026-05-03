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


def fetch_thumbnail(url: str) -> bytes:
    """
    Download thumbnail image data from a URL.

    Args:
        url (str): URL to download the thumbnail from.

    Returns:
        bytes: The thumbnail image data, or an empty bytes object if download failed.

    Raises:
        Any exception raised by urllib.request.urlopen if not caught (e.g., invalid URL, network issues).
    """
    try:
        with urllib.request.urlopen(url) as response:
            return cast(bytes, response.read())
    except URLError as e:
        logger.error(f"Error downloading thumbnail from url '{url}': {e}")
        return b""


def retrieve_thumbnail(spreadsheet_id: str, thumbnail_link: str) -> tuple[bytes, LoadSource]:
    """
    Retrieves the thumbnail of a spreadsheet from the database if available,
    otherwise downloads it and caches the result.

    Args:
        spreadsheet_id (str): The ID of the spreadsheet.
        thumbnail_link (str): The URL to download the thumbnail from if not cached.

    Returns:
        tuple[bytes, LoadSource]: The thumbnail data and the source (DATABASE or API).

    Raises:
        Any exception raised by the database or fetch_thumbnail if not caught.
    """
    thumbnail = Db.get_spreadsheet_thumbnail(spreadsheet_id)
    if thumbnail:
        logger.debug(f"Thumbnail for spreadsheet {spreadsheet_id} found in database. Returning cached thumbnail data.")
        return thumbnail, LoadSource.DATABASE
    else:
        logger.debug(f"Thumbnail for spreadsheet {spreadsheet_id} not found in database. Downloading from url.")
        thumbnail = fetch_thumbnail(thumbnail_link)
        Db.store_spreadsheet_thumbnail(spreadsheet_id, thumbnail)
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


def retrieve_sheet_data(
    service: SheetsService, spreadsheet_id: str, range_name: str
) -> tuple[SheetData, list[tuple[LoadSource, str]]]:
    """
    Retrieve sheet data from cache or API with intelligent caching.

    This function implements smart caching logic:
    1. Check if the exact range or a super-range is cached
    2. For sub-ranges, return subset from cache
    3. For overlapping ranges, combine cached data with API calls for missing parts
    4. For completely new ranges, fetch from API and cache the result

    Args:
        service: Authenticated Google Sheets API service
        spreadsheet_id: The ID of the spreadsheet to read from
        range_name: The A1 notation of the range to read (includes sheet name and cell range)    Returns:
        Tuple of (sheet_data, range_sources) where sheet_data is a list of lists containing
        the values and range_sources is a list of (LoadSource, range_str) pairs indicating
        which ranges came from which sources

    Raises:
        ValueError: If the range format is invalid
    """
    try:
        # Parse sheet name and range from the range_name
        if "!" not in range_name:
            raise ValueError(f"Range must include sheet name (e.g., 'Sheet1!A1:B5'): {range_name}")

        sheet_name, range_part = range_name.split("!", 1)

        # Use the sheet data cache
        from ripper.ripperlib.sheet_data_cache import SheetDataCache

        cache = SheetDataCache()

        return cache.get_sheet_data(service, spreadsheet_id, sheet_name, range_part)

    except Exception as e:
        logger.error(f"Error in retrieve_sheet_data: {e}")
        # Fallback to direct API call
        return fetch_data_from_spreadsheet(service, spreadsheet_id, range_name), [(LoadSource.API, range_name)]


def get_tiller_transactions(
    service: Any,
    spreadsheet_id: str,
    sheet_name: str = "Transactions",
) -> list[dict[str, Any]]:
    """Get transaction data from Tiller spreadsheet.

    Retrieves all rows from the configured sheet and returns them as a list of
    dictionaries with normalized header keys. Date range and account/category
    filtering is handled by the caller (e.g. ``DashboardDataService._apply_filters``).

    Args:
        service: Google Sheets API service instance
        spreadsheet_id: The ID of the spreadsheet
        sheet_name: Name of the transactions sheet (default: "Transactions")

    Returns:
        List of transaction dictionaries
    """
    try:
        data, _ = retrieve_sheet_data(service, spreadsheet_id, f"{sheet_name}!A:Z")
        if not data or len(data) < 2:
            return []

        headers = [str(cell).lower().replace(" ", "_") for cell in data[0]]
        transactions = []

        for row in data[1:]:
            if len(row) >= len(headers):
                transaction = {}
                for i, header in enumerate(headers):
                    if i < len(row):
                        transaction[header] = row[i]
                transactions.append(transaction)

        return transactions
    except Exception as e:
        logger.error(f"Error getting Tiller transactions: {e}")
        return []


def get_tiller_categories(service: Any, spreadsheet_id: str, sheet_name: str = "Categories") -> list[dict[str, Any]]:
    """Get category data from Tiller spreadsheet.

    Args:
        service: Google Sheets API service instance
        spreadsheet_id: The ID of the spreadsheet
        sheet_name: Name of the categories sheet (default: "Categories")

    Returns:
        List of category dictionaries
    """
    try:
        data, _ = retrieve_sheet_data(service, spreadsheet_id, f"{sheet_name}!A:Z")
        if not data or len(data) < 2:
            return []

        headers = [str(cell).lower().replace(" ", "_") for cell in data[0]]
        categories = []

        for row in data[1:]:
            if len(row) >= len(headers):
                category = {}
                for i, header in enumerate(headers):
                    if i < len(row):
                        category[header] = row[i]
                categories.append(category)

        return categories
    except Exception as e:
        logger.error(f"Error getting Tiller categories: {e}")
        return []


def get_tiller_budget(service: Any, spreadsheet_id: str, sheet_name: str = "Budget") -> list[dict[str, Any]]:
    """Get budget data from Tiller spreadsheet.

    Args:
        service: Google Sheets API service instance
        spreadsheet_id: The ID of the spreadsheet
        sheet_name: Name of the budget sheet (default: "Budget")

    Returns:
        List of budget dictionaries
    """
    try:
        data, _ = retrieve_sheet_data(service, spreadsheet_id, f"{sheet_name}!A:Z")
        if not data or len(data) < 2:
            return []

        headers = [str(cell).lower().replace(" ", "_") for cell in data[0]]
        budget_items = []

        for row in data[1:]:
            if len(row) >= len(headers):
                budget_item = {}
                for i, header in enumerate(headers):
                    if i < len(row):
                        budget_item[header] = row[i]
                budget_items.append(budget_item)

        return budget_items
    except Exception as e:
        logger.error(f"Error getting Tiller budget: {e}")
        return []
