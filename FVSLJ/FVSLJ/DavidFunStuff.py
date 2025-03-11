import threading
import signal
import os
import re
import sys
from labjack import ljm
from datetime import datetime
import math
import time

serial_number = 470031561
flag = True

def printSin():
    while 1:
        tim = time.time() / 10
        print((math.sin(tim) + 1) / 2)
        time.sleep(1)

def sinMod(handle):
    while flag:
        tim = time.time() 
        volt = (((math.sin(tim)+1) / 2) * 3) + 2
        print(volt)
        ljm.eWriteName(handle, "DAC1", volt)
        
handle = ljm.openS("ANY", "ANY", str(serial_number))
timethread = threading.Thread(target=sinMod,args=(handle,))
timethread.start()


signal.signal(signal.SIGINT, sys.exit())
signal.signal(signal.SIGTERM, sys.exit())