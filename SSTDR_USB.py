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

import sys
import os
import subprocess
from PcapPacketReceiver import *
from concurrent.futures import ThreadPoolExecutor
import curses
import matplotlib.pyplot as plt

def main(screen):
    
    #read arguments, prepare to launch usbpcap
    if (len(sys.argv) != 3):
        print("Error: Please supply two arguments: filter and device address.")
        return    
    
    arg_filter = sys.argv[1]
    arg_address = sys.argv[2]
    path = "C:\\Program Files\\USBPcap\\USBPcapCMD.exe"
    args = [path, "-d", "\\\\.\\USBPcap" + str(arg_filter), "--devices", str(arg_address), "-o", "-"]

    #set up scanning window
    print("Opening scanner window...")
    screen.clear()
    screen.nodelay(True)
    screen.addstr(0,0,"Scanning on filter " + str(arg_filter) + ", address " + str(arg_address) + "...")
    screen.addstr(1,0,"Press 'q' to stop.")
    screen.addstr(3,0,"System OK.")
    screen.refresh()    
    max_row, max_col = screen.getmaxyx()
    
    #open USBPcap, throwing all output onto a pipe
    fd_r, fd_w = os.pipe()
    usbpcap_process = subprocess.Popen(args, stdout=fd_w)
    
    #start receiving usbpcap output and organizing it into packets
    usb_stream = os.fdopen(fd_r, "rb")

    #set up receiver to process raw USB bytestream
    receiver = PcapPacketReceiver(usb_stream, loop=True)
    #set up a thread that targets receiver.run()
    with ThreadPoolExecutor(max_workers=1) as executor:
        executor.submit(receiver.run)

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
                screen.addstr(5,0,"Received packet at timestamp: " + str(pBlock.ts_sec + 0.000001*pBlock.ts_usec)) 
                screen.refresh()
                
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
                            process_waveform_region(payloadString)
                            screen.addstr(7,0,"Received waveform at timestamp: " + str(pBlock.ts_sec + 0.000001*pBlock.ts_usec))
                            screen.refresh()
                            payloadString = b''
                            byteCount = 0
                elif (byteCount > 0):
                    payloadString = b''
                    byteCount = 0
            
            #check for quit
            c = screen.getch()
            if (c == ord('q')):
                screen.addstr(0,0,"Quitting: Terminating scanner...")
                screen.refresh()                
                usbpcap_process.terminate()
                
                screen.addstr(0,0, "Stopped scanner. Waiting for threads...")
                screen.refresh()
                receiver.stop() #TODO why does this hang?
                #executor.shutdown() #performed implicitly by "with" statement
                screen.addstr(0,0, "Finished. Exiting...")
                break

        
    print("All done. :)")

def process_waveform_region(pString):
    waveform = convert_waveform_region(pString)[6:-1]
    #do anything with this waveform
    plt.plot(waveform)
    plt.show()
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


if (__name__ == '__main__'):
    curses.wrapper(main)

