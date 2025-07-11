"""
Action and context classes

This module provides custom Qt widgets to create interactive menus for plots.
Each menu allows the user to configure plot-specific behavior using GUI components
such as dropdowns, spin boxes, and list views. The widgets are dynamically constructed
based on metadata and plotting context.

Main Classes:
- DropdownDialog: Dynamically generates a dialog with labeled input widgets.
- ChannelList: Provides a selectable list view of plotting channels.
- MenuWidget: UI component to attach interactive actions and selections to a plot.
"""

from collections import OrderedDict
from typing import Any, Callable

import numpy as np
from PyQt6.QtCore import QPoint, QSize, Qt
from PyQt6.QtWidgets import (
    QComboBox,
    QDialog,
    QDoubleSpinBox,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QMenu,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QSpacerItem,
    QStyle,
    QVBoxLayout,
    QWidget,
)

from pynaviz.qt.drop_down_dict_builder import get_popup_kwargs
from pynaviz.qt.qt_item_models import ChannelListModel, DynamicSelectionListView
from pynaviz.utils import get_plot_attribute

WIDGET_PARAMS = {
    QComboBox: {
        "name": "setObjectName",
        "items": "addItems",
        "values": "setItemData",
        "current_index": "setCurrentIndex",
    },
    QDoubleSpinBox: {
        "name": "setObjectNAme",  # Note: typo here in key name
        "value": "setValue",
    },
}


def widget_factory(parameters: dict) -> QWidget:
    """
    Constructs a QWidget (QComboBox or QDoubleSpinBox) with specified parameters.

    Parameters
    ----------
    parameters : dict
        Dictionary containing widget configuration.

    Returns
    -------
    QWidget
        The configured widget instance.
    """
    widget_type = parameters.pop("type")
    if widget_type == QComboBox:
        widget = QComboBox()
        for arg_name, attr_name in WIDGET_PARAMS[QComboBox].items():
            method = getattr(widget, attr_name, None)
            value = parameters.get(arg_name)
            if method and value is not None:
                if arg_name == "values":
                    for i, v in enumerate(value):
                        method(i, v)
                else:
                    method(value)
    elif widget_type == QDoubleSpinBox:
        widget = QDoubleSpinBox()
        for arg_name, attr_name in WIDGET_PARAMS[QDoubleSpinBox].items():
            method = getattr(widget, attr_name, None)
            value = parameters.get(arg_name)
            if method and value is not None:
                method(value)
    else:
        raise ValueError("Unknown widget type.")
    return widget


class DropdownDialog(QDialog):
    """
    A popup dialog that dynamically creates widgets from metadata and applies a callback.

    Parameters
    ----------
    title : str
        Title of the dialog window.
    widgets : OrderedDict[str, dict]
        Keys are labels; values are widget parameter dictionaries.
    func : Callable
        Function to call when selections are made.
    ok_cancel_button : bool, optional
        Whether to display OK/Cancel buttons (default is False).
    parent : QWidget, optional
        Parent widget.
    """

    def __init__(
        self,
        title: str,
        widgets: OrderedDict[str, dict],
        func: Callable,
        ok_cancel_button: bool = False,
        parent: QWidget | None = None,
    ):
        super().__init__(parent=parent)
        self.setWindowTitle(title)
        self.setWindowModality(Qt.WindowModality.ApplicationModal)

        num_cols = min(len(widgets), 3)
        num_rows = len(widgets) // num_cols
        self.setFixedWidth(200 * num_cols)
        self.setFixedHeight(min(150 * num_rows, 400))

        self._func = func
        self.widgets: dict[int, QWidget] = {}

        main_layout = QVBoxLayout(self)

        # Scrollable area
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        scroll_content = QWidget()
        scroll_content.setSizePolicy(
            QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Minimum
        )

        grid_layout = QGridLayout()
        inner_layout = QVBoxLayout()
        inner_layout.addLayout(grid_layout)

        spacer = QSpacerItem(
            0, 0, QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Expanding
        )
        h_spacer = QSpacerItem(
            0, 0, QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum
        )
        inner_layout.addItem(spacer)

        outer_layout = QHBoxLayout()
        outer_layout.addLayout(inner_layout)
        outer_layout.addItem(h_spacer)

        scroll_content.setLayout(outer_layout)
        scroll.setWidget(scroll_content)
        main_layout.addWidget(scroll)

        # Add widgets with labels
        def make_labeled_widget(label_text: str, widget: QWidget) -> QWidget:
            label = QLabel(label_text)
            label.setSizePolicy(QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Fixed)
            widget.setSizePolicy(QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Fixed)
            wrapper = QWidget()
            layout = QHBoxLayout()
            layout.setContentsMargins(1, 0, 1, 0)
            layout.setSpacing(2)
            layout.addWidget(label)
            layout.addWidget(widget)
            wrapper.setLayout(layout)
            return wrapper

        for i, (label, params) in enumerate(widgets.items()):
            widget = widget_factory(params)
            if hasattr(widget, "currentIndexChanged"):
                widget.currentIndexChanged.connect(self.item_changed)
            if hasattr(widget, "valueChanged"):
                widget.valueChanged.connect(self.item_changed)

            row, col = divmod(i, num_cols)
            grid_layout.addWidget(make_labeled_widget(label, widget), row, col)
            self.widgets[i] = widget

        # Optional buttons
        if ok_cancel_button:
            self._update_on_selection = False
            button_layout = QHBoxLayout()
            ok_button = QPushButton("OK")
            ok_button.setDefault(True)
            cancel_button = QPushButton("Cancel")

            ok_button.clicked.connect(self.accept)
            cancel_button.clicked.connect(self.reject)

            button_layout.addStretch()
            button_layout.addWidget(cancel_button)
            button_layout.addWidget(ok_button)
            main_layout.addLayout(button_layout)
        else:
            self._update_on_selection = True

        self.adjustSize()

    def get_selections(self) -> list[Any]:
        """
        Extracts current selections from the widgets.

        Returns
        -------
        list
            List of selected values from each widget.
        """
        out = []
        for widget in self.widgets.values():
            if isinstance(widget, QComboBox):
                data = widget.currentData()
                out.append(data if data is not None else widget.currentText())
            elif isinstance(widget, QDoubleSpinBox):
                out.append(widget.value())
        return out

    def update_plot(self) -> None:
        """Calls the provided function with current widget values."""
        self._func(*self.get_selections())

    def item_changed(self) -> None:
        """Callback triggered when a widget value changes."""
        if self._update_on_selection:
            self.update_plot()

    def accept(self) -> None:
        """Override accept to call plot update before closing."""
        self.update_plot()
        return super().accept()


