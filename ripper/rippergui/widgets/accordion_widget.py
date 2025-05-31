from typing import List, Optional

from PySide6.QtCore import (
    QByteArray,
    QEasingCurve,
    QPropertyAnimation,
    Qt,
    Signal,
)
from PySide6.QtGui import QFont, QMouseEvent
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)


class ClickableHeader(QFrame):
    """A clickable header frame for accordion panels."""

    # Signal emitted when header is clicked
    clicked = Signal()

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)

    def mousePressEvent(self, event: QMouseEvent) -> None:
        """Handle mouse press events to emit clicked signal."""
        if event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit()
        super().mousePressEvent(event)


class AccordionPanel(QFrame):
    """A collapsible panel widget similar to VS Code's accordion panels."""

    # Signal emitted when panel is expanded/collapsed
    toggled = Signal(bool)

    def __init__(self, title: str, content_widget: QWidget, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.title = title
        self.content_widget = content_widget
        self.is_expanded = True
        self.animation_duration = 200

        self.setup_ui()
        self.setup_animation()

    def setup_ui(self) -> None:
        """Set up the accordion panel UI."""
        self.setFrameStyle(QFrame.Shape.StyledPanel)

        # Main layout
        self.main_layout = QVBoxLayout(self)
        self.main_layout.setContentsMargins(0, 0, 0, 0)
        self.main_layout.setSpacing(0)

        # Header (always visible)
        self.header = self.create_header()
        self.main_layout.addWidget(self.header)

        # Content container
        self.content_container = QFrame()
        self.content_container.setFrameStyle(QFrame.Shape.NoFrame)
        content_layout = QVBoxLayout(self.content_container)
        content_layout.setContentsMargins(8, 4, 8, 8)
        content_layout.addWidget(self.content_widget)

        self.main_layout.addWidget(self.content_container)

        # Set size policy
        self.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Maximum)

    def create_header(self) -> QWidget:
        """Create the clickable header for the accordion panel."""
        header = ClickableHeader(self)
        header.setFrameStyle(QFrame.Shape.StyledPanel)
        header.setFixedHeight(32)
        header.setCursor(Qt.CursorShape.PointingHandCursor)

        # Connect the clicked signal to our toggle method
        header.clicked.connect(self.toggle_panel_simple)

        # Header layout
        header_layout = QHBoxLayout(header)
        header_layout.setContentsMargins(8, 4, 8, 4)

        # Expand/collapse indicator
        self.indicator = QLabel("▼")
        self.indicator.setFont(QFont("Arial", 8))
        self.indicator.setFixedWidth(16)
        header_layout.addWidget(self.indicator)

        # Title label
        self.title_label = QLabel(self.title)
        title_font = QFont()
        title_font.setBold(True)
        self.title_label.setFont(title_font)
        header_layout.addWidget(self.title_label)

        # Spacer
        header_layout.addStretch()

        return header

    def setup_animation(self) -> None:
        """Set up the smooth expand/collapse animation."""
        self.animation = QPropertyAnimation(self.content_container, QByteArray(b"maximumHeight"))
        self.animation.setDuration(self.animation_duration)
        self.animation.setEasingCurve(QEasingCurve.Type.OutCubic)

    def toggle_panel(self, event: Optional[QMouseEvent] = None) -> None:
        """Toggle the panel expansion state."""
        if self.is_expanded:
            self.collapse()
        else:
            self.expand()

    def toggle_panel_simple(self) -> None:
        """Simple toggle method without event parameter for use with ClickableHeader."""
        self.toggle_panel()

    def expand(self) -> None:
        """Expand the panel to show content."""
        if not self.is_expanded:
            self.is_expanded = True
            self.indicator.setText("▼")

            # Calculate target height
            self.content_container.setMaximumHeight(16777215)  # Remove limit temporarily
            content_height = self.content_widget.sizeHint().height() + 12  # Add padding

            # Animate expansion
            self.animation.setStartValue(0)
            self.animation.setEndValue(content_height)
            self.animation.finished.connect(lambda: self.content_container.setMaximumHeight(16777215))
            self.animation.start()

            self.toggled.emit(True)

    def collapse(self) -> None:
        """Collapse the panel to hide content."""
        if self.is_expanded:
            self.is_expanded = False
            self.indicator.setText("▶")

            # Get current height and animate to 0
            current_height = self.content_container.height()
            self.animation.setStartValue(current_height)
            self.animation.setEndValue(0)
            self.animation.finished.connect(lambda: self.content_container.setMaximumHeight(0))
            self.animation.start()

            self.toggled.emit(False)

    def set_expanded(self, expanded: bool) -> None:
        """Programmatically set the expansion state."""
        if expanded != self.is_expanded:
            if expanded:
                self.expand()
            else:
                self.collapse()


class AccordionWidget(QWidget):
    """Container widget that holds multiple accordion panels."""

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.panels: List[AccordionPanel] = []
        self.setup_ui()

    def setup_ui(self) -> None:
        """Set up the accordion container UI."""
        # Main layout
        self.main_layout = QVBoxLayout(self)
        self.main_layout.setContentsMargins(0, 0, 0, 0)
        self.main_layout.setSpacing(1)

        # Add stretch at the bottom to push panels to the top
        self.main_layout.addStretch()

    def add_panel(self, title: str, content_widget: QWidget, expanded: bool = True) -> AccordionPanel:
        """Add a new panel to the accordion."""
        panel = AccordionPanel(title, content_widget)
        panel.set_expanded(expanded)

        # Insert before the stretch
        self.main_layout.insertWidget(len(self.panels), panel)
        self.panels.append(panel)

        return panel

    def remove_panel(self, panel: AccordionPanel) -> None:
        """Remove a panel from the accordion."""
        if panel in self.panels:
            self.panels.remove(panel)
            self.main_layout.removeWidget(panel)
            panel.deleteLater()

    def expand_all(self) -> None:
        """Expand all panels."""
        for panel in self.panels:
            panel.expand()

    def collapse_all(self) -> None:
        """Collapse all panels."""
        for panel in self.panels:
            panel.collapse()
