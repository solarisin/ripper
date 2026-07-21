"""Tests for drag-move and resize interaction on the dashboard editor canvas (#42)."""

import pytest
from PySide6.QtCore import QEvent, QPointF, Qt
from PySide6.QtGui import QMouseEvent

from ripper.rippergui.dashboard.models import Dashboard, WidgetConfig, WidgetType
from ripper.rippergui.dashboard.views.dashboard_editor import DashboardEditor

# These tests instantiate Qt widgets via qtbot and drive synthetic mouse events.
pytestmark = pytest.mark.qt

CELL = 60  # DashboardCanvas.cell_size


def _editor_with_widget(qtbot, position=(0, 0), size=(2, 2), widget_id="w1"):
    """Build a DashboardEditor holding a single widget at the given grid geometry."""
    dashboard = Dashboard.create_new("Finance")
    dashboard.add_widget(
        WidgetConfig(
            id=widget_id,
            type=WidgetType.SPENDING_TREND,
            title="Spending",
            position=position,
            size=size,
        )
    )
    editor = DashboardEditor(dashboard, data_source_provider=lambda: [])
    qtbot.addWidget(editor)
    return editor, dashboard


def _mk(event_type, local, global_pos, button, buttons):
    return QMouseEvent(
        event_type,
        QPointF(*local),
        QPointF(*global_pos),
        button,
        buttons,
        Qt.KeyboardModifier.NoModifier,
    )


def _drag(container, press_local, press_global, release_global):
    """Drive a press -> move -> release gesture directly through the handlers."""
    container.mousePressEvent(
        _mk(
            QEvent.Type.MouseButtonPress,
            press_local,
            press_global,
            Qt.MouseButton.LeftButton,
            Qt.MouseButton.LeftButton,
        )
    )
    container.mouseMoveEvent(
        _mk(QEvent.Type.MouseMove, press_local, release_global, Qt.MouseButton.NoButton, Qt.MouseButton.LeftButton)
    )
    container.mouseReleaseEvent(
        _mk(
            QEvent.Type.MouseButtonRelease,
            press_local,
            release_global,
            Qt.MouseButton.LeftButton,
            Qt.MouseButton.NoButton,
        )
    )


def _click(container, local):
    """Drive a press -> release with no movement (a plain click)."""
    container.mousePressEvent(
        _mk(QEvent.Type.MouseButtonPress, local, (500, 500), Qt.MouseButton.LeftButton, Qt.MouseButton.LeftButton)
    )
    container.mouseReleaseEvent(
        _mk(QEvent.Type.MouseButtonRelease, local, (500, 500), Qt.MouseButton.LeftButton, Qt.MouseButton.NoButton)
    )


def test_drag_updates_model_position_after_apply(qtbot):
    """Dragging a widget then saving moves its model position, snapped to the grid (#42)."""
    editor, dashboard = _editor_with_widget(qtbot)
    container = editor.canvas.widgets["w1"]

    # Widget occupies (0,0) -> pixel rect (0,0,120,120). Press away from the resize grip,
    # drag by a global delta of (180, 120) -> snaps to grid position (row=2, col=3).
    _drag(container, press_local=(30, 30), press_global=(500, 500), release_global=(680, 620))

    editor.apply_canvas_state()

    assert dashboard.widgets["w1"].position == (2, 3)
    assert dashboard.widgets["w1"].position != (0, 0)


def test_plain_click_only_selects_and_leaves_position(qtbot):
    """A click without a drag selects the widget and does not move it (#42)."""
    editor, dashboard = _editor_with_widget(qtbot)
    container = editor.canvas.widgets["w1"]

    _click(container, local=(30, 30))
    editor.apply_canvas_state()

    assert editor._selected_widget_id == "w1"
    assert dashboard.widgets["w1"].position == (0, 0)
    assert dashboard.widgets["w1"].size == (2, 2)


def test_resize_updates_model_size_after_apply(qtbot):
    """Dragging the bottom-right grip resizes the widget in grid units (#42)."""
    editor, dashboard = _editor_with_widget(qtbot)
    container = editor.canvas.widgets["w1"]

    # Press inside the bottom-right resize grip (widget is 120x120), drag by (120, 60)
    # -> new pixel size (240, 180) -> grid size (width=4, height=3).
    _drag(container, press_local=(114, 114), press_global=(500, 500), release_global=(620, 560))

    editor.apply_canvas_state()

    assert dashboard.widgets["w1"].size == (4, 3)


def test_apply_bumps_updated_at_when_geometry_changes(qtbot):
    """apply_canvas_state bumps updated_at only after real geometry changes (#42)."""
    editor, dashboard = _editor_with_widget(qtbot)
    container = editor.canvas.widgets["w1"]
    before = dashboard.updated_at

    _drag(container, press_local=(30, 30), press_global=(500, 500), release_global=(680, 620))
    editor.apply_canvas_state()

    assert dashboard.updated_at > before


def test_apply_does_not_bump_updated_at_without_changes(qtbot):
    """apply_canvas_state must not bump updated_at when nothing moved (#42)."""
    editor, dashboard = _editor_with_widget(qtbot)
    before = dashboard.updated_at

    editor.apply_canvas_state()

    assert dashboard.updated_at == before


def test_moved_geometry_survives_serialization_round_trip(qtbot):
    """A dragged/resized widget's geometry round-trips through to_dict/from_dict (#42)."""
    editor, dashboard = _editor_with_widget(qtbot)
    container = editor.canvas.widgets["w1"]

    _drag(container, press_local=(30, 30), press_global=(500, 500), release_global=(680, 620))
    editor.apply_canvas_state()

    restored = Dashboard.from_dict(dashboard.to_dict())
    widget = restored.widgets["w1"]
    assert widget.position == (2, 3)
    assert isinstance(widget.position, tuple)
    assert all(isinstance(v, int) for v in widget.position)
