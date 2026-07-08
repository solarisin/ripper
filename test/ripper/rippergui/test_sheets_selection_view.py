from unittest.mock import MagicMock, patch

import pytest
from PySide6.QtWidgets import QWidget

from ripper.rippergui.sheets_selection_view import (
    SheetsSelectionDialog,
    _SheetMetadataLoader,
    _SpreadsheetLoader,
)
from ripper.rippergui.spreadsheet_thumbnail_widget import SpreadsheetThumbnailWidget
from ripper.ripperlib.database import Db
from ripper.ripperlib.defs import LoadSource, SheetProperties, SpreadsheetProperties


@pytest.fixture(autouse=True)
def setup_database():
    """Provide the global Db, which the root conftest isolates to a fresh temp database.

    Previously this fixture mutated ``Db._db_file_path`` and called ``Db.clean()``/``open()``
    on the global singleton; with the lazy Db proxy that risked operating on the real
    ``ripper.db``. The ``_isolate_global_db`` fixture in test/conftest.py now points Db at a
    per-test temp database, so no path mutation or global cleanup is needed here.
    """
    yield Db


@pytest.mark.qt
class TestSpreadsheetThumbnailWidget:
    """Test cases for the SpreadsheetThumbnailWidget class."""

    @pytest.mark.xfail(
        reason="#47: thumbnail widget elides the display text (and mutates the shared name); "
        "the elided result is also font-metric/platform dependent.",
        strict=False,
    )
    def test_initialization(self, qtbot):
        """Test that the widget initializes correctly."""
        # Create a mock spreadsheet properties
        spreadsheet_properties = MagicMock(spec=SpreadsheetProperties)
        spreadsheet_properties.id = "test_id"
        spreadsheet_properties.name = "Test Spreadsheet"
        spreadsheet_properties.modified_time = "2024-01-01T00:00:00Z"
        spreadsheet_properties.created_time = "2023-12-01T00:00:00Z"
        spreadsheet_properties.thumbnail_link = ""

        # Create a parent widget
        parent = QWidget()
        qtbot.addWidget(parent)

        # Create the widget
        widget = SpreadsheetThumbnailWidget(spreadsheet_properties, parent)
        qtbot.addWidget(widget)

        # Check that the widget was initialized with the correct info
        assert widget.spreadsheet_properties == spreadsheet_properties
        assert widget.name_label.text() == "Test Spreadsheet"

    @patch("ripper.rippergui.spreadsheet_thumbnail_widget.retrieve_thumbnail")
    @patch("ripper.rippergui.spreadsheet_thumbnail_widget._ThumbnailLoader")
    def test_thumbnail_is_loaded_off_the_gui_thread(self, mock_loader_cls, mock_retrieve, qtbot):
        """The constructor must not fetch synchronously; it starts a worker and shows a placeholder (#35)."""
        from ripper.rippergui import spreadsheet_thumbnail_widget as stw

        props = MagicMock(spec=SpreadsheetProperties)
        props.id = "test_id"
        props.name = "Test"
        props.thumbnail_link = "https://example.com/thumbnail.png"
        props.modified_time = "2024-01-01T00:00:00Z"
        props.created_time = "2023-12-01T00:00:00Z"
        parent = QWidget()
        qtbot.addWidget(parent)

        try:
            widget = SpreadsheetThumbnailWidget(props, parent)  # owned by parent; teardown closes both

            mock_retrieve.assert_not_called()  # no network on the GUI thread
            mock_loader_cls.assert_called_once_with("test_id", "https://example.com/thumbnail.png")
            mock_loader_cls.return_value.start.assert_called_once()
            # A placeholder is shown immediately, before the worker finishes.
            assert not widget.thumbnail_label.pixmap().isNull()
        finally:
            stw._active_thumbnail_loaders.clear()

    @patch("ripper.rippergui.spreadsheet_thumbnail_widget.retrieve_thumbnail")
    @patch("ripper.rippergui.spreadsheet_thumbnail_widget._ThumbnailLoader")
    def test_no_thumbnail_link_does_not_start_worker(self, mock_loader_cls, mock_retrieve, qtbot):
        """With no thumbnailLink, no worker is started and the placeholder remains (#35)."""
        props = MagicMock(spec=SpreadsheetProperties)
        props.id = "test_id"
        props.name = "Test"
        props.thumbnail_link = ""
        props.modified_time = "2024-01-01T00:00:00Z"
        props.created_time = "2023-12-01T00:00:00Z"
        parent = QWidget()
        qtbot.addWidget(parent)

        widget = SpreadsheetThumbnailWidget(props, parent)  # owned by parent; teardown closes both

        mock_loader_cls.assert_not_called()
        mock_retrieve.assert_not_called()
        assert not widget.thumbnail_label.pixmap().isNull()

    @patch("ripper.rippergui.spreadsheet_thumbnail_widget.QPixmap")
    def test_on_thumbnail_loaded_sets_pixmap_for_valid_data(self, mock_qpixmap_cls):
        """A valid image is applied to the label and the load source is re-emitted."""
        widget = MagicMock()
        pixmap = mock_qpixmap_cls.return_value
        pixmap.isNull.return_value = False

        SpreadsheetThumbnailWidget._on_thumbnail_loaded(widget, b"image-bytes", LoadSource.API)

        pixmap.loadFromData.assert_called_once_with(b"image-bytes")
        widget.thumbnail_label.setPixmap.assert_called_once_with(pixmap)
        widget.set_default_thumbnail.assert_not_called()
        widget.thumbnail_loaded.emit.assert_called_once_with(LoadSource.API)

    def test_on_thumbnail_loaded_falls_back_on_empty(self):
        """Empty bytes (a failed fetch) keep the default placeholder."""
        widget = MagicMock()

        SpreadsheetThumbnailWidget._on_thumbnail_loaded(widget, b"", LoadSource.NONE)

        widget.set_default_thumbnail.assert_called_once()
        widget.thumbnail_label.setPixmap.assert_not_called()
        widget.thumbnail_loaded.emit.assert_called_once_with(LoadSource.NONE)

    @patch("ripper.rippergui.spreadsheet_thumbnail_widget.QPixmap")
    def test_on_thumbnail_loaded_falls_back_on_invalid_image(self, mock_qpixmap_cls):
        """Non-empty bytes that don't decode to a valid image fall back to the placeholder."""
        widget = MagicMock()
        mock_qpixmap_cls.return_value.isNull.return_value = True

        SpreadsheetThumbnailWidget._on_thumbnail_loaded(widget, b"not-an-image", LoadSource.API)

        widget.set_default_thumbnail.assert_called_once()
        widget.thumbnail_label.setPixmap.assert_not_called()
        widget.thumbnail_loaded.emit.assert_called_once_with(LoadSource.API)


