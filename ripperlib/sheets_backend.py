import logging
from typing import Any, Dict, List, Optional

from googleapiclient.errors import HttpError

# Configure module logger
log = logging.getLogger("ripper:sheets_backend")


def list_sheets(service) -> Optional[List[Dict[str, str]]]:
    """
    List all Google Sheets in the user's Drive.

    Args:
        service: An authenticated Google Drive API service instance

    Returns:
        List of dictionaries containing sheet information (id, name),
        or None if an error occurred
    """
    files = []
    try:
        # Create drive api client
        page_token = None
        while True:
            response = (
                service.files()
                .list(
                    q="mimeType='application/vnd.google-apps.spreadsheet'",
                    spaces="drive",
                    fields="nextPageToken, files(id, name)",
                    pageToken=page_token,
                )
                .execute()
            )
            files.extend(response.get("files", []))
            page_token = response.get("nextPageToken", None)
            if page_token is None:
                break

    except HttpError as error:
        log.error(f"An error occurred fetching sheets list: {error}")
        return None

    # Log at debug level only if there are a reasonable number of files
    if len(files) <= 10:
        log.debug(f"Found {len(files)} sheets:")
        for file_info in files:
            log.debug(f"  {file_info}")
    else:
        log.debug(f"Found {len(files)} sheets")

    return files


def read_data_from_spreadsheet(service, spreadsheet_id: str, range_name: str) -> Optional[List[List[Any]]]:
    """
    Reads data from specific cells in the spreadsheet.

    Args:
        service: An authenticated Sheets API service instance
        spreadsheet_id: The ID of the spreadsheet to read from
        range_name: The A1 notation of the range to read

    Returns:
        A list of lists containing the values, or None if no data was found or an error occurred
    """
    try:
        # Create a Sheets API instance
        sheets = service.spreadsheets()

        # Request to get values from the specified range in the Google Sheet
        result = sheets.values().get(spreadsheetId=spreadsheet_id, range=range_name).execute()

        # Extract the values from the response
        values = result.get("values", [])

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
