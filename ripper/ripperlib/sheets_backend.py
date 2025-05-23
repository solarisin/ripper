import json
import logging

from beartype.typing import Any, Dict, List, Optional, cast
from googleapiclient.errors import HttpError

from ripper.ripperlib.database import Db
from ripper.ripperlib.defs import DriveService, FileInfo, SheetData, SheetProperties, SheetsService

# Configure module logger
log = logging.getLogger("ripper:sheets_backend")


DRIVE_FILE_FIELDS: frozenset[str] = frozenset(
    [
        "id",
        "name",
        "thumbnailLink",
        "webViewLink",
        "createdTime",
        "modifiedTime",
        "owners",
        "size",
        "shared",
    ]
)


def list_spreadsheets(
    service: DriveService, file_fields: frozenset[str] = DRIVE_FILE_FIELDS
) -> Optional[List[FileInfo]]:
    """
    List Google Spreadsheets in the user's Drive.

    :param DriveService service: Authenticated Google Drive API service
    :param list[str] file_fields: Override the default fields to request from the API
    :return: A list of dictionaries containing information about the spreadsheets, or None if an error occurred

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
                    fields=f"nextPageToken, files({', '.join(file_fields)})",
                    pageToken=page_token,
                )
                .execute()
            )
            files.extend(response.get("files", []))
            page_token = response.get("nextPageToken", None)
            if page_token is None:
                break

        log.debug(f"Found {len(files)} sheets with thumbnail information")
        return files

    except HttpError as error:
        log.error(f"An error occurred fetching sheets list: {error}")
        return None


def read_spreadsheet_metadata(service: SheetsService, spreadsheet_id: str) -> Optional[list[SheetProperties]]:
    try:
        # Create a Sheets API instance
        sheets = service.spreadsheets()

        # Request to get values from the specified range in the Google Sheet
        result = sheets.get(spreadsheetId=spreadsheet_id, fields=SheetProperties.api_fields()).execute()

        return SheetProperties.from_api_result(result)

    except HttpError as error:
        log.error(f"An error occurred reading spreadsheet metadata: {error}")
        return None


def read_data_from_spreadsheet(service: SheetsService, spreadsheet_id: str, range_name: str) -> Optional[SheetData]:
    """
    Reads data from specific cells in the spreadsheet.

    Args:
        service: An authenticated Sheets API service instance
        spreadsheet_id: The ID of the spreadsheet to read from
        range_name: The A1 notation of the range to read (includes sheet name and cell range)

    Returns:
        A list of lists containing the values, or None if no data was found or an error occurred
    """
    try:
        # Create a Sheets API instance
        sheets = service.spreadsheets()

        # Request to get values from the specified range (includes sheet name and cell range) in the Google Sheet
        result = cast(Dict[str, Any], sheets.values().get(spreadsheetId=spreadsheet_id, range=range_name).execute())

        # Extract the values from the response
        values = cast(SheetData, result.get("values", []))

        # If the spreadsheet is empty, log an info message and return None
        if not values:
            log.info("No data found in spreadsheet.")
            return None

        # Log the number of rows found at debug level
        log.debug(f"Found {len(values)} rows of data in spreadsheet")
        return values

    except HttpError as error:
        log.error(f"An error occurred reading spreadsheet data: {error}")
        return None


def fetch_and_store_spreadsheets(drive_service: DriveService, db: Db) -> Optional[List[FileInfo]]:
    """
    Fetches the list of spreadsheets from Google Drive and stores relevant information in the database.

    Args:
        drive_service: Authenticated Google Drive API service.
        db: An instance of the database class.

    Returns:
        A list of dictionaries containing information about the fetched sheets, or None if an error occurred.
    """
    log.debug("Fetching and storing spreadsheets from Google Drive.")
    sheets_list = list_spreadsheets(drive_service)

    if not sheets_list:
        log.error("Failed to fetch sheets list.")
        return None

    for sheet_info in sheets_list:
        spreadsheet_id = sheet_info.get("id")
        if spreadsheet_id:
            info_to_store = {
                "name": sheet_info.get("name"),
                "modifiedTime": sheet_info.get("modifiedTime"),
                "webViewLink": sheet_info.get("webViewLink"),
                "createdTime": sheet_info.get("createdTime"),
                # owners is a list of dicts, store as JSON string for simplicity
                "owners": json.dumps(sheet_info.get("owners")) if sheet_info.get("owners") is not None else None,
                "size": sheet_info.get("size"),
                "shared": sheet_info.get("shared"),
            }
            db.store_spreadsheet_info(spreadsheet_id, info_to_store)

    log.debug(f"Successfully fetched and stored {len(sheets_list)} spreadsheets.")
    return sheets_list