@pytest.mark.qt
class TestSheetsSelectionDialog:
    """Test cases for the SheetsSelectionDialog class."""

    @patch("ripper.rippergui.sheets_selection_view._SpreadsheetLoader.start")
    @patch("ripper.rippergui.sheets_selection_view.AuthManager")
    @patch("ripper.ripperlib.sheets_backend.retrieve_spreadsheets")
    def test_initialization(self, mock_fetch, mock_auth_manager, mock_loader_start, qtbot):
        """Test that the dialog initializes correctly."""
        # Create a mock auth manager
        mock_auth_instance = MagicMock()
        mock_auth_manager.return_value = mock_auth_instance
        mock_auth_instance.create_drive_service.return_value = MagicMock()
        mock_auth_instance.create_sheets_service.return_value = MagicMock()

        # Create mock SpreadsheetProperties objects
        sheet1 = MagicMock(spec=SpreadsheetProperties)
        sheet1.id = "sheet1"
        sheet1.name = "Test Sheet 1"
        sheet1.modified_time = "2024-01-01T00:00:00Z"
        sheet1.created_time = "2023-12-01T00:00:00Z"
        sheet1.thumbnail_link = ""
        sheet1.web_view_link = "https://example.com/sheet1"
        sheet1.owners = [{"displayName": "Test User"}]
        sheet1.size = 1024
        sheet1.shared = True

        sheet2 = MagicMock(spec=SpreadsheetProperties)
        sheet2.id = "sheet2"
        sheet2.name = "Test Sheet 2"
        sheet2.modified_time = "2024-01-02T00:00:00Z"
        sheet2.created_time = "2023-12-02T00:00:00Z"
        sheet2.thumbnail_link = ""
        sheet2.web_view_link = "https://example.com/sheet2"
        sheet2.owners = [{"displayName": "Test User"}]
        sheet2.size = 2048
        sheet2.shared = True

        # Set up the mock to return a list of spreadsheets
        mock_fetch.return_value = [sheet1, sheet2]

        # Create the dialog — _SpreadsheetLoader.start is patched so no background
        # thread races with our assertions.  load_spreadsheets() still runs normally
        # so all internal state is set up correctly.
        dialog = SheetsSelectionDialog()
        qtbot.addWidget(dialog)
        # Simulate what the background loader would deliver
        dialog._on_spreadsheets_loaded([sheet1, sheet2])

        # Check that the dialog was initialized correctly
        assert dialog.windowTitle() == "Create Data Source"
        assert dialog.selected_spreadsheet is None
        assert len(dialog.spreadsheets_list) == 2
        assert dialog.spreadsheets_list[0].id == "sheet1"
        assert dialog.spreadsheets_list[1].id == "sheet2"

    @patch("ripper.rippergui.sheets_selection_view._SpreadsheetLoader.start")
    @patch("ripper.rippergui.sheets_selection_view._SheetMetadataLoader.start")
    @patch("ripper.rippergui.sheets_selection_view.AuthManager")
    @patch("ripper.ripperlib.sheets_backend.retrieve_spreadsheets")
    @patch("ripper.ripperlib.sheets_backend.retrieve_sheets_of_spreadsheet")
    def test_select_spreadsheet(
        self, mock_retrieve_sheets, mock_fetch, mock_auth_manager, mock_meta_start, mock_loader_start, qtbot
    ):
        """Test selecting a spreadsheet."""
        # Create a mock auth manager
        mock_auth_instance = MagicMock()
        mock_auth_manager.return_value = mock_auth_instance
        mock_auth_instance.create_drive_service.return_value = MagicMock()
        mock_auth_instance.create_sheets_service.return_value = MagicMock()

        # Create mock SpreadsheetProperties object
        sheet1 = MagicMock(spec=SpreadsheetProperties)
        sheet1.id = "sheet1"
        sheet1.name = "Test Sheet 1"
        sheet1.modified_time = "2024-01-01T00:00:00Z"
        sheet1.created_time = "2023-12-01T00:00:00Z"
        sheet1.thumbnail_link = ""
        sheet1.web_view_link = "https://example.com/sheet1"
        sheet1.owners = [{"displayName": "Test User"}]
        sheet1.size = 1024
        sheet1.shared = True

        # Set up the mock to return a list of spreadsheets
        mock_fetch.return_value = [sheet1]

        # Create the dialog
        dialog = SheetsSelectionDialog()
        qtbot.addWidget(dialog)

        # Mock the return value for retrieve_sheets_of_spreadsheet
        mock_sheet_props = [
            MagicMock(
                spec=SheetProperties, id="sheet1_tab1", title="Sheet1", grid=MagicMock(row_count=100, column_count=26)
            ),
            MagicMock(
                spec=SheetProperties, id="sheet1_tab2", title="Sheet2", grid=MagicMock(row_count=200, column_count=52)
            ),
        ]
        mock_retrieve_sheets.return_value = mock_sheet_props

        # Select the spreadsheet — metadata thread is patched so it won't start;
        # we call the callback directly to simulate a successful load.
        dialog.select_spreadsheet(sheet1)

        # Check that the spreadsheet was selected and UI updated synchronously
        assert dialog.selected_spreadsheet == sheet1
        assert dialog.select_button.isEnabled()
        assert "Test Sheet 1" in dialog.details_content.text()

        # Simulate what the background metadata thread would deliver
        dialog._on_sheet_metadata_loaded(mock_sheet_props, sheet1.id)

        # Verify that the sheet properties list is updated in the dialog
        assert dialog.sheet_properties_list == mock_sheet_props

    @patch("ripper.rippergui.sheets_selection_view._SpreadsheetLoader.start")
    @patch("ripper.rippergui.sheets_selection_view.AuthManager")
    @patch("ripper.ripperlib.sheets_backend.retrieve_spreadsheets")
    def test_sheet_name_selected(self, mock_fetch, mock_auth_manager, mock_loader_start, qtbot):
        """Test that selecting a sheet name in the combobox updates the range input."""
        # Create a mock auth manager
        mock_auth_instance = MagicMock()
        mock_auth_manager.return_value = mock_auth_instance
        mock_auth_instance.create_drive_service.return_value = MagicMock()

        # Create mock SpreadsheetProperties object
        sheet1 = MagicMock(spec=SpreadsheetProperties)
        sheet1.id = "sheet1"
        sheet1.name = "Test Sheet 1"
        sheet1.modified_time = "2024-01-01T00:00:00Z"
        sheet1.created_time = "2023-12-01T00:00:00Z"
        sheet1.thumbnail_link = ""
        sheet1.web_view_link = "https://example.com/sheet1"
        sheet1.owners = [{"displayName": "Test User"}]
        sheet1.size = 1024
        sheet1.shared = True

        # Set up the mock to return a list of spreadsheets
        mock_fetch.return_value = [sheet1]

        # Create the dialog
        dialog = SheetsSelectionDialog()
        qtbot.addWidget(dialog)

        # Set up the selected sheet
        dialog.selected_spreadsheet = sheet1

        # Create mock sheet properties
        sheet_props = []
        sheet_prop1 = MagicMock(spec=SheetProperties)
        sheet_prop1.id = "sheet1"
        sheet_prop1.title = "Sheet 1"
        sheet_prop1.grid = MagicMock()
        sheet_prop1.grid.row_count = 100
        sheet_prop1.grid.column_count = 26
        sheet_props.append(sheet_prop1)

        sheet_prop2 = MagicMock(spec=SheetProperties)
        sheet_prop2.id = "sheet2"
        sheet_prop2.title = "Sheet 2"
        sheet_prop2.grid = MagicMock()
        sheet_prop2.grid.row_count = 200
        sheet_prop2.grid.column_count = 52
        sheet_props.append(sheet_prop2)

        dialog.sheet_properties_list = sheet_props

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


