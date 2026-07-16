"""
Widget for displaying a Google Spreadsheet thumbnail and name in the ripper application.

This module provides SpreadsheetThumbnailWidget, a Qt widget that displays a spreadsheet's thumbnail image and name,
emits signals when the thumbnail is loaded or the widget is selected, and handles thumbnail loading from cache or API.
"""

from loguru import logger
from PySide6.QtCore import Qt, QThread, Signal, Slot
from PySide6.QtGui import QMouseEvent, QPixmap
from PySide6.QtWidgets import QFrame, QLabel, QVBoxLayout, QWidget

from ripper.ripperlib.defs import LoadSource, SpreadsheetProperties
from ripper.ripperlib.sheets_backend import retrieve_thumbnail


class _ThumbnailLoader(QThread):
    """Background worker that fetches a single spreadsheet's thumbnail (cache or network).

    ``retrieve_thumbnail`` reads the DB and, on a miss, performs a network download; doing that
    in the widget constructor blocked the GUI thread once per spreadsheet. This runs it off-thread
    and emits the bytes back to the widget.

    Signals:
        loaded (object, object): Emitted with ``(image_bytes, LoadSource)`` when the fetch finishes
            (``image_bytes`` is empty on failure).
    """

    loaded: Signal = Signal(object, object)  # type: ignore[misc]

    def __init__(self, spreadsheet_id: str, thumbnail_link: str) -> None:
        # Not parented to the widget: the widget can be destroyed (dialog closed) while this runs,
        # so lifetime is managed via _active_thumbnail_loaders instead of Qt parent ownership.
        super().__init__()
        self._spreadsheet_id = spreadsheet_id
        self._thumbnail_link = thumbnail_link

    def run(self) -> None:
        """Fetch the thumbnail in the background."""
        try:
            data, source = retrieve_thumbnail(self._spreadsheet_id, self._thumbnail_link)
        except Exception as exc:  # retrieve_thumbnail already guards downloads; belt-and-suspenders
            logger.error(f"Error loading thumbnail for spreadsheet {self._spreadsheet_id}: {exc}")
            data, source = b"", LoadSource.NONE
        self.loaded.emit(data, source)


# Thumbnail loaders are kept alive here (a reference that outlives the widget) so their QThread
# wrappers aren't GC'd — or force-destroyed with a closing dialog — while still running. Each
# removes itself when it finishes.
_active_thumbnail_loaders: set[_ThumbnailLoader] = set()


