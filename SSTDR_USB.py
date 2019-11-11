# -*- coding: utf-8 -*-
"""
SSTDR_USB.py
Created on Wed Oct 23 13:50:16 2019

@author: Cody
"""
#should launch USBPcap with arguments based on command line input.
#uses a PcapPacketReceiver to process output from USBPcap.
#notices waveforms that are transmitted and visualizes them.
#waits for user to quit, then tells receiver to halt.

#TODO
#add testing mode, where USBPcap is not used, and instead an input file is looped forever
#need to look at and use mashaad code to perform fault detection

"""
DEPENDENCIES
- matplotlib (in conda)
- numpy (in conda)
- curses (in pip, use "windows-curses" for windows)
- pyformulas (in pip)
    - pyaudio (required by pyformulas, in conda)
    - portaudio (required by pyformulas, in conda)
"""

import sys
import os
import subprocess
from PcapPacketReceiver import *
from concurrent.futures import ThreadPoolExecutor
import curses
import matplotlib.pyplot as plt
import numpy as np
import pyformulas as pf
from collections import deque
import time

def main(screen):
    ######################################################
    ##                    STARTUP                       ##
    ######################################################
    
    #read arguments, prepare to launch usbpcap
    if (len(sys.argv) != 3):
        print("Error: Please supply two arguments: filter and device address.")
        return    
    
    arg_filter = sys.argv[1]
    arg_address = sys.argv[2]
    path = "C:\\Program Files\\USBPcap\\USBPcapCMD.exe"
    args = [path, "-d", "\\\\.\\USBPcap" + str(arg_filter), "--devices", str(arg_address), "-o", "-"]

    #set up scanning interface in curses (cscreen = curses screen)
    print("Opening scanner interface...")
    cscreen.clear()
    cscreen.nodelay(True)
    cscreen.addstr(0,0,"Scanning on filter " + str(arg_filter) + ", address " + str(arg_address) + "...")
    cscreen.addstr(1,0,"Press 'q' to stop.")
    cscreen.addstr(3,0,"System OK.")
    cscreen.refresh()    
    
    #open USBPcap, throwing all output onto a pipe
    usb_fd_r, usb_fd_w = os.pipe()
    usbpcap_process = subprocess.Popen(args, stdout=usb_fd_w)
    #start receiving usbpcap output and organizing it into packets
    usb_stream = os.fdopen(usb_fd_r, "rb")
    #set up receiver to process raw USB bytestream
    receiver = PcapPacketReceiver(usb_stream, loop=True)
    
    #prepare deque for waveform visualization; only stores 10 most recently received waveforms
    wf_deque = deque(maxlen=4)
    
    fig = plt.figure()
    plot_window = pf.screen(title='SSTDR Correlation Waveform')
    
    #set up threads:
    #first child thread: receives and interprets packets using receiver.run()
    with ThreadPoolExecutor(max_workers=3) as executor:
        rec_thread = executor.submit(receiver.run)

        payloadString = b''
        byteCount = 0
        WAVEFORM_BYTE_COUNT = 199 #every waveform region contains 199 payload bytes

        while(True):
            #take packet from Q, process in some way
            """
            goal is to identify shape of data in intermittent test, and have this
            code recognize when a sequence of packet blocks represents a
            correlation waveform. This waveform should be calculated from payload
            bytes, and either shown for visualization (pyplot?) or fed to matlab
            for processing (which is the ultimate goal).
            """
            #show some packet data so it's clear the scanner is working
            if receiver.q.empty() == False:
                pBlock = receiver.q.get()
                #cscreen.addstr(5,0,"Received packet at timestamp: " + str(pBlock.ts_sec + 0.000001*pBlock.ts_usec)) 
                #cscreen.refresh()
                
                #if received packet may be in a waveform region of the stream:
                #criteria: input (to host) from endpoint 3 and function == URB_FUNCTION_BULK_OR_INTERRUPT_TRANSFER
                if (pBlock.packet.endpoint == 0x83 and pBlock.packet.function == 0x09):
                    #if block has a payload:
                    p = pBlock.packet.payload
                    l = len(p)
                    if (l > 0):
                        payloadString = payloadString + p
                        byteCount = byteCount + l
                        if (byteCount >= WAVEFORM_BYTE_COUNT):
                            #perform processing on raw waveform
                            wf = process_waveform_region(payloadString)
                            wf_deque.append(wf)
                            #show that we've received a waveform
                            cscreen.addstr(7,0,"Received waveform at timestamp: " + str(pBlock.ts_sec + 0.000001*pBlock.ts_usec))
                            cscreen.refresh()                                                     
                            #prepare to receive next waveform region                            
                            payloadString = b''
                            byteCount = 0
                elif (byteCount > 0):
                    payloadString = b''
                    byteCount = 0
            elif len(wf_deque) > 0:
                #q was empty, we have some extra time to plot a waveform
                wf = wf_deque.popleft()
                #visualize waveform
                #code from https://stackoverflow.com/questions/40126176/fast-live-plotting-in-matplotlib-pyplot
                plt.plot(wf)
                fig.canvas.draw()
                image = np.frombuffer(fig.canvas.tostring_rgb(), dtype=np.uint8)
                image = image.reshape(fig.canvas.get_width_height()[::-1] + (3,))
                plot_window.update(image) 
            
            #check for quit
            c = cscreen.getch()
            if (c == ord('q')):
                cscreen.addstr(0,0,"Quitting: Terminating scanner...")
                cscreen.refresh()                
                usbpcap_process.terminate()                
                cscreen.addstr(0,0, "Stopped scanner. Waiting for threads...")
                cscreen.refresh()
                receiver.halt()
                #plt_thread.cancel()
                while(rec_thread.running()):
                    pass
                usb_stream.close()
                #executor.shutdown() #performed implicitly by "with" statement
                cscreen.addstr(0,0, "Finished. Exiting...")
                break

        
    print("All done. :)")

def process_waveform_region(pString):
    waveform = convert_waveform_region(pString)[6:-1]
    #we can do anything with this waveform
    return waveform

    
def convert_waveform_region(pString):
    """takes a bytestring of len 199, converts it into little-endian int16s"""
    N = 199
    Nh = int(N/2)
    concat = [0]*Nh
    for i in range(Nh):
        v1 = pString[2*i] #indexing with a scalar returns an integer
        v2 = pString[2*i+1]
        #combine , little endian
        value = ((v2<<8)+v1)
        #convert to signed integer
        if (value & 0x8000 != 0):
            value = value - 2**16
        concat[i] = value
    return concat

#deprecated. plotting moved to main thread.
def plot_waveforms(wf_deque):
    """intended to be run as a separate thread. Takes waveforms from a deque and plots them."""
    fig = plt.figure()
    plot_window = pf.screen(title='SSTDR Correlation Waveform')

    #TODO: make this dependent on a halt event
    while(True):
        #wait for deque entry
        if(len(wf_deque) > 0):
            wf = wf_deque.popleft()
            #visualize waveform
            #code from https://stackoverflow.com/questions/40126176/fast-live-plotting-in-matplotlib-pyplot
            plt.plot(wf)
            fig.canvas.draw()
            image = np.frombuffer(fig.canvas.tostring_rgb(), dtype=np.uint8)
            image = image.reshape(fig.canvas.get_width_height()[::-1] + (3,))
            plot_window.update(image)  
        #polling is bad, can't block with a deque, just sleep for a bit
        time.sleep(0.25)


if (__name__ == '__main__'):
    curses.wrapper(main)

