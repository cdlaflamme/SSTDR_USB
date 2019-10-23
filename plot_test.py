# -*- coding: utf-8 -*-
"""
Created on Wed Oct 16 14:08:11 2019

@author: Cody
"""
#plot_test.py
#tests how quickly pyplot refreshes data that quickly changes

import numpy as np
import matplotlib.pyplot as plt
import time
import pickle
from PcapPacketReceiver import *

with open("test4.pickle","rb") as f:
    blocks4 = pickle.load(f)

with open("test6.pickle","rb") as f:
    blocks6 = pickle.load(f)



"""
wf = np.array([i for i in range(1,93)] + [i for i in range(92,0,-1)])
refreshRate = 5 #hertz

while(True):
    #plt.figure(1)
    plt.plot(wf)
    plt.show(block=False)
    time.sleep(5)
    wf = np.roll(wf,5)
""" 