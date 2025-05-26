from unittest.mock import MagicMock, patch

import pytest

from ripper.rippergui.sheets_selection_view import (
    SheetsSelectionDialog,
    SpreadsheetThumbnailWidget,
    col_to_letter,
    parse_cell,
)
from ripper.ripperlib.database import Db


@pytest.fixture(autouse=True)
def setup_database(tmp_path, monkeypatch):
    """Setup a clean database for each test."""
    # Create a test database file in a temporary directory
    test_db_path = str(tmp_path / "test.db")

    # Store the original __init__
    original_init = Db.__init__

    def mock_init(self, db_file_path=None):
        # Always use the test database path
        original_init(self, test_db_path)

    # Patch the Db.__init__ method
    monkeypatch.setattr(Db, "__init__", mock_init)

    # Create a new database instance
    db = Db()
    # Clean any existing data
    db.clean()
    # Initialize the database
    db.open()
    yield db
    # Close the database connection
    db.close()
    # Clean the database (but don't delete the file)
    db.clean()


def test_col_to_letter():
    """Test the col_to_letter function."""
    assert col_to_letter(1) == "A"
    assert col_to_letter(26) == "Z"
    assert col_to_letter(27) == "AA"
    assert col_to_letter(52) == "AZ"
    assert col_to_letter(53) == "BA"
    assert col_to_letter(702) == "ZZ"
    assert col_to_letter(703) == "AAA"


def test_parse_cell():
    """Test the parse_cell function."""
    # Test valid cell references
    assert parse_cell("A1") == (1, 1)
    assert parse_cell("Z10") == (10, 26)
    assert parse_cell("AA1") == (1, 27)
    assert parse_cell("AB20") == (20, 28)

    # Test invalid cell references
    with pytest.raises(ValueError):
        parse_cell("1A")  # Invalid format
    with pytest.raises(ValueError):
        parse_cell("A")  # Missing row
    with pytest.raises(ValueError):
        parse_cell("1")  # Missing column


@pytest.mark.qt
class TestSpreadsheetThumbnailWidget:
    """Test cases for the SpreadsheetThumbnailWidget class."""

    def test_initialization(self, qtbot):
        """Test that the widget initializes correctly."""
        # Create a mock spreadsheet info
        spreadsheet_info = {
            "id": "test_id",
            "name": "Test Spreadsheet",
            "modifiedTime": "2024-01-01T00:00:00Z",
        }

        # Create the widget
        widget = SpreadsheetThumbnailWidget(spreadsheet_info)
        qtbot.addWidget(widget)

        # Check that the widget was initialized with the correct info
        assert widget.spreadsheet_info == spreadsheet_info
        assert widget.name_label.text() == "Test Spreadsheet"

    @patch("ripper.rippergui.sheets_selection_view.Db")
    def test_load_thumbnail_from_cache(self, mock_db_class, qtbot):
        """Test loading a thumbnail from cache."""
        # Create a mock spreadsheet info
        spreadsheet_info = {
            "id": "test_id",
            "name": "Test Spreadsheet",
            "thumbnailLink": "https://example.com/thumbnail.png",
        }

        # Create a mock database instance
        mock_db_instance = MagicMock()
        mock_db_class.return_value = mock_db_instance

        # Set up the mock to return a cached thumbnail
        mock_thumbnail_data = b"mock_image_data"
        mock_db_instance.get_spreadsheet_thumbnail.return_value = {
            "thumbnail": mock_thumbnail_data,
            "modifiedTime": "2024-01-01T00:00:00Z",
        }

        # Patch QImage and QPixmap for this specific test
        with (
            patch("ripper.rippergui.sheets_selection_view.QImage") as mock_qimage_class,
            patch("ripper.rippergui.sheets_selection_view.QPixmap.fromImage") as mock_from_image,
        ):
            mock_image = MagicMock()
            mock_pixmap = MagicMock()
            mock_qimage_class.return_value = mock_image
            mock_from_image.return_value = mock_pixmap
            mock_image.loadFromData.return_value = True

            widget = SpreadsheetThumbnailWidget(spreadsheet_info)
            qtbot.addWidget(widget)

            # Reset mock call count after widget construction
            mock_db_instance.get_spreadsheet_thumbnail.reset_mock()
            mock_image.loadFromData.reset_mock()
            # Replace setPixmap and network_manager.get with mocks for assertion
            widget.thumbnail_label.setPixmap = MagicMock()
            widget.network_manager.get = MagicMock()

            # Connect to the signal and track emissions
            results = []
            widget.thumbnail_loaded.connect(lambda result: results.append(result))

            # Call load_thumbnail
            widget.load_thumbnail("https://example.com/thumbnail.png", "test_id")

            # Verify that the thumbnail was loaded from cache
            mock_db_instance.get_spreadsheet_thumbnail.assert_called_once_with("test_id")
            mock_image.loadFromData.assert_called_once_with(mock_thumbnail_data)
            widget.thumbnail_label.setPixmap.assert_called_once_with(mock_pixmap)
            # Verify that the network request was not made
            assert widget.network_manager.get.call_count == 0
            # Verify the signal was emitted with 'cache'
            assert results == ["cache"]


