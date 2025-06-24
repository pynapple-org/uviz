"""
Plotting class for each pynapple object using Qt Widget.
Create a unique Qt widget for each class.
"""

import pathlib
from typing import Optional

from numpy._typing import NDArray
from PyQt6.QtWidgets import QVBoxLayout, QWidget

from .base_plot import PlotTs, PlotTsd, PlotTsdFrame, PlotTsdTensor, PlotTsGroup, PlotVideo
from .widget_menu import MenuWidget


class TsGroupWidget(QWidget):
    def __init__(self, data, index=None, size=(640, 480), set_parent=True):
        super().__init__(None)
        self.resize(*size)

        # The main layout
        layout = QVBoxLayout()
        layout.setContentsMargins(0, 0, 0, 0)  # Remove default margins
        layout.setSpacing(0)
        self.setLayout(layout)

        # Canvas
        parent = self if set_parent else None
        self.plot = PlotTsGroup(data, index=index, parent=parent)

        # Top level menu container
        self.button_container = MenuWidget(metadata=data.metadata, plot=self.plot)

        # Add overlay and canvas to layout
        layout.addWidget(self.button_container)
        layout.addWidget(self.plot.canvas)


class TsdWidget(QWidget):
    def __init__(self, data, index=None, size=(640, 480), set_parent=True):
        super().__init__(None)
        self.resize(*size)

        # The main layout
        layout = QVBoxLayout()
        layout.setContentsMargins(0, 0, 0, 0)  # Remove default margins
        layout.setSpacing(0)
        self.setLayout(layout)

        # Canvas
        parent = self if set_parent else None
        self.plot = PlotTsd(data, index=index, parent=parent)

        # Top level menu container
        self.button_container = MenuWidget(metadata={}, plot=self.plot)

        # Add overlay and canvas to layout
        layout.addWidget(self.button_container)
        layout.addWidget(self.plot.canvas)


class TsdFrameWidget(QWidget):
    def __init__(self, data, index=None, size=(640, 480), set_parent=True):
        super().__init__(None)
        self.resize(*size)

        # The main layout
        layout = QVBoxLayout()
        layout.setContentsMargins(0, 0, 0, 0)  # Remove default margins
        layout.setSpacing(0)
        self.setLayout(layout)

        # Canvas
        parent = self if set_parent else None
        self.plot = PlotTsdFrame(data, index=index, parent=parent)

        # Top level menu container
        self.button_container = MenuWidget(metadata=data.metadata, plot=self.plot)

        # Add overlay and canvas to layout
        layout.addWidget(self.button_container)
        layout.addWidget(self.plot.canvas)


class TsdTensorWidget(QWidget):
    def __init__(self, data, index=None, size=(640, 480), set_parent=True):
        super().__init__(None)
        self.resize(*size)

        # The main layout
        layout = QVBoxLayout()
        layout.setContentsMargins(0, 0, 0, 0)  # Remove default margins
        layout.setSpacing(0)
        self.setLayout(layout)

        # Canvas
        parent = self if set_parent else None
        self.plot = PlotTsdTensor(data, index=index, parent=parent)

        # Top level menu container
        self.button_container = MenuWidget(metadata={}, plot=self.plot)

        # Add overlay and canvas to layout
        layout.addWidget(self.button_container)
        layout.addWidget(self.plot.canvas)


class TsWidget(QWidget):
    def __init__(self, data, index=None, set_parent=False):
        super().__init__(None)
        parent = self if set_parent else None
        self.plot = PlotTs(data, index=index, parent=parent)


class VideoWidget(QWidget):
    def __init__(
        self,
        video_path: str | pathlib.Path,
        t: Optional[NDArray] = None,
        stream_index: int = 0,
        index=None,
        size=(640, 480),
        set_parent=True,
        show_time: Optional[float] = None,
    ):
        super().__init__(None)
        self.resize(*size)

        # The main layout
        layout = QVBoxLayout()
        layout.setContentsMargins(0, 0, 0, 0)  # Remove default margins
        layout.setSpacing(0)
        self.setLayout(layout)

        # Canvas
        parent = self if set_parent else None
        self.plot = PlotVideo(
            video_path=video_path,
            t=t,
            stream_index=stream_index,
            index=index,
            parent=parent,
            show_time=show_time,
        )

        # Top level menu container
        self.button_container = MenuWidget(metadata={}, plot=self.plot)

        # Add overlay and canvas to layout
        layout.addWidget(self.button_container)
        layout.addWidget(self.plot.canvas)
