"""
Widget for displaying a Google Spreadsheet thumbnail and name in the ripper application.

This module provides SpreadsheetThumbnailWidget, a Qt widget that displays a spreadsheet's thumbnail image and name,
emits signals when the thumbnail is loaded or the widget is selected, and handles thumbnail loading from cache or API.
"""

from loguru import logger
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QMouseEvent, QPixmap
from PySide6.QtWidgets import QFrame, QLabel, QVBoxLayout, QWidget

from ripper.ripperlib.defs import LoadSource, SpreadsheetProperties
from ripper.ripperlib.sheets_backend import retrieve_thumbnail


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

        # Check if the text needs to be elided
        if font_metrics.horizontalAdvance(self.spreadsheet_properties.name) > available_width:
            # Elide the text (add ... at the end)
            elided_text = font_metrics.elidedText(
                self.spreadsheet_properties.name, Qt.TextElideMode.ElideMiddle, available_width
            )
            self.spreadsheet_properties.name = elided_text

        self.name_label = QLabel(self.spreadsheet_properties.name)
        self.name_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.name_label.setWordWrap(False)
        self.name_label.setFixedWidth(180)
        self.name_label.setMaximumHeight(30)
        self.name_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self.name_label.setToolTip(tooltip)

        layout.addWidget(self.thumbnail_label)
        layout.addWidget(self.name_label)

        thumb_bytes: bytes | None = None
        if len(spreadsheet_properties.thumbnail_link) > 0:
            logger.debug(
                "Loading thumbnail for spreadsheet {id}: thumbnailLink: {link}".format(
                    id=self.spreadsheet_properties.id, link=self.spreadsheet_properties.thumbnail_link
                )
            )
            thumb_bytes, source = retrieve_thumbnail(
                self.spreadsheet_properties.id, self.spreadsheet_properties.thumbnail_link
            )
            self.thumbnail_loaded.emit(source)
        else:
            thumb_bytes = None
            logger.debug(
                "No thumbnailLink provided for spreadsheet {name} : {id}".format(
                    name=self.spreadsheet_properties.name, id=self.spreadsheet_properties.id
                )
            )
            self.thumbnail_loaded.emit(LoadSource.NONE)

        if thumb_bytes:
            pixmap = QPixmap()
            pixmap.loadFromData(thumb_bytes)
            self.thumbnail_label.setPixmap(pixmap)
        else:
            self.set_default_thumbnail()

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
