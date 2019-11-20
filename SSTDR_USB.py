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

"""
DEPENDENCIES
- matplotlib (in conda)
- numpy (in conda)
- curses (in pip, use "windows-curses" on windows)
- pyformulas (in pip)
    - pyaudio (required by pyformulas, in conda)
    - portaudio (required by pyformulas, in conda)
- pygame (in pip)
- pyyaml (in conda)
"""
######################################################
##                    IMPORTS                       ##
######################################################
#built in python modules
import sys
import os
import subprocess
from concurrent.futures import ThreadPoolExecutor
import traceback
import threading

#python libraries
import numpy as np
import curses
import matplotlib.pyplot as plt
import pyformulas as pf
from collections import deque
import pygame

#homegrown code
from PcapPacketReceiver import *
import fault_detection

######################################################
##                   CONSTANTS                      ##
######################################################
SCREEN_SIZE = SCREEN_X, SCREEN_Y = 900, 700
TERMINAL_Y = 200
VISUAL_Y = SCREEN_Y - TERMINAL_Y
BORDER_WIDTH = 3
BORDER_PADDING = 2

COLOR_WHITE     = (225, 225, 225)
COLOR_GREY      = (128, 128, 128)
COLOR_ORANGE    = (255, 140,   0)
COLOR_BLUE      = (  0,   0, 200)
COLOR_BLACK     = ( 10,  10,  10)

BG_COLOR = COLOR_GREY
TERMINAL_COLOR = COLOR_WHITE
WIRE_COLOR = COLOR_BLUE
TEXT_COLOR = COLOR_BLACK

PANEL_SCALE = 1/6
PANEL_PADDING = (100, 25)
WIRE_WIDTH = 2


