"""
Test script
"""
import numpy as np
import pynapple as nap
from PyQt6.QtWidgets import QApplication
import pynaviz as viz
from qt_material import apply_stylesheet

tsd1 = nap.Tsd(t=np.arange(1000), d=np.cos(np.arange(1000) * 0.1))
tsg = nap.TsGroup({
    i:nap.Ts(
        t=np.linspace(0, 100, 100*(10-i))
    ) for i in range(10)},
    metadata={
        "label":np.arange(10),
        "colors":["hotpink","lightpink","cyan","orange","lightcoral","lightsteelblue","lime","lightgreen","magenta","pink"],
        "test": ["hello", "word"]*5,
        }
    )
tsdframe = nap.TsdFrame(t=np.arange(1000),d=np.random.randn(1000, 10), metadata={"label":np.random.randn(10)})
tsdtensor = nap.TsdTensor(t=np.arange(1000), d=np.random.randn(1000, 10, 10))



app = QApplication([])
apply_stylesheet(app, theme='dark_cyan.xml')
# viz.TsdWidget(tsd1).show()
# viz.TsdTensorWidget(tsdtensor).show()
v = viz.TsGroupWidget(tsg)
v.plot.controller.show_interval(0, 20)
# v.plot.color_by("label", 'jet')
# v.plot.sort_by("rate")
v.show()
# v = viz.TsdFrameWidget(tsdframe)
# v.show()

if __name__ == "__main__":
    app.exit(app.exec())