class SpreadsheetThumbnailWidget(QFrame):
    """
    Widget to display a Google Spreadsheet thumbnail and its name.

    Signals:
        thumbnail_loaded (LoadSource): Emitted when the thumbnail is loaded (from cache, API, or not found).
        spreadsheet_selected (SpreadsheetProperties): Emitted when the widget is selected by the user.

    This widget shows a thumbnail image of a Google Spreadsheet along with its name.
    It loads the thumbnail from cache if available, or from the Google API if not.
    """

    # Signal emitted when thumbnail is loaded
    thumbnail_loaded = Signal(LoadSource)

    # Signal emitted when this widget is selected
    spreadsheet_selected = Signal(SpreadsheetProperties)

    def __init__(self, spreadsheet_properties: SpreadsheetProperties, parent: QWidget) -> None:
        """
        Initialize the thumbnail widget, set up UI, and load the thumbnail image.

        Args:
            spreadsheet_properties (SpreadsheetProperties): Object containing spreadsheet information.
            parent (QWidget): Parent widget.

        Side effects:
            Sets up the widget UI, loads the thumbnail, and emits thumbnail_loaded signal.
        """
        super().__init__(parent)
        self.spreadsheet_properties: SpreadsheetProperties = spreadsheet_properties

        # Configure frame appearance
        self.setFrameShape(QFrame.Shape.Box)
        self.setFrameShadow(QFrame.Shadow.Raised)
        self.setLineWidth(1)
        self.setMinimumSize(200, 200)
        self.setMaximumSize(200, 200)

        # Set up layout
        layout = QVBoxLayout(self)

        # Set some info about the sheet as the tooltip
        tooltip = "{:9} {}\n{:9} {}\n{:9} {}".format(
            "Name:",
            self.spreadsheet_properties.name,
            "Created:",
            self.spreadsheet_properties.created_time,
            "Modified:",
            self.spreadsheet_properties.modified_time,
        )

        # Thumbnail image
        self.thumbnail_label = QLabel()
        self.thumbnail_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.thumbnail_label.setMinimumSize(180, 150)
        self.thumbnail_label.setMaximumSize(180, 150)
        self.thumbnail_label.setScaledContents(True)
        self.thumbnail_label.setToolTip(tooltip)

        # Create a QFontMetrics object to measure text width
        font_metrics = self.fontMetrics()
        # Get available width (slightly less than thumbnail width)
        available_width = 170

        # Compute a display-only string: elide a too-wide name for the label only. The elided text
        # must never be written back to spreadsheet_properties.name — that instance is shared (it is
        # emitted via spreadsheet_selected and consumed downstream for the details panel and the
        # auto-generated data-source name), so mutating it would corrupt the real model data (#47).
        display_name = self.spreadsheet_properties.name
        if font_metrics.horizontalAdvance(display_name) > available_width:
            display_name = font_metrics.elidedText(display_name, Qt.TextElideMode.ElideMiddle, available_width)

        self.name_label = QLabel(display_name)
        self.name_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.name_label.setWordWrap(False)
        self.name_label.setFixedWidth(180)
        self.name_label.setMaximumHeight(30)
        self.name_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self.name_label.setToolTip(tooltip)

        layout.addWidget(self.thumbnail_label)
        layout.addWidget(self.name_label)

        # Show a placeholder immediately, then load the real thumbnail off the GUI thread so the
        # selection dialog never blocks on N sequential downloads while it is being built (#35).
        self.set_default_thumbnail()

        if len(spreadsheet_properties.thumbnail_link) > 0:
            logger.debug(
                "Loading thumbnail for spreadsheet {id}: thumbnailLink: {link}".format(
                    id=self.spreadsheet_properties.id, link=self.spreadsheet_properties.thumbnail_link
                )
            )
            loader = _ThumbnailLoader(self.spreadsheet_properties.id, self.spreadsheet_properties.thumbnail_link)
            _active_thumbnail_loaders.add(loader)
            loader.loaded.connect(self._on_thumbnail_loaded)  # bound method: auto-disconnected if widget dies
            loader.loaded.connect(lambda *_, w=loader: _active_thumbnail_loaders.discard(w))
            loader.finished.connect(loader.deleteLater)
            loader.start()
        else:
            logger.debug(
                "No thumbnailLink provided for spreadsheet {name} : {id}".format(
                    name=self.spreadsheet_properties.name, id=self.spreadsheet_properties.id
                )
            )
            self.thumbnail_loaded.emit(LoadSource.NONE)

    @Slot(object, object)
    def _on_thumbnail_loaded(self, thumb_bytes: bytes, source: LoadSource) -> None:
        """Apply a fetched thumbnail on the GUI thread, falling back to the placeholder on failure."""
        if thumb_bytes:
            pixmap = QPixmap()
            pixmap.loadFromData(thumb_bytes)
            if not pixmap.isNull():
                self.thumbnail_label.setPixmap(pixmap)
            else:
                logger.debug(f"Thumbnail data for spreadsheet {self.spreadsheet_properties.id} was not a valid image")
                self.set_default_thumbnail()
        else:
            self.set_default_thumbnail()
        self.thumbnail_loaded.emit(source)

    def set_default_thumbnail(self) -> None:
        """
        Set a default thumbnail for the sheet.

        Creates a simple colored rectangle as a placeholder if no thumbnail is available.
        """
        pixmap = QPixmap(180, 150)
        pixmap.fill(Qt.GlobalColor.lightGray)
        self.thumbnail_label.setPixmap(pixmap)

    def mousePressEvent(self, event: QMouseEvent) -> None:
        """
        Handle mouse press events to select this spreadsheet.

        Args:
            event: Mouse event
        """
        super().mousePressEvent(event)
        self.setFrameShadow(QFrame.Shadow.Sunken)
        self.spreadsheet_selected.emit(self.spreadsheet_properties)

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:
        """
        Handle mouse release events.

        Args:
            event: Mouse event
        """
        super().mouseReleaseEvent(event)
        self.setFrameShadow(QFrame.Shadow.Raised)
