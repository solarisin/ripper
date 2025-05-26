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
FileInfo = dict[str, Any]


def get_app_data_dir() -> str:
    """
    Get the application data directory for the current user using platformdirs.

    Returns:
        The path to the application data directory.
    """
    # Use platformdirs to get the user data directory
    return platformdirs.user_data_dir(appname="ripper", ensure_exists=True)


LOG_FILE_PATH = Path(get_app_data_dir()) / "ripper.log"


class SheetProperties:
    class GridProperties:
        def __init__(self, row_count: int, column_count: int):
            self.row_count = row_count
            self.column_count = column_count

        def to_dict(self) -> dict[str, Any]:
            return {
                "rowCount": self.row_count,
                "columnCount": self.column_count,
            }

    def __init__(self, sheet_info: dict[str, Any]):
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
