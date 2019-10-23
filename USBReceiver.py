# -*- coding: utf-8 -*-
"""
USBReceiver.py
Created on Wed Oct 16 11:38:56 2019

@author: Cody
"""

#should launch USBPcap with arguments based on command line input.
#uses a PcapPacketReceiver to process output from USBPcap.
#waits for user to quit, then tells receiver to halt.

import sys
import os
import subprocess
from PcapPacketReceiver import *
from concurrent.futures import ThreadPoolExecutor
import curses

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
    screen.addstr(3,0,"Received USB data:")
    screen.refresh()    
    max_row, max_col = screen.getmaxyx()
    
    #open USBPcap, throwing all output onto a pipe
    fd_r, fd_w = os.pipe()
    usbpcap_process = subprocess.Popen(args, stdout=fd_w)
    
    #start receiving usbpcap output and organizing it into packets
    usb_stream = os.fdopen(fd_r, "rb")
    
    
    """
    #print raw data from USB stream
    while(True):
        #print received data
        screen.addstr(5,2,usb_stream.read(int(max_col/2)-2).hex())
        c = screen.getch()
        #check for quit
        if (c == ord('q')):
            usbpcap_process.terminate()
            break
    """

    #set up receiver to process raw USB bytestream
    receiver = PcapPacketReceiver(usb_stream, loop=True)
    #set up a thread that targets receiver.run()
    with ThreadPoolExecutor(max_workers=1) as executor:
        executor.submit(receiver.run)
        while(True):
            #take packet from Q, process in some way            
            #for now, take each packet and visualize it
            if receiver.q.empty() == False:
                pBlock = receiver.q.get()
                screen.addstr(4,0,"Packet at timestamp: " + str(pBlock.ts_sec + 0.000001*pBlock.ts_usec)) 
                screen.addstr(5,0,"Packet IRP: " + pBlock.packet.IRP.hex())
                screen.addstr(6,0, "Packet function & transfer type: " + str(pBlock.packet.function) + "," + str(pBlock.packet.transfer_type))
                screen.addstr(7,0,"Packet payload: ")
                screen.addstr(8,2,pBlock.packet.payload.hex())
                screen.refresh()
            
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



if (__name__ == '__main__'):
    curses.wrapper(main)
