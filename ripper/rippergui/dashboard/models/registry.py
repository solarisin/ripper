"""Widget registry for dashboard widgets."""

from typing import TYPE_CHECKING, Callable, Dict, Optional, Type, TypeVar

from .widget_types import WidgetType

if TYPE_CHECKING:
    from .widgets import BaseWidget

    BaseWidgetType = Type["BaseWidget"]
else:
    BaseWidgetType = Type[object]

# Widget registry for dynamic widget creation
WIDGET_REGISTRY: Dict[WidgetType, BaseWidgetType] = {}

T = TypeVar("T", bound=BaseWidgetType)


def register_widget(widget_type: WidgetType) -> Callable[[T], T]:
    """Register a widget class with the given type.

    Args:
        widget_type: The widget type to register

    Returns:
        A decorator that registers the widget class
    """

    def decorator(widget_class: T) -> T:
        WIDGET_REGISTRY[widget_type] = widget_class
        return widget_class

    return decorator


def get_widget_class(widget_type: WidgetType) -> Optional[BaseWidgetType]:
    """Get a widget class by type.

    Args:
        widget_type: The widget type to look up

    Returns:
        The widget class if found, None otherwise
    """
    return WIDGET_REGISTRY.get(widget_type)
