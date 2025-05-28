from enum import Enum, auto
from pathlib import Path

import platformdirs
from beartype.typing import Any, Dict, Protocol
from loguru import logger
from typing_extensions import runtime_checkable


# Protocol classes for Google API services
@runtime_checkable
class SheetsService(Protocol):
    def spreadsheets(self) -> Any: ...
    def values(self) -> Any: ...
    def get(self, spreadsheetId: str) -> Any: ...
    def batchUpdate(self, spreadsheetId: str, body: Dict[str, Any]) -> Any: ...


@runtime_checkable
class DriveService(Protocol):
    def files(self) -> Any: ...
    def get(self, fileId: str) -> Any: ...
    def list(self, **kwargs: Any) -> Any: ...


@runtime_checkable
class UserInfoService(Protocol):
    def userinfo(self) -> Any: ...
    def get(self) -> Any: ...


# Google API query result types
SheetData = list[list[Any]]


def get_app_data_dir() -> str:
    """
    Get the application data directory for the current user using platformdirs.

    Returns:
        The path to the application data directory.
    """
    # Use platformdirs to get the user data directory
    return platformdirs.user_data_dir(appname="ripper", ensure_exists=True)


LOG_FILE_PATH = Path(get_app_data_dir()) / "ripper.log"

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


class LoadSource(Enum):
    NONE = auto()
    API = auto()
    DATABASE = auto()


class SpreadsheetProperties:
    """
    Models the properties of a Google Spreadsheet (File) as returned by the Google Drive API.
    """

    def __init__(self, properties: dict[str, Any]):
        logger.debug(f"SpreadsheetProperties: {properties}")
        self.id = properties["id"]
        self.name = properties["name"]
        self.created_time = properties["createdTime"]
        self.modified_time = properties["modifiedTime"]
        self.web_view_link = properties["webViewLink"]
        self.owners = properties["owners"]
        self.shared = properties["shared"]
        if "thumbnailLink" in properties:
            self.thumbnail_link = properties["thumbnailLink"]
        else:
            self.thumbnail_link = ""
        if "size" in properties:
            self.size = properties["size"]
        else:
            self.size = 0
        if "thumbnail" in properties:
            self.thumbnail = properties["thumbnail"]
        else:
            self.thumbnail = None
        self.load_source = LoadSource.NONE

    def to_dict(self) -> dict[str, Any]:
        dict = {
            "id": self.id,
            "name": self.name,
            "createdTime": self.created_time,
            "modifiedTime": self.modified_time,
            "webViewLink": self.web_view_link,
            "thumbnailLink": self.thumbnail_link,
            "owners": self.owners,
            "size": self.size,
            "shared": self.shared,
        }
        if self.thumbnail is not None:
            dict["thumbnail"] = self.thumbnail
        return dict

    @staticmethod
    def fields(*, include_thumbnail: bool = False) -> list[str]:
        fields = [
            "id",
            "name",
            "createdTime",
            "modifiedTime",
            "webViewLink",
            "thumbnailLink",
            "owners",
            "size",
            "shared",
        ]
        if include_thumbnail:
            fields.append("thumbnail")
        return fields

    @staticmethod
    def api_fields(*, include_thumbnail: bool = False) -> str:
        return f"files({', '.join(SpreadsheetProperties.fields(include_thumbnail=include_thumbnail))})"


class SheetProperties:
    """
    Models the properties of a Google Sheet as returned by the Google Sheets API.
    """

    class GridProperties:
        def __init__(self, row_count: int, column_count: int):
            self.row_count = row_count
            self.column_count = column_count

        def to_dict(self) -> dict[str, Any]:
            return {
                "rowCount": self.row_count,
                "columnCount": self.column_count,
            }

    def __init__(self, sheet_info: dict[str, Any] | None = None):
        if sheet_info:
            logger.debug(f"SheetProperties: {sheet_info['properties']}")
            properties = sheet_info["properties"]
            self.id = properties["sheetId"]
            self.index = properties["index"]
            self.title = properties["title"]
            self.type = properties["sheetType"]
            self.grid = SheetProperties.GridProperties(
                properties["gridProperties"]["rowCount"],
                properties["gridProperties"]["columnCount"],
            )
            self.load_source = LoadSource.NONE

    def to_dict(self) -> dict[str, Any]:
        return {
            "sheetId": self.id,
            "index": self.index,
            "title": self.title,
            "sheetType": self.type,
            "gridProperties": self.grid.to_dict(),
        }

    @staticmethod
    def fields() -> list[str]:
        return ["sheetId", "index", "title", "sheetType", "gridProperties.rowCount", "gridProperties.columnCount"]

    @staticmethod
    def api_fields() -> str:
        return f"sheets.properties({','.join(SheetProperties.fields())})"

    @staticmethod
    def from_api_result(api_result: dict[str, Any]) -> list["SheetProperties"]:
        sheets = []
        if "sheets" in api_result:
            for sheet in api_result["sheets"]:
                sheets.append(SheetProperties(sheet))
        return sheets