@pytest.mark.qt
class TestSheetsSelectionDialog:
    """Test cases for the SheetsSelectionDialog class."""

    @patch("ripper.rippergui.sheets_selection_view.AuthManager")
    @patch("ripper.rippergui.sheets_selection_view.fetch_and_store_spreadsheets")
    def test_initialization(self, mock_fetch, mock_auth_manager, qtbot):
        """Test that the dialog initializes correctly."""
        # Create a mock auth manager
        mock_auth_instance = MagicMock()
        mock_auth_manager.return_value = mock_auth_instance
        mock_auth_instance.create_drive_service.return_value = MagicMock()
        mock_auth_instance.create_sheets_service.return_value = MagicMock()

        # Set up the mock to return a list of spreadsheets
        mock_fetch.return_value = [
            {
                "id": "sheet1",
                "name": "Test Sheet 1",
                "modifiedTime": "2024-01-01T00:00:00Z",
            },
            {
                "id": "sheet2",
                "name": "Test Sheet 2",
                "modifiedTime": "2024-01-02T00:00:00Z",
            },
        ]

        # Create the dialog
        dialog = SheetsSelectionDialog()
        qtbot.addWidget(dialog)

        # Check that the dialog was initialized correctly
        assert dialog.windowTitle() == "Select Google Sheet"
        assert dialog.selected_spreadsheet is None
        assert len(dialog.spreadsheets_list) == 2
        assert dialog.spreadsheets_list[0]["id"] == "sheet1"
        assert dialog.spreadsheets_list[1]["id"] == "sheet2"

    @patch("ripper.rippergui.sheets_selection_view.AuthManager")
    @patch("ripper.rippergui.sheets_selection_view.fetch_and_store_spreadsheets")
    def test_select_spreadsheet(self, mock_fetch, mock_auth_manager, qtbot):
        """Test selecting a spreadsheet."""
        # Create a mock auth manager
        mock_auth_instance = MagicMock()
        mock_auth_manager.return_value = mock_auth_instance
        mock_auth_instance.create_drive_service.return_value = MagicMock()
        mock_auth_instance.create_sheets_service.return_value = MagicMock()

        # Set up the mock to return a list of spreadsheets
        mock_fetch.return_value = [
            {
                "id": "sheet1",
                "name": "Test Sheet 1",
                "modifiedTime": "2024-01-01T00:00:00Z",
            }
        ]

        # Create the dialog
        dialog = SheetsSelectionDialog()
        qtbot.addWidget(dialog)

        # Create a mock spreadsheet info
        spreadsheet_info = {
            "id": "sheet1",
            "name": "Test Sheet 1",
            "modifiedTime": "2024-01-01T00:00:00Z",
        }

        # Mock the _load_and_cache_sheet_metadata method
        dialog._load_and_cache_sheet_metadata = MagicMock()
        dialog._update_sheet_details = MagicMock()

        # Select the spreadsheet
        dialog.select_spreadsheet(spreadsheet_info)

        # Check that the spreadsheet was selected
        assert dialog.selected_spreadsheet == spreadsheet_info
        assert dialog.select_button.isEnabled()
        assert "Test Sheet 1" in dialog.details_content.text()

        # Verify that the methods were called
        dialog._load_and_cache_sheet_metadata.assert_called_once_with(spreadsheet_info)
        dialog._update_sheet_details.assert_called_once_with(spreadsheet_info)

    @patch("ripper.rippergui.sheets_selection_view.AuthManager")
    @patch("ripper.rippergui.sheets_selection_view.fetch_and_store_spreadsheets")
    def test_sheet_name_selected(self, mock_fetch, mock_auth_manager, qtbot):
        """Test the _sheet_name_selected method."""
        # Create a mock auth manager
        mock_auth_instance = MagicMock()
        mock_auth_manager.return_value = mock_auth_instance
        mock_auth_instance.create_drive_service.return_value = MagicMock()

        # Set up the mock to return a list of spreadsheets
        mock_fetch.return_value = [
            {
                "id": "sheet1",
                "name": "Test Sheet 1",
                "modifiedTime": "2024-01-01T00:00:00Z",
            }
        ]

        # Create the dialog
        dialog = SheetsSelectionDialog()
        qtbot.addWidget(dialog)

        # Set up the selected sheet and sheet properties
        dialog.selected_spreadsheet = {
            "id": "sheet1",
            "name": "Test Sheet 1",
            "modifiedTime": "2024-01-01T00:00:00Z",
        }

        # Create mock sheet properties
        class MockSheetProperties:
            def __init__(self, id, title, row_count, col_count):
                self.id = id
                self.title = title
                self.grid = MagicMock()
                self.grid.row_count = row_count
                self.grid.column_count = col_count

        sheet_props = [
            MockSheetProperties("sheet1", "Sheet 1", 100, 26),
            MockSheetProperties("sheet2", "Sheet 2", 200, 52),
        ]

        dialog.all_sheet_properties = {"sheet1": sheet_props}

        # Call the _sheet_name_selected method
        dialog._sheet_name_selected(0)

        # Check that the sheet range was updated correctly
        assert dialog.sheet_range_input.text() == "A1:Z100"

        # Test with an invalid index
        dialog.sheet_range_input.clear()
        dialog._sheet_name_selected(-1)

        # Check that the sheet range was cleared
        assert dialog.sheet_range_input.text() == ""
        assert not dialog.select_button.isEnabled()