class ChannelList(QDialog):
    """
    A dialog listing selectable channels (e.g., for visibility toggling).

    Parameters
    ----------
    model : ChannelListModel
        Data model that holds the list of channel states.
    parent : QWidget, optional
        Parent widget.
    """

    def __init__(self, model: ChannelListModel, parent: QWidget | None = None):
        super().__init__(parent)
        self.setWindowTitle("Channel List")
        self.setWindowModality(Qt.WindowModality.ApplicationModal)
        self.setFixedSize(300, 150)

        self.view = DynamicSelectionListView(self)
        self.view.setSelectionMode(self.view.SelectionMode.ExtendedSelection)
        self.view.setModel(model)
        model.checkStateChanged.connect(self.view.on_check_state_changed)

        layout = QVBoxLayout()
        layout.addWidget(self.view)
        self.setLayout(layout)


class MenuWidget(QWidget):
    """
    Menu bar widget that allows channel selection and plot actions.

    Parameters
    ----------
    metadata : dict or pd.DataFrame or None
        Metadata associated with the plot.
    plot : _BasePlot
        The plot instance this menu is attached to.
    """

    def __init__(self, metadata: Any, plot: Any):
        super().__init__()
        self.metadata = metadata
        self.plot = plot
        self.channel_model = ChannelListModel(self.plot)
        self.channel_model.checkStateChanged.connect(self._request_draw)

        layout = QHBoxLayout()
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        icon_size = 18
        if hasattr(plot._data, "metadata"):
            self.select_button = self._make_button(
                self.show_select_menu, "SP_DialogApplyButton", icon_size
            )
            layout.addWidget(self.select_button)

        if metadata is not None and hasattr(metadata, "shape") and np.prod(metadata.shape):
            self.action_button = self._make_button(
                self.show_action_menu, "SP_FileDialogDetailedView", icon_size
            )
            layout.addWidget(self.action_button)

        layout.addStretch()
        self.setLayout(layout)
        self.setFixedHeight(icon_size + 2)

        self._action_menu()

    def _request_draw(self) -> None:
        """Request a redraw of the plot when channel states change."""
        widget = self.sender()
        materials = get_plot_attribute(self.plot, "material")
        for index, val in getattr(widget, "checks", {}).items():
            materials[index].opacity = val
        self.plot.canvas.request_draw(self.plot.animate)

    def _make_button(
        self, menu_to_show: Callable, icon_name: str, icon_size: int = 20
    ) -> QPushButton:
        """Helper to create a styled button with icon and action."""
        button = QPushButton()
        button.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        icon = self.style().standardIcon(getattr(QStyle.StandardPixmap, icon_name))
        button.setIcon(icon)
        button.setIconSize(QSize(icon_size, icon_size))
        button.setFixedSize(icon_size + 3, icon_size + 3)
        button.setFlat(True)
        button.clicked.connect(menu_to_show)
        return button

    def _action_menu(self) -> None:
        """Creates the action menu with plot operation entries."""
        self.action_menu = QMenu()
        for name, func_name in zip(
            ["Color by", "Group by", "Sort by"], ["color_by", "group_by", "sort_by"]
        ):
            action = self.action_menu.addAction(name)
            action.setObjectName(func_name)
            action.triggered.connect(self._popup_menu)

    def show_action_menu(self) -> None:
        """Displays the action menu below the button."""
        pos = self.action_button.mapToGlobal(QPoint(0, self.action_button.height()))
        self.action_menu.exec(pos)

    def show_select_menu(self) -> None:
        """Opens the channel list selection dialog."""
        dialog = ChannelList(self.channel_model, parent=self)
        dialog.exec()

    def _popup_menu(self) -> None:
        """Opens a dropdown dialog based on selected action."""
        action = self.sender()
        popup_name = action.objectName()
        kwargs = get_popup_kwargs(popup_name, self)
        if kwargs is not None:
            dialog = DropdownDialog(**kwargs)
            dialog.setEnabled(True)
            dialog.exec()
