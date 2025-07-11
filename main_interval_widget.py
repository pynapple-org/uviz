import numpy as np
import pynapple as nap
from PyQt6.QtWidgets import QApplication

import pynaviz as viz

tsd1 = nap.Tsd(t=np.arange(1000), d=np.cos(np.arange(1000) * 0.1))
tsg = nap.TsGroup(
    {i: nap.Ts(t=np.linspace(0, 100, 100 * (10 - i))) for i in range(10)},
    metadata={
        "label": np.arange(10),
        "colors": [
            "hotpink",
            "lightpink",
            "cyan",
            "orange",
            "lightcoral",
            "lightsteelblue",
            "lime",
            "lightgreen",
            "magenta",
            "pink",
        ],
        "test": ["hello", "word"] * 5,
    },
)
tsdframe = nap.TsdFrame(
    t=np.arange(1000),
    d=np.random.randn(1000, 10),
    metadata={"label": np.random.randn(10)},
)
tsdtensor = nap.TsdTensor(t=np.arange(1000), d=np.random.randn(1000, 10, 10))

app = QApplication([])

# v = viz.TsGroupWidget(tsg)
# v.plot.controller.show_interval(0, 20)
ep = [nap.IntervalSet(35, 50), nap.IntervalSet(30, 40)]
# v.plot.add_interval_sets(ep, colors=["cyan", "blue"])

# v.plot.add_interval_sets(
#     nap.IntervalSet([10, 80], [20, 100]), colors="purple", alpha=0.3
# )
ep = nap.IntervalSet(
    [0, 5, 10, 15, 20, 25, 30, 35, 40, 45, 50],
    [4.9, 9.9, 14.9, 19.9, 24.9, 29.9, 34.9, 39.9, 44.9, 49.9, 54.9],
    metadata={
        "label": ["a", "b", "c", "d", "e", "f", "g", "h", "i", "j", "k"],
        "choice": [1, 2, 0, 3, 1, 1, 0, 2, 3, 1, 3],
        "reward": [0, 0, 1, 0, 1, 1, 1, 0, 1, 0, 1],
    },
)

v2 = viz.IntervalSetWidget(ep)

# ctrl_group = ControllerGroup([v.plot, v2.plot])

# v.plot.plot_intervals(["interval_0", "interval_1"], )
# v.plot.color_by("label", 'jet')
# v.plot.sort_by("rate")

# v.show()
v2.show()


# window = QWidget()
# window.setMinimumSize(1500, 800)

# layout = QHBoxLayout()
# layout.addWidget(v)
# layout.addWidget(v2)
# window.setLayout(layout)
# window.show()
# # v = viz.TsdFrameWidget(tsdframe)
# # v.show()


# app.exit(app.exec())

if __name__ == "__main__":
    app.exit(app.exec())
