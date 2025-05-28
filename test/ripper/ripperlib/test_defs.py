import unittest
from unittest.mock import patch

from ripper.ripperlib.defs import LoadSource, SheetProperties, SpreadsheetProperties, get_app_data_dir


class TestSpreadsheetProperties(unittest.TestCase):
    """Test cases for the SpreadsheetProperties class."""

    def test_initialization(self):
        """Test that SpreadsheetProperties initializes correctly."""
        mock_properties = {
            "id": "test_id",
            "name": "Test Spreadsheet",
            "createdTime": "2023-01-01T10:00:00Z",
            "modifiedTime": "2023-01-01T11:00:00Z",
            "webViewLink": "http://example.com/view",
            "thumbnailLink": "http://example.com/thumbnail",
            "owners": [{"displayName": "Test User"}],
            "size": 1024,
            "shared": True,
        }
        props = SpreadsheetProperties(mock_properties)

        self.assertEqual(props.id, "test_id")
        self.assertEqual(props.name, "Test Spreadsheet")
        self.assertEqual(props.created_time, "2023-01-01T10:00:00Z")
        self.assertEqual(props.modified_time, "2023-01-01T11:00:00Z")
        self.assertEqual(props.web_view_link, "http://example.com/view")
        self.assertEqual(props.thumbnail_link, "http://example.com/thumbnail")
        self.assertEqual(props.owners, [{"displayName": "Test User"}])
        self.assertEqual(props.size, 1024)
        self.assertEqual(props.shared, True)
        self.assertIsNone(props.thumbnail)
        self.assertEqual(props.load_source, LoadSource.NONE)

    def test_initialization_missing_optional_fields(self):
        """Test that SpreadsheetProperties initializes correctly with missing optional fields."""
        mock_properties = {
            "id": "test_id_2",
            "name": "Another Spreadsheet",
            "createdTime": "2023-01-02T10:00:00Z",
            "modifiedTime": "2023-01-02T11:00:00Z",
            "webViewLink": "http://example.com/view_2",
            "owners": [{"displayName": "Another User"}],
            "shared": False,
        }
        props = SpreadsheetProperties(mock_properties)

        self.assertEqual(props.id, "test_id_2")
        self.assertEqual(props.name, "Another Spreadsheet")
        self.assertEqual(props.thumbnail_link, "")
        self.assertEqual(props.size, 0)
        self.assertIsNone(props.thumbnail)

    def test_to_dict(self):
        """Test that to_dict method returns the correct dictionary representation."""
        mock_properties = {
            "id": "test_id",
            "name": "Test Spreadsheet",
            "createdTime": "2023-01-01T10:00:00Z",
            "modifiedTime": "2023-01-01T11:00:00Z",
            "webViewLink": "http://example.com/view",
            "thumbnailLink": "http://example.com/thumbnail",
            "owners": [{"displayName": "Test User"}],
            "size": 1024,
            "shared": True,
        }
        props = SpreadsheetProperties(mock_properties)
        result_dict = props.to_dict()

        expected_dict = {
            "id": "test_id",
            "name": "Test Spreadsheet",
            "createdTime": "2023-01-01T10:00:00Z",
            "modifiedTime": "2023-01-01T11:00:00Z",
            "webViewLink": "http://example.com/view",
            "thumbnailLink": "http://example.com/thumbnail",
            "owners": [{"displayName": "Test User"}],
            "size": 1024,
            "shared": True,
        }
        self.assertEqual(result_dict, expected_dict)

    def test_to_dict_with_thumbnail(self):
        """Test that to_dict method includes thumbnail if present."""
        mock_properties = {
            "id": "test_id",
            "name": "Test Spreadsheet",
            "createdTime": "2023-01-01T10:00:00Z",
            "modifiedTime": "2023-01-01T11:00:00Z",
            "webViewLink": "http://example.com/view",
            "thumbnailLink": "http://example.com/thumbnail",
            "owners": [{"displayName": "Test User"}],
            "size": 1024,
            "shared": True,
            "thumbnail": b"dummy_thumbnail_data",
        }
        props = SpreadsheetProperties(mock_properties)
        result_dict = props.to_dict()

        expected_dict = {
            "id": "test_id",
            "name": "Test Spreadsheet",
            "createdTime": "2023-01-01T10:00:00Z",
            "modifiedTime": "2023-01-01T11:00:00Z",
            "webViewLink": "http://example.com/view",
            "thumbnailLink": "http://example.com/thumbnail",
            "owners": [{"displayName": "Test User"}],
            "size": 1024,
            "shared": True,
            "thumbnail": b"dummy_thumbnail_data",
        }
        self.assertEqual(result_dict, expected_dict)

    def test_fields_static_method(self):
        """Test the static fields method."""
        expected_fields = [
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
        self.assertEqual(SpreadsheetProperties.fields(), expected_fields)
        self.assertEqual(SpreadsheetProperties.fields(include_thumbnail=False), expected_fields)

    def test_fields_static_method_with_thumbnail(self):
        """Test the static fields method with include_thumbnail=True."""
        expected_fields = [
            "id",
            "name",
            "createdTime",
            "modifiedTime",
            "webViewLink",
            "thumbnailLink",
            "owners",
            "size",
            "shared",
            "thumbnail",
        ]
        self.assertEqual(SpreadsheetProperties.fields(include_thumbnail=True), expected_fields)

    def test_api_fields_static_method(self):
        """Test the static api_fields method."""
        expected_api_fields = (
            "files(id, name, createdTime, modifiedTime, webViewLink, thumbnailLink, owners, size, shared)"
        )
        self.assertEqual(SpreadsheetProperties.api_fields(), expected_api_fields)
        self.assertEqual(SpreadsheetProperties.api_fields(include_thumbnail=False), expected_api_fields)

    def test_api_fields_static_method_with_thumbnail(self):
        """Test the static api_fields method with include_thumbnail=True."""
        expected_api_fields = (
            "files(id, name, createdTime, modifiedTime, webViewLink, thumbnailLink, owners, size, shared, thumbnail)"
        )
        self.assertEqual(SpreadsheetProperties.api_fields(include_thumbnail=True), expected_api_fields)


class TestAppDataDir(unittest.TestCase):
    """Test cases for the get_app_data_dir function."""

    @patch("platformdirs.user_data_dir")
    def test_get_app_data_dir(self, mock_user_data_dir):
        """Test that get_app_data_dir calls platformdirs.user_data_dir correctly."""
        mock_user_data_dir.return_value = "/fake/app/data/dir"
        data_dir = get_app_data_dir()

        mock_user_data_dir.assert_called_once_with(appname="ripper", ensure_exists=True)
        self.assertEqual(data_dir, "/fake/app/data/dir")


class TestSheetProperties(unittest.TestCase):
    """Test cases for the SheetProperties class."""

    def test_initialization(self):
        """Test that SheetProperties initializes correctly."""
        mock_sheet_info = {
            "properties": {
                "sheetId": 12345,
                "index": 0,
                "title": "Sheet1",
                "sheetType": "GRID",
                "gridProperties": {
                    "rowCount": 100,
                    "columnCount": 10,
                },
            }
        }
        props = SheetProperties(mock_sheet_info)

        self.assertEqual(props.id, 12345)
        self.assertEqual(props.index, 0)
        self.assertEqual(props.title, "Sheet1")
        self.assertEqual(props.type, "GRID")
        self.assertEqual(props.grid.row_count, 100)
        self.assertEqual(props.grid.column_count, 10)
        self.assertEqual(props.load_source, LoadSource.NONE)

    def test_initialization_none(self):
        """Test that SheetProperties initializes correctly with None."""
        props = SheetProperties(None)
        # Assert that attributes are not set or have default-like values (depending on implementation)
        # Based on the __init__, if sheet_info is None, no attributes are set.
        # We should perhaps modify the __init__ to set default values or handle this case better.
        # For now, we assert that the object is created without errors.
        self.assertIsInstance(props, SheetProperties)
        # Add more specific assertions if __init__ is modified to set defaults.

    def test_grid_properties_to_dict(self):
        """Test that GridProperties to_dict method works."""
        grid_props = SheetProperties.GridProperties(100, 10)
        expected_dict = {
            "rowCount": 100,
            "columnCount": 10,
        }
        self.assertEqual(grid_props.to_dict(), expected_dict)

    def test_to_dict(self):
        """Test that SheetProperties to_dict method returns the correct dictionary representation."""
        mock_sheet_info = {
            "properties": {
                "sheetId": 12345,
                "index": 0,
                "title": "Sheet1",
                "sheetType": "GRID",
                "gridProperties": {
                    "rowCount": 100,
                    "columnCount": 10,
                },
            }
        }
        props = SheetProperties(mock_sheet_info)
        result_dict = props.to_dict()

        expected_dict = {
            "sheetId": 12345,
            "index": 0,
            "title": "Sheet1",
            "sheetType": "GRID",
            "gridProperties": {
                "rowCount": 100,
                "columnCount": 10,
            },
        }
        self.assertEqual(result_dict, expected_dict)

    def test_fields_static_method(self):
        """Test the static fields method."""
        expected_fields = [
            "sheetId",
            "index",
            "title",
            "sheetType",
            "gridProperties.rowCount",
            "gridProperties.columnCount",
        ]
        self.assertEqual(SheetProperties.fields(), expected_fields)

    def test_api_fields_static_method(self):
        """Test the static api_fields method."""
        expected_api_fields = (
            "sheets.properties(sheetId,index,title,sheetType,gridProperties.rowCount,gridProperties.columnCount)"
        )
        self.assertEqual(SheetProperties.api_fields(), expected_api_fields)

    def test_from_api_result_static_method(self):
        """Test the static from_api_result method."""
        mock_api_result = {
            "sheets": [
                {
                    "properties": {
                        "sheetId": 123,
                        "index": 0,
                        "title": "SheetA",
                        "sheetType": "GRID",
                        "gridProperties": {"rowCount": 50, "columnCount": 5},
                    }
                },
                {
                    "properties": {
                        "sheetId": 456,
                        "index": 1,
                        "title": "SheetB",
                        "sheetType": "GRID",
                        "gridProperties": {"rowCount": 20, "columnCount": 3},
                    }
                },
            ]
        }
        sheets = SheetProperties.from_api_result(mock_api_result)

        self.assertEqual(len(sheets), 2)
        self.assertIsInstance(sheets[0], SheetProperties)
        self.assertEqual(sheets[0].title, "SheetA")
        self.assertEqual(sheets[1].title, "SheetB")

    def test_from_api_result_empty(self):
        """Test from_api_result with empty sheets list."""
        mock_api_result = {"sheets": []}
        sheets = SheetProperties.from_api_result(mock_api_result)
        self.assertEqual(len(sheets), 0)

    def test_from_api_result_no_sheets_key(self):
        """Test from_api_result with no 'sheets' key in the result."""
        mock_api_result = {"some_other_key": "value"}
        sheets = SheetProperties.from_api_result(mock_api_result)
        self.assertEqual(len(sheets), 0)


class TestLoadSourceEnum(unittest.TestCase):
    """Test cases for the LoadSource enum."""

    def test_enum_values(self):
        """Test that LoadSource enum has expected values."""
        self.assertEqual(LoadSource.NONE.value, 1)
        self.assertEqual(LoadSource.API.value, 2)
        self.assertEqual(LoadSource.DATABASE.value, 3)

    def test_enum_names(self):
        """Test that LoadSource enum has expected names."""
        self.assertEqual(LoadSource.NONE.name, "NONE")
        self.assertEqual(LoadSource.API.name, "API")
        self.assertEqual(LoadSource.DATABASE.name, "DATABASE")
