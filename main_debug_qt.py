"""
Test script
"""
import numpy as np
import pynapple as nap
import pynaviz as viz
from PyQt6.QtWidgets import QApplication, QWidget, QHBoxLayout, QPushButton
import sys
from pynaviz.controller import ControllerGroup


tsd1 = nap.Tsd(t=np.arange(1000), d=np.cos(np.arange(1000) * 0.1))
tsg = nap.TsGroup({
    i:nap.Ts(
        t=np.sort(np.random.uniform(0, 1000, 100*(i+1)))
    ) for i in range(10)})
tsdframe = nap.TsdFrame(t=np.arange(1000),d=np.random.randn(1000, 10))
tsdtensor = nap.TsdTensor(t=np.arange(1000), d=np.random.randn(1000, 10, 10))



app = QApplication([])

window = QWidget()
window.setMinimumSize(1500, 800)

layout = QHBoxLayout()

viz1 = viz.TsdFrameWidget(tsdframe, set_parent=True)
# viz2 = viz.TsdWidget(tsd1, set_parent=True)
viz2 = viz.TsdTensorWidget(tsdtensor, set_parent=True)

arg =  [(viz1.plot.controller, viz1.plot.renderer), (viz2.plot.controller, viz2.plot.renderer)]

ctrl_group = ControllerGroup(arg)
# ctrl_group.add(viz1.plot.controller, viz1.plot.renderer, 0)
# ctrl_group.add(viz2.plot.controller, viz2.plot.renderer, 1)

layout.addWidget(viz1)
layout.addWidget(viz2)
window.setLayout(layout)
window.show()

viz1.plot.x_vs_y(0, 1)

if __name__ == "__main__":
    app.exit(app.exec())
