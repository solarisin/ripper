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
