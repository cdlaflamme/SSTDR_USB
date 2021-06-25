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
import time

#python libraries
import numpy as np
import curses
import matplotlib.pyplot as plt
import pyformulas as pf
from collections import deque
import pygame
import yaml
import usb

#homegrown code
from PcapPacketReceiver import *
import fault_detection

######################################################
##                   CONSTANTS                      ##
######################################################
USE_CURSES = True
VERIFY_WAVEFORMS = True
DEBUG_VERIFICATION = False

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

BG_COLOR = COLOR_GREY
TERMINAL_COLOR = COLOR_WHITE
WIRE_COLOR = COLOR_BLUE
TEXT_COLOR = COLOR_BLACK

PANEL_SCALE = 1/15
PANEL_PADDING = (50, 50)
WIRE_WIDTH = 2
PANEL_SCREEN_X_RATIO = 1/2+1/8

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
    
    #read cmd line arguments
    valid_args = ['-yaml', 'y', '-filter', '-f', '-address', '-a', '-file', '-out', '-o', '-curses', '-c', '-no-curses', '-nc']
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
        elif arg in ['-out', '-o']:
            output_path = value
        #elif arg in ['-curses', '-c']:
        #    USE_CURSES = True
        #    skip = False
        #elif arg in ['-no-curses', '-nc']:
        #    USE_CURSES = False
        #    skip = False
        
    #prepare usb sniffing
    if (arg_filter is None or arg_address is None):
        sstdr_device = usb.core.find(idVendor=0x067b, idProduct=0x2303) #constants for our SSTDR device
        if sstdr_device == None:
            print("Error: Could not automatically find SSTDR device. Either restart it or provide filter/address manually.")
            return
        arg_filter  = sstdr_device.bus
        arg_address = sstdr_device.address
    
    usb_path = "C:\\Program Files\\USBPcap\\USBPcapCMD.exe"
    usb_args = [usb_path, "-d", "\\\\.\\USBPcap" + str(arg_filter), "--devices", str(arg_address), "-o", "-"]
    
    #prepare output file for logging
    with open(output_path, "a+") as out_f:
        out_f.seek(0,0)
        first_char = out_f.read(1)
        if (first_char == ''):
            #file did not exist or is empty. write header row; set session/log index to 0
            #write header row
            out_f.write("session_number,log_number,timestamp,waveform\n")
            session_number = 0
            log_number = 0
        else:
            #file was not empty. jump almost to end, read last line, extract session index
            #"read up until start of last line" code from S.O. user Trasp: https://stackoverflow.com/questions/3346430/what-is-the-most-efficient-way-to-get-first-and-last-line-of-a-text-file/3346788
            with open(output_path, "rb") as f:
                f.seek(-2, os.SEEK_END)     # Jump to the second last byte.
                while f.read(1) != b"\n":   # Until EOL is found...
                    f.seek(-2, os.SEEK_CUR) # ...jump back the read byte plus one more.
                last = f.readline()         # Read last line as bytes.
            session_number = 1+int(chr(int.from_bytes(last.split(b',')[0],'little'))) #assumes little endian, and that session index is present in column 0 (as will be standard in the future)
            log_number = 0

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
    panel_layout, panel_ds, panel_length = load_panel_layout(yaml_path)
    panel_cols = panel_rows = 0
    try:
        N = len(panel_ds)
        H = int(N/2)-1
        if (panel_layout['layout'] == 'loop'):
            panel_rows = 2
            panel_cols = int(N/2+0.5)
            r = 0
            PANEL_COORDS = [(c*(PANEL_PADDING[0] + panel_rect.w), r*(PANEL_PADDING[1] + panel_rect.h)) for c in range(0,H+1)]
            if (len(panel_ds)%2):
                r = 0.5
                PANEL_COORDS.append(((H+1)*(PANEL_PADDING[0] + panel_rect.w), r*(PANEL_PADDING[1] + panel_rect.h)))
            r = 1
            PANEL_COORDS = PANEL_COORDS + [(c*(PANEL_PADDING[0] + panel_rect.w), r*(PANEL_PADDING[1] + panel_rect.h)) for c in range(H,-1,-1)]
        
        elif(panel_layout['layout'] == 'home-run'):
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
    array_rect.center = (int(SCREEN_X*PANEL_SCREEN_X_RATIO), int(VISUAL_Y/2))

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
    
    button_text_p = 5 #padding
    button_outer_p = 5
    button_size = list(STATUS_FONT.size("Measure"))
    button_size[0] += 2*button_text_p
    button_size[1] += 2*button_text_p
    button_rect = pygame.Rect(SCREEN_X-button_size[0]-button_outer_p, button_outer_p, button_size[0], button_size[1])
    button_surf = pygame.Surface(button_size)
    button_text_surf = STATUS_FONT.render("Measure", True, COLOR_WHITE)
    
    ######################################################
    ##              FAULT DETECTION SETUP               ##
    ######################################################

    detector = fault_detection.Detector(fault_detection.METHOD_NONE)
    fault = (fault_detection.FAULT_NONE, 0)
    terminal_waveform = None
    logging = False #if this is true, measured waveforms will be written to a file
    measurement_counter = 0
    
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
        
        valid_waveform_prefix = b'\xaa\xaa\xaa\xad\x00\xbf' #valid waveform regions start with this pattern
        valid_waveform_suffix = 253 #valid waveform regions end with this pattern
        
        payloadString = b''
        byteCount = 0
        WAVEFORM_BYTE_COUNT = 199 #every waveform region contains 199 payload bytes
        
        try:
            while(True):
                #take packet from Q, process in some way
                if file_mode:
                    #TODO change this to whatever the baseline index ought to be
                    if input_row_index == 12:
                        detector.set_baseline(input_data[input_row_index][3:])
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
                    #criteria: input (to host) from endpoint 3 and function == URB_FUNCTION_BULK_OR_INTERRUPT_TRANSFER
                    if (pBlock.packet.endpoint == 0x83 and pBlock.packet.function == 0x09):
                        #if block has a payload:
                        p = pBlock.packet.payload
                        l = len(p)
                        if (l > 0):
                            payloadString = payloadString + p
                            byteCount = byteCount + l
                            if ((l==1 and p==0xaa) or (l>1 and p[0] == 0xaa) or (b'\xaa' in p)):
                                if not cscreen is None and DEBUG_VERIFICATION:
                                    cscreen.addstr(13,0,"Received start of prefix at timestamp: " + str(pBlock.ts_sec + 0.000001*pBlock.ts_usec))
                                    cscreen.addstr(14,4,"Starting payload: " + str(p))
                                    cscreen.addstr(15,4,"New payload string: " + str(payloadString))
                                    cscreen.refresh()
 
                            #for the first few bytes, compare it to a prefix pattern that all valid waveforms start with.
                            if (VERIFY_WAVEFORMS and byteCount <= len(valid_waveform_prefix)):
                                #TODO: currently assumes prefix bytes arrive one at a time (ie not in the same payload). this is OK the vast majority of the time.
                                if (p[0] != valid_waveform_prefix[byteCount-1]):
                                    #the current waveform is not valid. throw it out.
                                    if not(cscreen is None):
                                        cscreen.addstr(10,0,"Invalid waveform at timestamp: " + str(pBlock.ts_sec + 0.000001*pBlock.ts_usec))
                                        cscreen.addstr(11,4,"Prefix string: " + str(payloadString) + "; Byte count: " + str(byteCount))
                                        if (byteCount > 1):
                                            cscreen.addstr(12,4,"Last long invalid prefix: "+ str(payloadString) + "; Byte count: " + str(byteCount))
                                        cscreen.refresh()
                                    else:
                                        print("Invalid waveform at timestamp: " + str(pBlock.ts_sec + 0.000001*pBlock.ts_usec))
                                        print("Prefix string: " + str(payloadString)+'\n')
                                    if ((l==1 and p==0xaa) or (l>1 and p[0] == 0xaa) or (b'\xaa' in p)): #if the byte that ruined everything may be the start of a valid region, keep it
                                        payloadString = b'' + p
                                        byteCount = l
                                    else:
                                        payloadString = b''
                                        byteCount = 0
                            elif (byteCount >= WAVEFORM_BYTE_COUNT):
                                #perform processing on raw waveform
                                wf = process_waveform_region(payloadString,cscreen)
                                wf_deque.append(wf)
                                if not(cscreen is None):
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
                    if (logging):
                        #write row with session index, log index, timestamp, and measured waveform.
                        with open("SSTDR_waveforms.csv", "a") as f:
                            f.write(str(session_number)+","+str(log_number)+","+str(pBlock.ts_sec + 0.000001*pBlock.ts_usec)+","+str(list(wf))[1:-1]+'\n')
                        if measurement_counter > 0:
                            measurement_counter -= 1
                            if measurement_counter == 0:
                                logging = False                    
                                log_number += 1
                    
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
                        bls = detector.last_processed_waveform - detector.processed_baseline
                        max_f = fault_detection.SPLINE_FEET_VECTOR[np.argmax(bls)]-detector.spline_feet_offset
                        plt.plot(fault_detection.SPLINE_FEET_VECTOR-detector.spline_feet_offset, bls)
                        plt.plot([max_f, max_f], [-750, 750])
                        #plt.ylim((-1,1))
                        plt.ylim((-(750), 750))
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
                            if (button_rect.collidepoint(pygame.mouse.get_pos())):
                                #log for 10 samples. "window capture"
                                logging = True
                                measurement_counter = 10 #counts down to zero
                        if event.type == pygame.KEYDOWN:
                            if event.key == pygame.K_b:
                                detector.set_baseline(wf)#set baseline
                            elif event.key == pygame.K_l:
                                #START/STOP LOGGING.
                                if logging:
                                    #stop logging; increment log index.
                                    log_number = log_number+1
                                    measurement_counter = 0
                                    logging = False
                                else:
                                    #start logging
                                    logging = True
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
                                #log for 10 samples. "window capture"
                                logging = True
                                measurement_counter = 10 #counts down to zero
                                
                    #per-frame logic here
                    is_fault = (fault[0] != fault_detection.FAULT_NONE)
                    fault_d_f = fault[1]
                    
                    if (is_fault):
                        d = 0
                        px = WIRE_COORDS[0][0]
                        py = WIRE_COORDS[0][1]
                        hazard_point = WIRE_COORDS[-1]
                        
                        #determine which panel the fault is AFTER
                        for i in range(len(panel_ds)):
                            if (panel_ds[i] > fault_d_f):
                                break                        
                        #get the distance from the SSTDR positive lead to the pre-fault point ('point' being a point in WIRE_COORDS)
                        if i == 0:
                            pre_d = 0
                        else:
                            pre_d = panel_ds[i-1]
                        #get the distance from the SSTDR positive lead to the post-fault point
                        if i == len(panel_ds):
                            post_d = panel_ds[-1] + panel_layout['home_cable_length'] #point in feet at final SSTDR terminal
                        else:
                            post_d = panel_ds[i]          
                        #get PIXEL locations of pre-fault and post-fault points, then calculate PIXEL location of fault point
                        pre_x, pre_y = WIRE_COORDS[i] #WIRE COORDS has an extra point at i=0 (where x=0), so this chooses the point of the panel/terminal BEFORE the fault
                        post_x, post_y = WIRE_COORDS[i+1] #certainly safe; WIRE_COORDS has two more points than PANEL_COORDS. chooses the point AFTER the fault
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
                    param_text_surf = STATUS_FONT.render("Current Log Number: "+str(log_number), True, COLOR_WHITE)
                    param_text_rect = param_text_surf.get_rect()
                    param_text_rect.bottomright = (SCREEN_X-3, VISUAL_Y - BORDER_WIDTH - int(0.5*BORDER_PADDING) - 3)
                    
                    logging_string = "Logging to 'SSTDR_waveforms.csv'..." if logging else "Not logging."
                    logging_text_surf = STATUS_FONT.render(logging_string, True, COLOR_WHITE)
                    logging_text_rect = logging_text_surf.get_rect()
                    logging_text_rect.bottomright = param_text_rect.topright
                    
                    #buttons: fill with color depending on context
                    #for now just fill orange
                    if (button_rect.collidepoint(pygame.mouse.get_pos())):
                        button_surf.fill(COLOR_ORANGE)
                    else:
                        button_surf.fill(COLOR_BLUE)
                    button_surf.blit(button_text_surf,(button_text_p,button_text_p))
                    
                    #drawing
                    pscreen.blit(bg_surf, bg_rect)
                    pscreen.blit(term_surf, term_rect)
                    pscreen.blit(fault_text_surf, fault_text_rect)
                    pscreen.blit(param_text_surf, param_text_rect)
                    pscreen.blit(logging_text_surf, logging_text_rect)
                    pscreen.blit(array_surf, array_rect)
                    pscreen.blit(button_surf, button_rect)
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

def process_waveform_region(pString,cscreen = None):
    if not cscreen is None and DEBUG_VERIFICATION:
        cscreen.addstr(8,4,"Waveform prefix: "+str(pString[0:6]))
        cscreen.refresh()
    elif DEBUG_VERIFICATION:
        print("Prefix: "+str(pString[0:6])+'\n')
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
        panel_series = data[0]
        N = panel_series['panel_count'] #TODO: only loads 0th series. for multi-series systems, this should be changed
        panel_ds = [0]*N #init empty array
        panel_ds[0] = panel_series['header_cable_length'] + panel_series['panel_cable_length'] + 1/2*panel_series['panel_electrical_length']
        for i in range(1,N):
            panel_ds[i] = panel_ds[i-1] + 2*panel_series['panel_cable_length'] + panel_series['panel_electrical_length'] #elec length not halved; there's two contributing panels
        #returns tuple:
        #   panel_series: layout dictionary directly loaded from .yaml
        #   panel_ds: list of panel distances from SSTDR, in feet
        return (panel_series, panel_ds, panel_series['panel_electrical_length'])
        
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
