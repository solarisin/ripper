import logging
import os
from pathlib import Path

from beartype.typing import Any, Dict, Protocol
from PySide6.QtCore import QStandardPaths
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


def get_app_data_dir(log: logging.Logger = logging.getLogger("ripper:defs")) -> str:
    """
    Get the application data directory for the current user.

    Returns:
        The path to the application data directory.
    """
    app_data_dir = (
        Path(QStandardPaths.writableLocation(QStandardPaths.StandardLocation.AppLocalDataLocation)) / "ripper"
    )

    # Attempt to create the directory if it doesn't exist
    if not app_data_dir.exists():
        try:
            app_data_dir.mkdir(exist_ok=True, parents=True)
        except Exception as e:
            # Fall back to current directory if we can't create the app data directory
            log.warning(f"Application data directory {app_data_dir} does not exist, and failed to create it: {e}")
            app_data_dir = Path(os.getcwd())
            log.warning(f"Using current directory {app_data_dir} for application data")
    return str(app_data_dir)


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
        logging.debug(f"SheetProperties: {sheet_info['properties']}")
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
