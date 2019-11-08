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
import pyformulas as pf

with open("..\\test4.pickle","rb") as f:
    blocks4 = pickle.load(f)

with open("..\\test6.pickle","rb") as f:
    blocks6 = pickle.load(f)



fig = plt.figure()

screen = pf.screen(title='Plot')

start = time.time()
for i in range(10000):
    t = time.time() - start

    x = np.linspace(t-3, t, 100)
    y = np.sin(2*np.pi*x) + np.sin(3*np.pi*x)
    plt.xlim(t-3,t)
    plt.ylim(-3,3)
    plt.plot(x, y, c='black')

    # If we haven't already shown or saved the plot, then we need to draw the figure first...
    fig.canvas.draw()

    image = np.frombuffer(fig.canvas.tostring_rgb(), dtype=np.uint8)
    image = image.reshape(fig.canvas.get_width_height()[::-1] + (3,))

    screen.update(image)

#screen.close()












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