class TestLoaderReferenceTracking:
    """Identity-safe background-loader tracking guards the #74 out-of-order completion race.

    These exercise the real _track_loader/_retire_loader/_stop_loaders logic against a mock
    dialog + mock workers, so no Qt event loop or network is needed.
    """

    @staticmethod
    def _mock_dialog():
        dialog = MagicMock()
        dialog._active_loaders = set()
        dialog._loader = None
        return dialog

    def test_late_completion_of_superseded_loader_keeps_replacement(self):
        """A superseded worker finishing late must not clear its replacement's reference (#74)."""
        dialog = self._mock_dialog()
        worker_a = MagicMock(spec=_SpreadsheetLoader)
        worker_b = MagicMock(spec=_SpreadsheetLoader)

        SheetsSelectionDialog._track_loader(dialog, "_loader", worker_a)
        assert dialog._loader is worker_a

        SheetsSelectionDialog._track_loader(dialog, "_loader", worker_b)  # B supersedes A; both running
        assert dialog._loader is worker_b
        assert {worker_a, worker_b} <= dialog._active_loaders

        # A finishes AFTER B started; its retire must leave B intact and still tracked.
        SheetsSelectionDialog._retire_loader(dialog, "_loader", worker_a)
        assert dialog._loader is worker_b
        assert worker_a not in dialog._active_loaders
        assert worker_b in dialog._active_loaders

    def test_current_loader_completion_clears_and_untracks(self):
        """When the CURRENT loader finishes, it clears the attribute and drops from tracking."""
        dialog = self._mock_dialog()
        worker = MagicMock(spec=_SpreadsheetLoader)

        SheetsSelectionDialog._track_loader(dialog, "_loader", worker)
        SheetsSelectionDialog._retire_loader(dialog, "_loader", worker)

        assert dialog._loader is None
        assert worker not in dialog._active_loaders

    def test_stop_loaders_waits_for_every_tracked_worker(self):
        """_stop_loaders must wait for all in-flight loaders, not just the current attribute (#74)."""
        dialog = self._mock_dialog()
        running = MagicMock(spec=_SheetMetadataLoader)
        running.isRunning.return_value = True
        running.wait.return_value = True  # finishes within the grace period
        already_done = MagicMock(spec=_SpreadsheetLoader)
        already_done.isRunning.return_value = False
        dialog._active_loaders = {running, already_done}

        SheetsSelectionDialog._stop_loaders(dialog)

        running.wait.assert_called_once_with(1000)
        already_done.wait.assert_not_called()
        assert dialog._active_loaders == set()

    def test_stop_loaders_retains_loader_that_outlives_wait(self):
        """A loader still running after wait() times out must be retained, not dropped (#74 review).

        Clearing _active_loaders unconditionally would drop the last reference to a running QThread
        (no parent, no cleanup signal), recreating the destroy/leak-while-running failure. Such a
        loader must instead be kept alive with self-cleanup wired.
        """
        from ripper.rippergui import sheets_selection_view as ssv

        ssv._orphaned_loaders.clear()
        dialog = self._mock_dialog()
        slow = MagicMock(spec=_SpreadsheetLoader)
        slow.isRunning.return_value = True
        slow.wait.return_value = False  # outlives the 1s grace period
        dialog._active_loaders = {slow}

        try:
            SheetsSelectionDialog._stop_loaders(dialog)

            slow.wait.assert_called_once_with(1000)
            assert slow in ssv._orphaned_loaders  # retained, not lost
            slow.finished.connect.assert_called()  # self-cleanup wired
            assert dialog._active_loaders == set()
        finally:
            ssv._orphaned_loaders.discard(slow)  # don't leak state into other tests
