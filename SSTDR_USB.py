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

"""
DEPENDENCIES
- USBPcap installation
- libusb-1.0.dll (for pyusb. needs to be found in system PATH. solves "No backend available" from pyusb)
- matplotlib (in conda)
- numpy (in conda)
- curses (in pip, use "windows-curses" on windows)
- pyformulas (in pip)
    - pyaudio (required by pyformulas, in conda)
    - portaudio (required by pyformulas, in conda)
- pygame (in pip)
- pyyaml (in conda)
- pyusb (in pip)
- scipy (conda)
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
import time
from collections import deque

#python libraries
import numpy as np
import curses
import matplotlib.pyplot as plt
import pyformulas as pf
import pygame
import yaml
import usb
import datetime as dt
import re

#homegrown code
from PcapPacketReceiver import *
import fault_detection
import ui_elements as ui

######################################################
##                   CONSTANTS                      ##
######################################################
USE_CURSES = True
VERIFY_WAVEFORMS = True
DEBUG_LOG = True
DEBUG_VERIFICATION = False
VERBOSE_LOGGING = False
DEBUG_LAYOUT = True

#FAULT_DETECTION_METHOD = fault_detection.METHOD_NONE
FAULT_DETECTION_METHOD = fault_detection.METHOD_BLS_PEAKS
#FAULT_DETECTION_METHOD = fault_detection.METHOD_LOW_PASS_PEAKS
#FAULT_DETECTION_METHOD = fault_detection.METHOD_BLS_DEVIATION_CORRECTION


SCREEN_SIZE = SCREEN_X, SCREEN_Y = 800, 480
TERMINAL_Y = 100
VISUAL_Y = SCREEN_Y - TERMINAL_Y
BORDER_WIDTH = 3
BORDER_PADDING = 2

COLOR_WHITE     = (225, 225, 225)
COLOR_GREY      = (128, 128, 128)
COLOR_ORANGE    = (255, 140,   0)
COLOR_BLUE      = (  0,   0, 200)
COLOR_BLACK     = ( 10,  10,  10)
COLOR_RED       = ( 200,  0,   0)

BG_COLOR = COLOR_GREY
TERMINAL_COLOR = COLOR_WHITE
WIRE_COLOR = COLOR_BLUE
TEXT_COLOR = COLOR_BLACK
CONNECTOR_COLOR = COLOR_RED

PANEL_SCALE = 1/15
PANEL_PADDING = (50, 50)
WIRE_WIDTH = 2
PANEL_SCREEN_X_RATIO = 1/2+1/8
CONNECTOR_SIZE = 5
CONNECTOR_WIDTH = WIRE_WIDTH

######################################################
##                 DEVICE SUPPORT                   ##
######################################################

DEVICE_PROTOTYPE = 0 #such as the UF lab's PCB SSTDR
DEVICE_COMMERCIAL = 1 #such as the commercial devices available at the U and livewire

######################################################
##               STATE DEFINITION                   ##
######################################################

#struct for variables controlled by buttons, that thus need to be passable to functions out of main scope
class MonitorState:
    def __init__(self):
        self.logging = False #is the system recording data?
        self.measurement_counter = 0 #the number of measurements to take before stopping logging (if 0, never stop)
        self.log_number = 0 #the current log number (groups like measurements by assigning all the same number)
        self.session_number = 0 #the current session number (increases by 1 every time the software is launched & pointed at the same file)
        self.file_has_header = False #has the system yet to write the frst data row? (if so, write the header row in addition to data)
        self.last_log_time = dt.datetime.now()
        self.next_log_time = dt.datetime.now()
        self.device_class = None
        
def main(cscreen = None):
    ######################################################
    ##                    STARTUP                       ##
    ######################################################
    
    #default values
    arg_filter = None
    arg_address = None
    input_path = "NREL_sequence_canadian_1.csv"
    file_mode = False
    output_path = "SSTDR_waveforms.csv"
    yaml_path = 'default.yaml'
    time_interval = -1
    debug_log_path = 'log.txt'
    baseline_indices = [0]
    terminal_indices = [0]
    
    #read cmd line arguments
    valid_args = ['-yaml', 'y', '-filter', '-f', '-address', '-a', '-file', '-out', '-o', '-curses', '-c', '-no-curses', '-nc', '-interval', '-i', '-t', '-bli','-tli','-ti']
    args = {}
    skip = False
    for i,arg in enumerate(sys.argv):
        if skip:
            skip = False
            continue #only look at args in loop
        if arg in valid_args:
            skip = True #skip next word; we use it as a value here
            if (i+1 < len(sys.argv)):
                value = sys.argv[i+1]
        if arg in ['-yaml', '-y']:
            yaml_path = value
        elif arg in ['-filter', '-f']:
            arg_filter = int(value)
        elif arg in ['-address', '-a']:
            arg_address = int(value)
        elif arg in ['-file']:
            file_mode = True
            input_path = value
        elif arg in ['-bli']:
            baseline_indices = [int(x) for x in value.split(',')]
        elif arg in ['-tli', '-ti']:
            terminal_indices = [int(x) for x in value.split(',')]
        elif arg in ['-out', '-o']:
            output_path = value
        elif arg in ['-interval', '-i', '-t']:
            try:
                time_interval = int(value)
            except:
                if value in ['h', 'hour']:
                    time_interval = 3600
                elif value in ['m', 'min', 'minute']:
                    time_interval = 60
                elif value in ['s', 'second']:
                    time_interval = 1
        #elif arg in ['-curses', '-c']:
        #    USE_CURSES = True
        #    skip = False
        #elif arg in ['-no-curses', '-nc']:
        #    USE_CURSES = False
        #    skip = False
    
    #repotr session start & info in log
    if DEBUG_LOG:
        debug_log(debug_log_path, "===========================================================================")
        debug_log(debug_log_path, "STARTING SESSION")
        debug_log(debug_log_path, "===========================================================================")
        debug_log(debug_log_path, "Yaml path: "+yaml_path)
        debug_log(debug_log_path, "Data input file: "+("N/A" if not file_mode else input_path))
        debug_log(debug_log_path, "Output file: "+output_path)
        debug_log(debug_log_path, "Time interval: "+str(time_interval))
    #prepare usb sniffing
    #create logging state
    state = MonitorState()
    if not file_mode and (arg_filter is None or arg_address is None):
        #auto-detect an SSTDR device. depending on the device, determine the device class (which influences data extraction)
        #try to find prototype device
        sstdr_device = usb.core.find(idVendor=0x067b, idProduct=0x2303)
        if sstdr_device is not None:
            state.device_class = DEVICE_PROTOTYPE
        else:
            #try to find commercial device
            sstdr_device = usb.core.find(idVendor=7214,idProduct=5)# constants for devices tested with Sam Kingston. (WILMA & ARNOLD)
            if sstdr_device is not None:
                state.device_class = DEVICE_COMMERCIAL
        if sstdr_device is None:
            print("Error: Could not automatically find SSTDR device. Either restart it or provide filter/address manually.")
            return
        arg_filter  = sstdr_device.bus
        arg_address = sstdr_device.address
    
    usb_path = "C:\\Program Files\\USBPcap\\USBPcapCMD.exe"
    usb_args = [usb_path, "-d", "\\\\.\\USBPcap" + str(arg_filter), "--devices", str(arg_address), "-o", "-"]
    
    if DEBUG_LOG:
        debug_log(debug_log_path, "Opened device: Filter "+str(arg_filter)+", Address "+str(arg_address))
        debug_log(debug_log_path, "Device Class: "+str(state.device_class))
    
    #prepare output file for logging
    with open(output_path, "a+") as out_f:
        out_f.seek(0,0)
        first_char = out_f.read(1)
        if (first_char == ''):
            #file did not exist or is empty. write header row; set session/log index to 0
            state.file_has_header = False
            state.session_number = 0
            state.log_number = 0
        else:
            #file was not empty. jump almost to end, read last line, extract session index
            #"read up until start of last line" code from S.O. user Trasp: https://stackoverflow.com/questions/3346430/what-is-the-most-efficient-way-to-get-first-and-last-line-of-a-text-file/3346788
            with open(output_path, "rb") as f:
                f.seek(-2, os.SEEK_END)     # Jump to the second last byte.
                while f.read(1) != b"\n":   # Until EOL is found...
                    f.seek(-2, os.SEEK_CUR) # ...jump back the read byte plus one more.
                last = f.readline()         # Read last line as bytes.
            state.file_has_header = True
            state.session_number = 1+int(chr(int.from_bytes(last.split(b',')[0],'little'))) #assumes little endian, and that session index is present in column 0 (as will be standard in the future)
            state.log_number = 0

    #set up scanning interface in curses (cscreen = curses screen)
    print("Opening scanner interface...")
    if not(cscreen is None):
        cscreen.clear()
        cscreen.nodelay(True)
        if (file_mode):
            cscreen.addstr(0,0,"Playing back input file: '" + input_path +"'...")
        else:
            cscreen.addstr(0,0,"Scanning on filter " + str(arg_filter) + ", address " + str(arg_address) + "...")
        cscreen.addstr(1,0,"Press 'q' to stop.")
        cscreen.addstr(3,0,"System OK.")
        cscreen.refresh()    
    else:
        print("Scanning on filter " + str(arg_filter) + ", address " + str(arg_address) + "...")
    
    if (not file_mode):
        #open USBPcap, throwing all output onto a pipe
        usb_fd_r, usb_fd_w = os.pipe()
        usbpcap_process = subprocess.Popen(usb_args, stdout=usb_fd_w)
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
    FONT_PATH = os.path.join("Assets", "Titillium-Regular.otf")
    TERMINAL_FONT = pygame.font.Font(FONT_PATH, 40)
    STATUS_FONT = pygame.font.Font(FONT_PATH, 20)

    panel_surf = pygame.image.load(os.path.join("Assets", "PV_panel_CharlesMJames_CC.jpg"))
    panel_surf = pygame.transform.scale(panel_surf, (int(panel_surf.get_width()*PANEL_SCALE), int(panel_surf.get_height()*PANEL_SCALE)))
    panel_rect = panel_surf.get_rect()

    #grass_surf = pygame.image.load(os.path.join("Assets", "grass.png"))
    #grass_rect = grass_surf.get_rect()

    hazard_surf = pygame.image.load(os.path.join("Assets", "hazard.png"))
    hazard_rect = hazard_surf.get_rect()

    bg_surf = pygame.Surface(pscreen.get_size())
    bg_surf.convert()
    bg_rect = bg_surf.get_rect()
    bg_surf.fill(BG_COLOR)
    
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
    panel_layout, connector_ds, panel_length = load_panel_layout(yaml_path)
    panel_cols = panel_rows = 0
    try:
        N = len(connector_ds) #number of connectors; = (panel count)+1
        P = N-1 #number of panels
        H = int(P/2)-1 #H for half; the number of panels in one row
        if (panel_layout['layout'] == 'loop'):
            panel_rows = 2
            panel_cols = int(P/2+0.5)
            r = 0
            PANEL_COORDS = [(c*(PANEL_PADDING[0] + panel_rect.w), r*(PANEL_PADDING[1] + panel_rect.h)) for c in range(0,H+1)] #pixel coordinates for panels in top row
            CONNECTOR_COORDS = [(x - PANEL_PADDING[0],y) for x,y in PANEL_COORDS] #pixel coordinates of MC-4 connectors for top row; just bisects the panel padding
            
            #WIRE_COORDS.append((panel_rect.center[0] + array_rect.topleft[0], panel_rect.center[1] + array_rect.topleft[1])) #places wire nodes at each panel center

            if (P%2 == 1):
                #add odd panel
                r = 0.5
                new_panel_coord = ((H+1)*(PANEL_PADDING[0] + panel_rect.w), r*(PANEL_PADDING[1] + panel_rect.h)) #central panel for odd panel counts
                PANEL_COORDS = PANEL_COORDS + [new_panel_coord]
                #add connectors diagonally positioned before & after odd panel
                CONNECTOR_COORDS = CONNECTOR_COORDS + [(new_panel_coord[0] - PANEL_PADDING[0], new_panel_coord[1] - PANEL_PADDING[1]/2**0.5)]
                CONNECTOR_COORDS = CONNECTOR_COORDS + [(new_panel_coord[0] - PANEL_PADDING[0], new_panel_coord[1] + PANEL_PADDING[1]/2**0.5)]
            else:
                #add connector coord vertically between the top & bottom panels
                CONNECTOR_COORDS = CONNECTOR_COORDS + [(PANEL_COORDS[-1][0], PANEL_COORDS[-1][1]+0.5*PANEL_PADDING[1])]
            r = 1
            bottom_panel_coords = [(c*(PANEL_PADDING[0] + panel_rect.w), r*(PANEL_PADDING[1] + panel_rect.h)) for c in range(H,-1,-1)] #pixel coordinates for panels in bottom row
            bottom_connector_coords = [(x - PANEL_PADDING[0], y) for x,y in bottom_panel_coords] #pixel coordinates of MC-4 connectors for bottom row; just bisects the panel padding
            if (P%2 == 1):
                #amend first connector from the bottom row to be diagonally positioned (we placed a diagonal one earlier, just remove the first one
                #bottom_connector_coords = bottom_connector_coords[1:]
                pass
            PANEL_COORDS = PANEL_COORDS + bottom_panel_coords
            CONNECTOR_COORDS= CONNECTOR_COORDS+ bottom_connector_coords
            
        elif(panel_layout['layout'] == 'home-run'):
            panel_rows = 1
            panel_cols = N
            r = 0
            PANEL_COORDS = [(c*(PANEL_PADDING[0] + panel_rect.w), r*(PANEL_PADDING[1] + panel_rect.h)) for c in range(0,N)] #one long row, with a home-run leading all the way back
            CONNECTOR_COORDS = [(x - PANEL_PADDING[0]/2+array_rect.topleft[0],y+array_rect.topleft[1]) for x,y in PANEL_COORDS] #pixel coordinates of MC-4 connectors for top row; just bisects the panel padding
        else:
            raise Exception("Error: unknown layout field in layout yaml file.")
    except:
        print("Error: invalid layout yaml file.")
        print("Exception:")
        print('='*40)
        traceback.print_exc(file=sys.stdout)
        print('='*40)
        if DEBUG_LOG:
            debug_log(debug_log_path, "Error: invalid layout yaml file.")
        return
    
    #array surface, panels are blitted onto this
    ARRAY_SIZE = (panel_cols*(panel_rect.w + PANEL_PADDING[0]), panel_rows*(panel_rect.h + PANEL_PADDING[1]))
    array_surf = pygame.Surface(ARRAY_SIZE, pygame.SRCALPHA)
    array_surf.convert()
    
    for p in PANEL_COORDS:
        panel_rect.topleft = p
        array_surf.blit(panel_surf, panel_rect)

    array_rect = array_surf.get_rect()
    array_rect.center = (int(SCREEN_X*PANEL_SCREEN_X_RATIO), int(VISUAL_Y/2))

    #draw wires onto background surface
    WIRE_COORDS = []
    for p in PANEL_COORDS:
        panel_rect.topleft = p
        WIRE_COORDS.append((panel_rect.center[0] + array_rect.topleft[0], panel_rect.center[1] + array_rect.topleft[1])) #places wire nodes at each panel center
    WIRE_COORDS.insert(0,(0,WIRE_COORDS[0][1]))#insert wire nodes at x=0 and same y as first & last panels in string
    WIRE_COORDS.append((0,WIRE_COORDS[-1][1]))
    pygame.draw.lines(bg_surf, WIRE_COLOR, False, WIRE_COORDS, WIRE_WIDTH)

    #draw connectors onto background surface
    #update connector coords to align with array surface
    CONNECTOR_COORDS = [(x+array_rect.topleft[0]+panel_rect.width/2, y+array_rect.topleft[1]+panel_rect.height/2) for x,y in CONNECTOR_COORDS]
    for x,y in CONNECTOR_COORDS:
        pygame.draw.circle(bg_surf, CONNECTOR_COLOR, (x,y), CONNECTOR_SIZE, width=CONNECTOR_WIDTH)
    #then append 0 and end points to the connector coords. We want these for positioning but we don't want to draw them.
    CONNECTOR_COORDS.insert(0,(0,CONNECTOR_COORDS[0][1]))#insert wire nodes at x=0 and same y as first & last panels in string
    CONNECTOR_COORDS.append((0,CONNECTOR_COORDS[-1][1]))
    
    
    term_surf = pygame.Surface((SCREEN_X, TERMINAL_Y - int(BORDER_PADDING/2) - BORDER_WIDTH))
    term_surf.fill(TERMINAL_COLOR)
    term_rect = term_surf.get_rect()
    term_rect.bottom = SCREEN_Y

    #define buttons
    button_outer_p = 5
    measure_b = ui.Button("Measure", STATUS_FONT, take_window_measurement)
    measure_b.move(SCREEN_X-measure_b.size_x-button_outer_p, button_outer_p)
    log_b = ui.Button("Toggle Logging",  STATUS_FONT, toggle_logging)
    log_b.move(SCREEN_X-log_b.size_x-button_outer_p, button_outer_p*2+measure_b.size_y)
    
    ######################################################
    ##              FAULT DETECTION SETUP               ##
    ######################################################

    detector = fault_detection.Detector(FAULT_DETECTION_METHOD)
    #detector = fault_detection.Detector(fault_detection.METHOD_NONE)
    fault = (fault_detection.FAULT_NONE, 0)
    terminal_waveform = None
    
    first_timestamp = None
    first_time_played = None
    input_row_index = 0
    if file_mode:
        input_data = fault_detection.read_csv_ungrouped(input_path)
    
    ######################################################
    ##                      LOOP                        ##
    ######################################################
    
    #set up threads:
    #first child thread: receives and interprets packets using receiver.run()
    with ThreadPoolExecutor(max_workers=3) as executor:
        if not file_mode:
            rec_thread = executor.submit(receiver.run)
        
        if state.device_class == DEVICE_PROTOTYPE:
            valid_waveform_prefix = b'\xaa\xaa\xaa\xad\x00\xbf' #valid waveform regions start with this pattern
            device_endpoint = 0x83
        else:
            valid_waveform_prefix = b'\x7F\xF2\x7F\xF3\x7F\xF1\xFE\xFE\x01\x01' #valid waveform regions start with this pattern (kingston devices)
            device_endpoint = 0x86
        
        payloadString = b'' #concatenated bytes from all unprocessed packets
        processStartIndex = 0 #the index at which the currently considered payload string starts (inclusive).
        processEndIndex = 0 #the index at which the currently considered payload string ends (exclusive).
        byteCount = 0
        MAX_BYTECOUNT = 512*4 #flush payloadString after reaching a buffer of this size 
        
        try:
            while(True):
                #take packet from Q, process in some way
                if file_mode:
                    if input_row_index in baseline_indices:
                        detector.set_baseline(input_data[input_row_index][3:])
                    if input_row_index in terminal_indices and FAULT_DETECTION_METHOD == fault_detection.METHOD_BLS_DEVIATION_CORRECTION:
                        detector.set_terminal(input_data[input_row_index][3:])
                    if input_row_index == 0:
                        first_time_played = time.time()
                        first_timestamp = input_data[0][2]
                    if True:#time.time() - first_time_played >= input_data[input_row_index+1][2] - first_timestamp:
                        input_row_index = input_row_index + 1
                    wf_deque.append(np.array(input_data[input_row_index][3:]))
                    time.sleep(0.25)
                """
                goal is to identify shape of data in intermittent test, and have this
                code recognize when a sequence of packet blocks represents a
                correlation waveform. This waveform should be calculated from payload
                bytes, and either shown for visualization (pyplot?) or fed to matlab
                for processing (which is the ultimate goal).
                """
                if not file_mode and receiver.q.empty() == False:
                    pBlock = receiver.q.get()
                    #commented out because this printing was very very slow, and ruined realtime
                    #if not(cscreen is None):
                        #cscreen.addstr(5,0,"Received packet at timestamp: " + str(pBlock.ts_sec + 0.000001*pBlock.ts_usec)) #show some packet data so it's clear the scanner is working
                        #cscreen.refresh()
                    
                    #if received packet may be in a waveform region of the stream:
                    #criteria: input (to host) from device endpoint and function == URB_FUNCTION_BULK_OR_INTERRUPT_TRANSFER
                    if (pBlock.packet.endpoint == device_endpoint and pBlock.packet.function == 0x09 and pBlock.packet.info == 1 and pBlock.packet.status == 0):
                        #if block has a payload:
                        p = pBlock.packet.payload
                        l = len(p)
                        if (state.device_class == DEVICE_PROTOTYPE or (state.device_class == DEVICE_COMMERCIAL and l == 512)): #all data seems to come in blocks of 512 for comm. devices
                            if byteCount + l > MAX_BYTECOUNT:
                                #if buffer overflowing, flush
                                payloadString = p
                                byteCount = l
                                processStartIndex = 0
                                processEndIndex = 0
                                if DEBUG_LOG and VERBOSE_LOGGING:
                                    debug_log(debug_log_path,"Buffer overfull, flushing buffer!")
                            else:
                                #else, append payload to buffer
                                payloadString = payloadString + p
                                byteCount = byteCount + l
                                #XXX
                                if DEBUG_LOG and VERBOSE_LOGGING:
                                    debug_log(debug_log_path, "Received payload")
                                if ((l==1 and p==valid_waveform_prefix[0]) or (l>1 and p[0] == valid_waveform_prefix[0]) or (valid_waveform_prefix[0] in p)):
                                    if DEBUG_LOG and DEBUG_VERIFICATION:
                                        debug_log(debug_log_path,"Received start of waveform prefix")
                                        debug_log(debug_log_path,"Starting payload: " + str(p))
                                        debug_log(debug_log_path,"New payload string: " + str(payloadString))
                        elif byteCount > 0:
                            #received packet from the device, but it's not valid; need to flush the buffer.
                            
                            if DEBUG_LOG and VERBOSE_LOGGING:
                                debug_log(debug_log_path, "Received invalid payload, discarding it and flushing buffer")
                            if USE_CURSES:
                                cscreen.addstr(7,0,"Flushed buffer at: "+str(pBlock.ts_sec + 0.000001*pBlock.ts_usec))
                                cscreen.refresh()
                            payloadString = b''
                            processStartIndex = 0
                            processEndIndex = 0
                            byteCount = 0
                        
                    else: #if we received an unwanted payload, ignore it.
                        pass
                        
                    #XXX
                    if DEBUG_LOG and VERBOSE_LOGGING and DEBUG_VERIFICATION:
                        debug_log(debug_log_path, "Payload string: "+str(payloadString))
                
                elif not file_mode and byteCount > 0:
                    #data is waiting in buffer, and we have time to process it
                    #check if we've started processing a waveform yet
                    if processEndIndex == 0: #if we haven't started processing a waveform yet
                        prefixStartIndex = payloadString.find(valid_waveform_prefix)
                        if prefixStartIndex != -1:
                            #waveform prefix found.
                            processStartIndex = prefixStartIndex
                            processEndIndex = processStartIndex + len(valid_waveform_prefix)
                    #if we've started a waveform, check if we can finish one
                    if processEndIndex > 0:
                        nextPrefixIndex = payloadString[processEndIndex:].find(valid_waveform_prefix)
                        if nextPrefixIndex != -1:
                            #we found the next waveform's prefix!
                            processEndIndex = nextPrefixIndex + processEndIndex
                            #prepare this waveform
                            if state.device_class == DEVICE_PROTOTYPE:
                                wf = process_waveform_region_prototype(payloadString[processStartIndex:processEndIndex],cscreen)
                            else:
                                wf = process_waveform_region(payloadString[processStartIndex:processEndIndex],cscreen)
                            #push this waveform into the deque.
                            wf_deque.append(wf)
                            if not(cscreen is None):
                                #show that we've received a waveform
                                cscreen.addstr(7,0,"Received waveform at timestamp: " + str(pBlock.ts_sec + 0.000001*pBlock.ts_usec))
                                cscreen.refresh()
                            #prepare to process the next waveform
                            payloadString = payloadString[processEndIndex:]
                            byteCount = len(payloadString)
                            processStartIndex = 0
                            processEndIndex = processStartIndex + len(valid_waveform_prefix)
                        else:
                            #no end to this waveform was found. sit on it.
                            pass
                
                if len(wf_deque) > 0: #either we're in file mode or the queue is empty; pop a waveform from the deque if any are ready (deque has max size, oldest entries are popped out when pushing if at max length)
                    time_log = False
                    if time_interval == -1 or dt.datetime.now() > state.next_log_time:
                        if time_interval != -1:
                            time_log = True
                            state.last_log_time = dt.datetime.now()
                            state.next_log_time = dt.datetime.now() + dt.timedelta(seconds=time_interval)
                        #q was empty, we have some extra time to visualize things
                        wf = np.array(wf_deque.popleft())
                        if (state.logging or time_log):
                            #write row with session index, log index, timestamp, and measured waveform.
                            with open(output_path, "a") as f:
                                #write header if needed
                                if not state.file_has_header:
                                    state.file_has_header = True
                                    f.write("session_number,log_number,timestamp,waveform\n")
                                f.write(str(state.session_number)+","+str(state.log_number)+","+str(pBlock.ts_sec + 0.000001*pBlock.ts_usec)+","+str(list(wf))[1:-1]+'\n') #1:-1 for brackets
                            if state.measurement_counter > 0:
                                state.measurement_counter -= 1
                                if state.measurement_counter == 0:
                                    state.logging = False    
                                    state.log_number += 1
                    
                    ###################################################################################################################################
                    #       PYFORMULAS: visualize waveform
                    ###################################################################################################################################
                    
                    #some code from https://stackoverflow.com/questions/40126176/fast-live-plotting-in-matplotlib-pyplot
                    plt.clf()
                    plt.xlabel("Distance (feet)")
                    plt.ylabel("Correlation With Reflection")
                    plt.gcf().subplots_adjust(left=0.15)
                
                    if detector.raw_baseline is None:
                        #plt.plot(fault_detection.FEET_VECTOR, wf_i/max(abs(wf_i)))
                        plt.plot(fault_detection.SPLINE_FEET_VECTOR-detector.spline_feet_offset, detector.last_processed_waveform)
                        #plt.ylim((-1,1))
                        plt.ylim((-(2**15), 2**15))
                        plt.xlim((fault_detection.SPLINE_FEET_VECTOR[0]-detector.spline_feet_offset, fault_detection.SPLINE_FEET_VECTOR[-1]-detector.spline_feet_offset))
                    else:
                        #plot BLS
                        ylim = ((-2**16,2**16))
                        bls = detector.last_processed_waveform - detector.processed_baseline
                        max_f = fault_detection.SPLINE_FEET_VECTOR[np.argmax(bls)]-detector.spline_feet_offset
                        plt.plot(fault_detection.SPLINE_FEET_VECTOR-detector.spline_feet_offset, bls)
                        plt.plot([max_f, max_f], ylim)
                        #plt.ylim((-1,1))
                        plt.ylim(ylim)
                        plt.xlim((fault_detection.SPLINE_FEET_VECTOR[0]-detector.spline_feet_offset, fault_detection.SPLINE_FEET_VECTOR[-1]-detector.spline_feet_offset))
                    
                    fig.canvas.draw()
                    image = np.frombuffer(fig.canvas.tostring_rgb(), dtype=np.uint8)
                    image = image.reshape(fig.canvas.get_width_height()[::-1] + (3,))
                    plot_window.update(image)
                    
                    ###################################################################################################################################
                    #       PYGAME: fault visualization & event queue
                    ###################################################################################################################################
                    fault = detector.detect_faults(wf)
                    
                    for event in pygame.event.get():
                        if event.type == pygame.QUIT or (event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE):
                            pygame.display.quit()
                            pygame.quit()
                        if event.type == pygame.MOUSEBUTTONUP:
                            for button in ui.Button.buttons:
                                if (button.rect.collidepoint(pygame.mouse.get_pos())):
                                    button.function(state)
                        if event.type == pygame.KEYDOWN:
                            if event.key == pygame.K_b:
                                detector.set_baseline(wf)#set baseline
                            elif event.key == pygame.K_l:
                                toggle_logging(state)
                            elif event.key == pygame.K_a:
                                terminal_waveform = wf #record waveform representing a disconnect at the panel terminal
                            elif event.key == pygame.K_t:
                                if (terminal_waveform is None): terminal_waveform = wf
                                detector.set_terminal(terminal_waveform)#set terminal points based on recorded terminal waveform and current BLSDT
                            elif event.key == pygame.K_LEFT:
                                detector.bls_deviation_thresh = detector.bls_deviation_thresh - 0.01 #adjust deviation threshold for peak location
                            elif event.key == pygame.K_RIGHT:
                                detector.bls_deviation_thresh = detector.bls_deviation_thresh + 0.01
                            elif event.key == pygame.K_w:
                                take_window_measurement(state)
                            elif event.key == pygame.K_i:
                                state.log_number += 1
                                
                    #per-frame logic here
                    is_fault = (fault[0] != fault_detection.FAULT_NONE)
                    fault_d_f = fault[1] #fault distance in feet, before correcting for panel electrical length
                    
                    if (is_fault):
                        d = 0
                        px = CONNECTOR_COORDS[0][0]
                        py = CONNECTOR_COORDS[0][1]
                        hazard_point = CONNECTOR_COORDS[-1]
                        
                        #determine the index of the first connector after the fault
                        for i in range(N):
                            if (connector_ds[i] > fault_d_f):
                                break
                        #i is now the index of the first connector junction AFTER the fault. if i=0, it means the fault is between the SSTDR and the first connector.
                        #if i is len(connector_ds), it means no connector is after the fault: it is between the final connector and the SSTDR.
                        
                        #get the distance from the SSTDR positive lead to the pre-fault connector. distance is in feet
                        if i == 0:
                            pre_d = 0
                        else:
                            pre_d = connector_ds[i-1]
                        #get the distance from the SSTDR positive lead to the post-fault node
                        if i == N:
                            post_d = connector_ds[-1] + panel_layout['home_cable_length'] #point in feet at final SSTDR terminal
                        else:
                            post_d = connector_ds[i]          
                        #get PIXEL locations of pre-fault and post-fault points, then calculate PIXEL location of fault point
                        pre_x, pre_y = CONNECTOR_COORDS[i] #CONNECTOR_COORDS has an extra point at i=0 (where x=0), so this chooses the point of the panel/terminal BEFORE the fault
                        post_x, post_y = CONNECTOR_COORDS[i+1] #certainly safe; CONNECTOR_COORDS has two more points than PANEL_COORDS. chooses the point AFTER the fault
                        hsr = (fault_d_f - pre_d)/(post_d - pre_d) #hazard step ratio: ratio at which the fault lies in between post point and pre point, s.t. fault_d = pre_d + hsr*(post_d - pre_d)
                        step = ((post_x-pre_x)**2 + (post_y-pre_y)**2)**0.5 #distance IN PIXELS between post and pre points
                        hazard_rect.center = (pre_x + hsr*(post_x-pre_x), pre_y + hsr*(post_y-pre_y))
                        
                        #subtract from distance to account for panel length; only want to report cable length
                        fault_cable_location = fault_d_f - panel_length*i
                        
                        fault_name = fault_detection.get_fault_name(fault[0])
                        fault_text_surf = TERMINAL_FONT.render(fault_name + " located at " + str(round(fault_cable_location,3)) + " feet", True, TEXT_COLOR)
                    else:
                        fault_text_surf = TERMINAL_FONT.render("System OK", True, TEXT_COLOR)
                    fault_text_rect = fault_text_surf.get_rect()
                    fault_text_rect.center = term_rect.center
                    
                    #param_text_surf = STATUS_FONT.render("BLS deviation threshold:" + str(detector.bls_deviation_thresh), True, COLOR_WHITE)
                    #param_text_surf = STATUS_FONT.render("LPF Cutoff Frequency: 6 MHz", True, COLOR_WHITE) #TODO don't hard code this, allow for live control of cutoff frequency
                    param_text_surf = STATUS_FONT.render("Current Log Number: "+str(state.log_number), True, COLOR_WHITE)
                    param_text_rect = param_text_surf.get_rect()
                    param_text_rect.bottomright = (SCREEN_X-3, VISUAL_Y - BORDER_WIDTH - int(0.5*BORDER_PADDING) - 3)
                    
                    logging_string = "Logging to '"+output_path+"'..." if state.logging else "Not logging."
                    logging_text_surf = STATUS_FONT.render(logging_string, True, COLOR_WHITE)
                    logging_text_rect = logging_text_surf.get_rect()
                    logging_text_rect.bottomright = param_text_rect.topright
                    
                    if time_interval != -1:
                        timer_string = "Next log time: "+state.next_log_time.strftime("%H:%M:%S")
                        timer_text_surf = STATUS_FONT.render(timer_string, True, COLOR_WHITE)
                        timer_text_rect = timer_text_surf.get_rect()
                        timer_text_rect.bottomright = logging_text_rect.topright
                    
                    #buttons: fill with color depending on context
                    mousepos = pygame.mouse.get_pos()
                    for button in ui.Button.buttons:
                        hovered = button.rect.collidepoint(mousepos)
                        button.set_highlight(hovered)
                    
                    #drawing
                    pscreen.blit(bg_surf, bg_rect)
                    pscreen.blit(term_surf, term_rect)
                    pscreen.blit(fault_text_surf, fault_text_rect)
                    pscreen.blit(param_text_surf, param_text_rect)
                    pscreen.blit(logging_text_surf, logging_text_rect)
                    if time_interval != -1:
                        pscreen.blit(timer_text_surf, timer_text_rect)
                    pscreen.blit(array_surf, array_rect)
                    for button in ui.Button.buttons:
                        pscreen.blit(button.surf, button.rect)
                    if (is_fault):
                        pscreen.blit(hazard_surf, hazard_rect)
                    pygame.display.flip()
                
                ###################################################################################################################################
                #       CURSES: Check for quit
                ###################################################################################################################################
                if not(cscreen is None):
                    c = cscreen.getch()
                    if (c == ord('q')):
                        cscreen.addstr(0,0,"Quitting: Terminating scanner...")
                        cscreen.refresh()                
                        usbpcap_process.terminate()                
                        cscreen.addstr(0,0, "Stopped scanner. Waiting for threads...")
                        cscreen.refresh()
                        receiver.halt()
                        #while(rec_thread.running()):
                        #    pass
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

def debug_log(debug_log_path, str):
    with open(debug_log_path,'a') as f:
        f.write("["+dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")+"] "+str+'\n')

def toggle_logging(state):
    #START/STOP LOGGING.
    if state.logging:
        #stop logging; increment log index.
        state.log_number = state.log_number+1
        state.measurement_counter = 0
        state.logging = False
    else:
        #start logging
        state.logging = True

def take_window_measurement(state):
    #log for 10 samples. "window capture"
    if state.logging:
        state.log_number += 1
    state.logging = True
    state.measurement_counter = 10 #counts down to zero

def process_waveform_region(pString,cscreen = None):
    #TODO alter this depending on the device class
    prefix_len = 20 #bytes
    if not cscreen is None and DEBUG_VERIFICATION:
        cscreen.addstr(8,4,"Waveform prefix: "+str(pString[0:prefix_len]))
        cscreen.refresh()
    elif DEBUG_VERIFICATION:
        print("Prefix: "+str(pString[0:prefix_len])+'\n')
    waveform_region = pString[prefix_len:]
    waveform = convert_waveform_region(waveform_region)
    #we can do anything with this waveform
    return waveform

def process_waveform_region_prototype(pString,cscreen = None):
    if not cscreen is None and DEBUG_VERIFICATION:
        cscreen.addstr(8,4,"Waveform prefix: "+str(pString[0:6]))
        cscreen.refresh()
    elif DEBUG_VERIFICATION:
        print("Prefix: "+str(pString[0:6])+'\n')
    waveform = convert_waveform_region_prototype(pString)[6:-1]
    #we can do anything with this waveform
    return waveform

def convert_waveform_region_prototype(pString):
    """takes a bytestring of arbitrary length, converts it into little-endian int16s. ignores trailing odd bytes"""
    N = len(pString)
    Nh = int(N/2)
    concat = [0]*Nh
    for i in range(Nh):
        vl = pString[2*i] #indexing with a scalar returns an integer
        vr = pString[2*i+1]
        #combine , little endian
        value = ((vr<<8)+vl)
        #convert to signed integer
        if (value & 0x8000 != 0):
            value = value - 2**16
        concat[i] = value
    return concat

def convert_waveform_region(pString):
    """takes a bytestring of arbitrary length, converts it into big-endian int16s. ignores trailing odd bytes"""
    N = len(pString)
    Nh = int(N/2)
    concat = [0]*Nh
    for i in range(Nh):
        vl = pString[2*i] #indexing with a scalar returns an integer
        vr = pString[2*i+1]
        #combine , big endian
        value = ((vl<<8)+vr)
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
        panel_series = data[0]
        N = panel_series['panel_count'] #TODO: only loads 0th series. for multi-series systems, this should be changed
        connector_ds = [0]*(N+1) #init empty array. connector_ds is distance in feet from the SSTDR to each MC-4 connector, accounting for module length, module cables & leading cables
        connector_ds[0] = panel_series['header_cable_length'] + panel_series['panel_cable_length']
        for i in range(1,N):
            connector_ds[i] = connector_ds[i-1] + 2*panel_series['panel_cable_length'] + panel_series['panel_electrical_length']
        #returns tuple:
        #   panel_series: layout dictionary directly loaded from .yaml
        #   connector_ds: list of connector distances from SSTDR, in feet
        #   panel length: electrical length of panels
        return (panel_series, connector_ds, panel_series['panel_electrical_length'])
        
    except:
        print("Exception Occurred:")
        print('='*40)
        traceback.print_exc(file=sys.stdout)
        print('='*40)
        return None

if (__name__ == '__main__'):
    if USE_CURSES:
        curses.wrapper(main)
    else:
        main()
