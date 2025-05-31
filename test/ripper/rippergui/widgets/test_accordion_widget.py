"""Tests for the AccordionWidget module."""

import unittest
from unittest.mock import Mock

import pytest
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication, QLabel

from ripper.rippergui.widgets.accordion_widget import (
    AccordionPanel,
    AccordionWidget,
    ClickableHeader,
)


@pytest.fixture(scope="session", autouse=True)
def qapp():
    """Create QApplication for the entire test session."""
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    yield app


class TestClickableHeader(unittest.TestCase):
    """Test cases for ClickableHeader."""

    def setUp(self) -> None:
        """Set up test fixtures."""
        self.header = ClickableHeader()

    def test_initialization(self) -> None:
        """Test ClickableHeader initialization."""
        self.assertIsInstance(self.header, ClickableHeader)

    def test_mouse_press_event_left_button(self) -> None:
        """Test mouse press event with left button emits clicked signal."""
        # Create a mock for the clicked signal
        clicked_mock = Mock()
        self.header.clicked.connect(clicked_mock)  # Create a real mouse event for left button
        from PySide6.QtCore import QPointF
        from PySide6.QtGui import QMouseEvent

        # Create a left mouse button press event
        event = QMouseEvent(
            QMouseEvent.Type.MouseButtonPress,
            QPointF(0, 0),  # Local position
            QPointF(0, 0),  # Scene position
            QPointF(0, 0),  # Global position
            Qt.MouseButton.LeftButton,
            Qt.MouseButton.LeftButton,
            Qt.KeyboardModifier.NoModifier,
        )

        # Trigger the mouse press event
        self.header.mousePressEvent(event)

        # Verify clicked signal was emitted
        clicked_mock.assert_called_once()

    def test_mouse_press_event_right_button(self) -> None:
        """Test mouse press event with right button does not emit clicked signal."""
        # Create a mock for the clicked signal
        clicked_mock = Mock()
        self.header.clicked.connect(clicked_mock)  # Create a real mouse event for right button
        from PySide6.QtCore import QPointF
        from PySide6.QtGui import QMouseEvent

        # Create a right mouse button press event
        event = QMouseEvent(
            QMouseEvent.Type.MouseButtonPress,
            QPointF(0, 0),  # Local position
            QPointF(0, 0),  # Scene position
            QPointF(0, 0),  # Global position
            Qt.MouseButton.RightButton,
            Qt.MouseButton.RightButton,
            Qt.KeyboardModifier.NoModifier,
        )

        # Trigger the mouse press event
        self.header.mousePressEvent(event)

        # Verify clicked signal was not emitted
        clicked_mock.assert_not_called()


class TestAccordionPanel(unittest.TestCase):
    """Test cases for AccordionPanel."""

    def setUp(self) -> None:
        """Set up test fixtures."""
        self.content_widget = QLabel("Test Content")
        self.panel = AccordionPanel("Test Panel", self.content_widget)

    def test_initialization(self) -> None:
        """Test AccordionPanel initialization."""
        self.assertIsInstance(self.panel, AccordionPanel)
        self.assertEqual(self.panel.title, "Test Panel")
        self.assertEqual(self.panel.content_widget, self.content_widget)
        self.assertTrue(self.panel.is_expanded)

    def test_toggle_panel(self) -> None:
        """Test panel toggle functionality."""
        initial_state = self.panel.is_expanded

        # Toggle the panel
        self.panel.toggle_panel()

        # Verify state changed
        self.assertNotEqual(self.panel.is_expanded, initial_state)

    def test_expand(self) -> None:
        """Test panel expansion."""
        # First collapse the panel
        self.panel.collapse()
        self.assertFalse(self.panel.is_expanded)

        # Now expand it
        self.panel.expand()
        self.assertTrue(self.panel.is_expanded)

    def test_collapse(self) -> None:
        """Test panel collapse."""
        # Panel starts expanded
        self.assertTrue(self.panel.is_expanded)

        # Collapse it
        self.panel.collapse()
        self.assertFalse(self.panel.is_expanded)

    def test_set_expanded_true(self) -> None:
        """Test setting expansion state to true."""
        # First collapse the panel
        self.panel.collapse()
        self.assertFalse(self.panel.is_expanded)

        # Set expanded to true
        self.panel.set_expanded(True)
        self.assertTrue(self.panel.is_expanded)

    def test_set_expanded_false(self) -> None:
        """Test setting expansion state to false."""
        # Panel starts expanded
        self.assertTrue(self.panel.is_expanded)

        # Set expanded to false
        self.panel.set_expanded(False)
        self.assertFalse(self.panel.is_expanded)


class TestAccordionWidget(unittest.TestCase):
    """Test cases for AccordionWidget."""

    def setUp(self) -> None:
        """Set up test fixtures."""
        self.accordion = AccordionWidget()

    def test_initialization(self) -> None:
        """Test AccordionWidget initialization."""
        self.assertIsInstance(self.accordion, AccordionWidget)
        self.assertEqual(len(self.accordion.panels), 0)

    def test_add_panel(self) -> None:
        """Test adding a panel to the accordion."""
        content_widget = QLabel("Test Content")
        panel = self.accordion.add_panel("Test Panel", content_widget)

        self.assertIsInstance(panel, AccordionPanel)
        self.assertEqual(len(self.accordion.panels), 1)
        self.assertIn(panel, self.accordion.panels)

    def test_add_panel_collapsed(self) -> None:
        """Test adding a collapsed panel to the accordion."""
        content_widget = QLabel("Test Content")
        panel = self.accordion.add_panel("Test Panel", content_widget, expanded=False)

        self.assertIsInstance(panel, AccordionPanel)
        self.assertFalse(panel.is_expanded)

    def test_remove_panel(self) -> None:
        """Test removing a panel from the accordion."""
        content_widget = QLabel("Test Content")
        panel = self.accordion.add_panel("Test Panel", content_widget)

        # Verify panel was added
        self.assertEqual(len(self.accordion.panels), 1)

        # Remove the panel
        self.accordion.remove_panel(panel)

        # Verify panel was removed
        self.assertEqual(len(self.accordion.panels), 0)
        self.assertNotIn(panel, self.accordion.panels)

    def test_expand_all(self) -> None:
        """Test expanding all panels."""
        # Add multiple panels, some collapsed
        content1 = QLabel("Content 1")
        content2 = QLabel("Content 2")
        panel1 = self.accordion.add_panel("Panel 1", content1, expanded=False)
        panel2 = self.accordion.add_panel("Panel 2", content2, expanded=False)

        # Verify both are collapsed
        self.assertFalse(panel1.is_expanded)
        self.assertFalse(panel2.is_expanded)

        # Expand all
        self.accordion.expand_all()

        # Verify both are expanded
        self.assertTrue(panel1.is_expanded)
        self.assertTrue(panel2.is_expanded)

    def test_collapse_all(self) -> None:
        """Test collapsing all panels."""
        # Add multiple panels, both expanded
        content1 = QLabel("Content 1")
        content2 = QLabel("Content 2")
        panel1 = self.accordion.add_panel("Panel 1", content1, expanded=True)
        panel2 = self.accordion.add_panel("Panel 2", content2, expanded=True)

        # Verify both are expanded
        self.assertTrue(panel1.is_expanded)
        self.assertTrue(panel2.is_expanded)

        # Collapse all
        self.accordion.collapse_all()

        # Verify both are collapsed
        self.assertFalse(panel1.is_expanded)
        self.assertFalse(panel2.is_expanded)


if __name__ == "__main__":
    unittest.main()
