import numpy as np
import matplotlib.pyplot as plt
import matplotlib.animation as animation
import random
import time
import math
import datetime as datetime

fig, ax = plt.subplots()
xdata, ydata = [], []
ln, = plt.plot([], [], '-', animated=True)

ax.set_xlim(0, 50)
ax.set_ylim(-1, 1)

def update(frame):
    xdata.append(frame)
    ydata.append(math.sin(time.time() * 10))
    if len(xdata) > 50:  # Keep only last 50 points
        xdata.pop(0)
        ydata.pop(0)
    ln.set_data(xdata, ydata)
    return ln,

ani = animation.FuncAnimation(fig, update, frames=range(0,50), blit=True, interval=10)
plt.show()