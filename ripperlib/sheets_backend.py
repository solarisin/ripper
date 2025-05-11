import logging

from googleapiclient.errors import HttpError

def list_sheets(service):
    log = logging.getLogger('list_sheets')
    log.setLevel(logging.DEBUG)
    files = []
    try:
        # create drive api client
        page_token = None
        while True:
            # pylint: disable=maybe-no-member
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
        files = None

    log.debug("result:")
    for file_info in files:
        log.debug(f"  {file_info}")
    return files


def read_data_from_spreadsheet(service, spreadsheet_id, range_name):
    """
    Reads data from specific cells in the spreadsheet.

    :param service: An authenticated Sheets API service instance.
    """
    # Create a Sheets API instance
    sheets = service.spreadsheets()

    # Request to get values from the specified range in the Google Sheet
    s = sheets.values()
    result = sheets.values().get(spreadsheetId=spreadsheet_id, range=range_name).execute()

    # Extract the values from the response
    values = result.get('values', [])

    # If the spreadsheet is empty, log an info message and return None
    if not values:
        logging.info('No data found.')
        return None

    # Log the values and return them
    logging.info(values)
    return values