def main(cscreen):
    ######################################################
    ##                    STARTUP                       ##
    ######################################################
    
    #read arguments, prepare to launch usbpcap
    if ([3,4].count(len(sys.argv)) == 0):
        print("Usage: python SSTDR_USB.py <filter> <device address> [layout yaml path]")
        return
    
    if (len(sys.argv) == 4):
        yaml_path = sys.argv[4]        
    else:
        yaml_path = 'default.yaml'
    
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
    halt_threads = threading.Event()
    receiver = PcapPacketReceiver(usb_stream, loop=True, halt_event=halt_threads)
    
    #prepare deque for waveform visualization; only stores a few of the most recently received waveforms. appended entries cycle out old ones
    #larger deque -> more maximum latency between visualization and actual system state
    #smaller deque -> not sure why this would be a problem (something about losing information if packets aren't received constantly)
    wf_deque = deque(maxlen=1)
    
    #prepare to visualize waveforms
    fig = plt.figure()
    plot_window = pf.screen(title='SSTDR Correlation Waveform')
    
    ######################################################
    ##                  PYGAME SETUP                    ##
    ######################################################

    #initializing pygame
    pygame.init()
    pscreen = pygame.display.set_mode(SCREEN_SIZE)
    pygame.display.set_caption("PV Fault Scanner")

    #loading assets, preparing pre-baked surfaces
    TERMINAL_FONT = pygame.font.Font(None, 40)
    STATUS_FONT = pygame.font.Font(None, 20)

    panel_surf = pygame.image.load(os.path.join("Assets", "PV_panel_CharlesMJames_CC.jpg"))
    panel_surf = pygame.transform.scale(panel_surf, (int(panel_surf.get_width()*PANEL_SCALE), int(panel_surf.get_height()*PANEL_SCALE)))
    panel_rect = panel_surf.get_rect()

    grass_surf = pygame.image.load(os.path.join("Assets", "grass.png"))
    grass_rect = grass_surf.get_rect()

    hazard_surf = pygame.image.load(os.path.join("Assets", "hazard.png"))
    hazard_rect = hazard_surf.get_rect()

    bg_surf = pygame.Surface(pscreen.get_size())
    bg_surf.convert()
    bg_rect = bg_surf.get_rect()
    bg_surf.fill(BG_COLOR)
    """
    for r in range(int(SCREEN_Y / grass_rect.h+1)):
        for c in range(int(SCREEN_X / grass_rect.w+1)):
            bg_surf.blit(grass_surf, grass_rect)
            grass_rect.move_ip(grass_rect.w,0)
        grass_rect.x = 0
        grass_rect.move_ip(0, grass_rect.h)
    """
    line_surf = pygame.Surface((SCREEN_X, BORDER_WIDTH))
    line_surf.fill(COLOR_ORANGE)
    line_rect = line_surf.get_rect()
    line_rect.y = VISUAL_Y - BORDER_WIDTH - int(BORDER_PADDING/2)
    bg_surf.blit(line_surf, line_rect)
    line_surf.fill(COLOR_BLUE)
    line_rect.move_ip(0, BORDER_WIDTH + BORDER_PADDING)
    bg_surf.blit(line_surf, line_rect)

    text_surf = STATUS_FONT.render("Scanning at 24MHz...", True, COLOR_WHITE)
    text_rect = text_surf.get_rect()
    text_rect.move_ip(3,3)
    bg_surf.blit(text_surf, text_rect)

    text_surf = STATUS_FONT.render("Selected Array Layout: " + yaml_path, True, COLOR_WHITE)
    text_rect = text_surf.get_rect()
    text_rect.x = 3
    text_rect.bottom = VISUAL_Y - BORDER_WIDTH - int(0.5*BORDER_PADDING) - 3
    bg_surf.blit(text_surf, text_rect)

    #load panel layout
    panel_layout, panel_ds = load_panel_layout(yaml_path)
    panel_cols, panel_rows = 0
    try:
        N = len(panel_ds)
        H = int((N-1)/2)
        if (layout['layout'] == 'loop'):
            panel_rows = 2
            panel_cols = H+N%2
            r = 0
            PANEL_COORDS = [(c*(PANEL_PADDING[0] + panel_rect.w), r*(PANEL_PADDING[1] + panel_rect.h)) for c in range(0,H+1)]
            if (len(panel_ds)%2):
                r = 0.5
                PANEL_COORDS.insert(H+1,(H+1)*(PANEL_PADDING[0] + panel_rect.w), r*(PANEL_PADDING[1] + panel_rect.h)))
            r = 1
            PANEL_COORDS = PANEL_COORDS + [(c*(PANEL_PADDING[0] + panel_rect.w), r*(PANEL_PADDING[1] + panel_rect.h)) for c in range(H,-1,-1)]
        
        elif(layout['layout'] == 'home-run'):
            panel_rows = 1
            panel_cols = N
            r = 0
            PANEL_COORDS = [(c*(PANEL_PADDING[0] + panel_rect.w), r*(PANEL_PADDING[1] + panel_rect.h)) for c in range(0,N)]
        else:
            raise Exception("Error: unknown layout field in layout yaml file.")
    except:
        print("Error: invalid layout yaml file.")
        return
    
    ARRAY_SIZE = (panel_cols*(panel_rect.w + PANEL_PADDING[0]), panel_rows*(panel_rect.h + PANEL_PADDING[1]))
    array_surf = pygame.Surface(ARRAY_SIZE, pygame.SRCALPHA)
    array_surf.convert()
    
    for p in PANEL_COORDS:
        panel_rect.topleft = p
        array_surf.blit(panel_surf, panel_rect)

    array_rect = array_surf.get_rect()
    array_rect.center = (int(SCREEN_X*2/3), int(VISUAL_Y/2))

    WIRE_COORDS = []
    for p in PANEL_COORDS:
        panel_rect.topleft = p
        WIRE_COORDS.append((panel_rect.center[0] + array_rect.topleft[0], panel_rect.center[1] + array_rect.topleft[1]))
    WIRE_COORDS.insert(0,(0,WIRE_COORDS[0][1]))
    WIRE_COORDS.append((0,WIRE_COORDS[-1][1]))
    pygame.draw.lines(bg_surf, WIRE_COLOR, False, WIRE_COORDS, WIRE_WIDTH)

    term_surf = pygame.Surface((SCREEN_X, TERMINAL_Y - int(BORDER_PADDING/2) - BORDER_WIDTH))
    term_surf.fill(TERMINAL_COLOR)
    term_rect = term_surf.get_rect()
    term_rect.bottom = SCREEN_Y

    ######################################################
    ##              FAULT DETECTION SETUP               ##
    ######################################################

    detector = fault_detection.Detector(fault_detection.METHOD_BLS_DEVIATION_CORRECTION)
    fault = (fault_detection.FAULT_NONE, 0)
    #TODO base this off of array layout file and distances provided within
    FEET_TO_PIXELS = 2.1
    
    ######################################################
    ##                      LOOP                        ##
    ######################################################
    
    #set up threads:
    #first child thread: receives and interprets packets using receiver.run()
    with ThreadPoolExecutor(max_workers=3) as executor:
        rec_thread = executor.submit(receiver.run)

        payloadString = b''
        byteCount = 0
        WAVEFORM_BYTE_COUNT = 199 #every waveform region contains 199 payload bytes
        
        try:
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
                    #q was empty, we have some extra time to visualize things
                    wf = np.array(wf_deque.popleft())
                    wf_i = fault_detection.spline_interpolate(wf)
                    
                    ###################################################################################################################################
                    #       PYFORMULAS: visualize waveform
                    ###################################################################################################################################
                    #code from https://stackoverflow.com/questions/40126176/fast-live-plotting-in-matplotlib-pyplot
                    plt.clf()
                    if (detector.baseline is None): 
                        plt.plot(wf_i)
                    else:
                        plt.plot(wf_i-detector.baseline)
                    fig.canvas.draw()
                    image = np.frombuffer(fig.canvas.tostring_rgb(), dtype=np.uint8)
                    image = image.reshape(fig.canvas.get_width_height()[::-1] + (3,))
                    plot_window.update(image)
                    
                    ###################################################################################################################################
                    #       PYGAME: fault visualization
                    ###################################################################################################################################
                    fault = detector.detect_faults(wf_i)
                    
                    for event in pygame.event.get():
                        if event.type == pygame.QUIT or (event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE):
                            pygame.display.quit()
                            pygame.quit()
                        if event.type == pygame.KEYDOWN:
                            if event.key == pygame.K_b:
                                detector.set_baseline(wf_i)#set baseline
                            elif event.key == pygame.K_t:
                                detector.set_terminal(wf_i)#set terminal waveform
                            elif event.key == pygame.K_LEFT:
                                detector.bls_deviation_thresh = detector.bls_deviation_thresh - 0.01 #adjust deviation threshold for peak location
                            elif event.key == pygame.K_RIGHT:
                                detector.bls_deviation_thresh = detector.bls_deviation_thresh + 0.01
                                
                    #per-frame logic here
                    is_fault = (fault[0] != fault_detection.FAULT_NONE)
                    fault_d_f = fault[1]
                    fault_d_p = fault_d_f * FEET_TO_PIXELS
                    
                    if (is_fault):
                        #TODO update this based on panel_ds so the fault is located properly
                        d = 0
                        px = WIRE_COORDS[0][0]
                        py = WIRE_COORDS[0][1]
                        hazard_point = WIRE_COORDS[-1]
                        for x,y in WIRE_COORDS[1:]:
                            step = ((x-px)**2 + (y-py)**2)**0.5
                            if (d+step >= fault_d_p):
                                hsr = (fault_d_p - d)/step #hazard step ratio
                                hazard_point = (px + (x-px)*hsr, py + (y-py)*hsr)
                                break
                            else:
                                px = x
                                py = y
                                d = d + step
                        hazard_rect.center = hazard_point
                        
                        fault_name = fault_detection.get_fault_name(fault[0])
                        fault_text_surf = TERMINAL_FONT.render(fault_name + " located at " + str(fault_d_f) + " feet", True, TEXT_COLOR)
                    else:
                        fault_text_surf = TERMINAL_FONT.render("System OK", True, TEXT_COLOR)
                    fault_text_rect = fault_text_surf.get_rect()
                    fault_text_rect.center = term_rect.center
                    
                    param_text_surf = STATUS_FONT.render("BLS deviation threshold:" + str(detector.bls_deviation_thresh), True, COLOR_WHITE)
                    param_text_rect = param_text_surf.get_rect()
                    param_text_rect.bottomright = (SCREEN_X-3, VISUAL_Y - BORDER_WIDTH - int(0.5*BORDER_PADDING) - 3)
                    
                    #drawing
                    pscreen.blit(bg_surf, bg_rect)
                    pscreen.blit(term_surf, term_rect)
                    pscreen.blit(fault_text_surf, fault_text_rect)
                    pscreen.blit(param_text_surf, param_text_rect)
                    pscreen.blit(array_surf, array_rect)
                    if (is_fault):
                        pscreen.blit(hazard_surf, hazard_rect)
                    pygame.display.flip()
                
                ###################################################################################################################################
                #       CURSES: Check for quit
                ###################################################################################################################################
                c = cscreen.getch()
                if (c == ord('q')):
                    cscreen.addstr(0,0,"Quitting: Terminating scanner...")
                    cscreen.refresh()                
                    usbpcap_process.terminate()                
                    cscreen.addstr(0,0, "Stopped scanner. Waiting for threads...")
                    cscreen.refresh()
                    receiver.halt()
                    while(rec_thread.running()):
                        pass
                    usb_stream.close()
                    #executor.shutdown() #performed implicitly by "with" statement
                    cscreen.addstr(0,0, "Finished. Exiting...")
                    break
        except:
            print("Exception Occurred:")
            print('='*40)
            traceback.print_exc(file=sys.stdout)
            print('='*40)
            
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

def load_panel_layout(yfile_path):
    #load panel layout file, determine panel locations along wire
    try:
        with open(yfile_path, "r") as f:
            data = yaml.safe_load(f)
        
        N = data['panel_count']
        panel_ds = [0]*N
        panel_ds[0] = data['header_cable_length'] + data['panel_cable_length']
        for i in range(1,N):
            panel_ds[i] = panel_ds[i-1] + 2*data['panel_cable_length'])
        #returns tuple:
        #   data: layout dictionary directly loaded from .yaml
        #   panel_ds: list of panel distances from SSTDR, in feet
        return (data, panel_ds)
        
    except:
        print("Exception Occurred:")
        print('='*40)
        traceback.print_exc(file=sys.stdout)
        print('='*40)
        return None

if (__name__ == '__main__'):
    curses.wrapper(main)

