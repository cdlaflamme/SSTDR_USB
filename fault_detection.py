#fault_detection.py
#a collection of fault detection methods and constants for PV array fault detection
#in several cases, an enum would be more appropriate, but the python implementation of enums is headache-inducing

import scipy.signal
import numpy as np

#constants representing fault type. returned by "detect_faults()"
FAULT_NONE = 0
FAULT_OPEN = 1
FAULT_SHORT = 2
FAULT_GROUND = 3
FAULT_ARC = 4

#constants that determine the method to use for fault detection
METHOD_BLS_PEAKS = 0
METHOD_BLS_DEVIATION_CORRECTION = 1
METHOD_DICTIONARY_LEARNING = 2

def get_fault_name(fault_ID):
    if (fault_ID == FAULT_NONE):
        return "No fault"
    elif (fault_ID == FAULT_OPEN):
        return "Open fault"
    elif (fault_ID == FAULT_SHORT):
        return "Short fault"
    elif (fault_ID == FAULT_GROUND):
        return "Ground fault"
    elif (fault_ID == FAULT_ARC):
        return "Arc fault"
    else:
        return "Unnamed fault"

class Detector:
    def __init__(self, method = METHOD_BLS_PEAKS):
        self.baseline = None
        self.method = method
        #TODO need some characterization of cables... conversion of sample index to feet based on frequency and VOP
        self.VOP = 0.71 #from .lws file
        self.units_per_sample = 3.63716 #from .lws file... accuracy not verified
        self.bls_deviation_thresh = 0.10 #(B)ase(L)ine (S)ubtraction deviation threshold: percent variations smaller than this in the baseline-subtracted waveform will be ignored
        self.terminal_dev_index = 0
        self.terminal_peak_index = 0
        self.terminal_pulse_width = 0
        
    #takes as input a waveform from a healthy system
    def set_baseline(self, bl):
        self.baseline = np.array(bl)
    
    #takes as input a waveform with a disconnect just before any solar panels (the "panel terminal", commonly called A+)
    def set_terminal(self, wf):
        #locate first non-sidelobe peak in raw waveform, find P(A) and D(A) as in Mashad's method (BLS_DEVIATION_CORRECTION)
        print("setting terminal locations...")
        if (self.baseline is None): return
        zero_index = np.argmax(self.baseline)
        wf = np.array(wf)
        bls = wf-self.baseline
        abs_bls = np.abs(bls)
        print("finding deviation index...")
        for dev_index in range(len(self.baseline)):
            if (abs_bls[dev_index] >= self.bls_deviation_thresh*max(self.baseline)): break
        print("dev index: ", dev_index)
        if (dev_index >= len(wf)-1): return
        #need to locate peak in raw waveform
        locs = scipy.signal.find_peaks(wf)[0]
        locs = list(filter(lambda x: x >= dev_index, locs))
        print("found peaks", locs)
        #set internal values
        self.terminal_peak_index = locs[0] #index 0 is first peak; only positive peaks located and we're not in absolute value
        self.terminal_dev_index = dev_index
        self.terminal_pulse_width = self.terminal_peak_index - self.terminal_dev_index;
        print("set terminal locations.")
        
    #takes as input any waveform, returns the location and type of fault detected, if any
    #returns a tuple: (fault type, distance to fault (in feet))
    def detect_faults(self, waveform):
        fault = (FAULT_NONE, 0)
        #basic baseline subtraction; just look at peak locations
        if self.method == METHOD_BLS_PEAKS:
            #perform baseline subtraction and return a fault
            if (self.baseline is None): return fault
            zero_index = np.argmax(self.baseline)
            wf = np.array(waveform)
            bls = wf-self.baseline
            abs_bls = np.abs(bls)
            for dev_index in range(len(self.baseline)):
                if (abs_bls[dev_index] >= self.bls_deviation_thresh*max(self.baseline)): break
            if (dev_index == len(wf)-1): return fault
            locs = scipy.signal.find_peaks(abs_bls)[0]
            locs = list(filter(lambda x: x >= dev_index, locs))
            fault_index = locs[1] #index 0 is a sidelobe
            if (bls[fault_index] > 0):
                fault_type = FAULT_OPEN
            else:
                fault_type = FAULT_SHORT
            
            fault = (fault_type, self.units_per_sample*(fault_index-zero_index)) #TODO adjust for noninteger zero index using spline interpolation
        
        #Mashad's method: uses width of pulse from disconnect at panel terminal to correct other disconnect locations
        if self.method == METHOD_BLS_DEVIATION_CORRECTION:
            if (self.baseline is None): return fault
            zero_index = np.argmax(self.baseline)
            wf = np.array(waveform)
            bls = wf-self.baseline
            abs_bls = np.abs(bls)
            for dev_index in range(len(self.baseline)):
                if (abs_bls[dev_index] >= self.bls_deviation_thresh*max(self.baseline)): break
            if (dev_index == len(wf)-1): return fault
            #determine type of fault using sign of BLS peak; need to locate BLS peak
            locs = scipy.signal.find_peaks(abs_bls)[0]
            locs = list(filter(lambda x: x >= dev_index, locs))
            peak_index = locs[1] #index 0 is a sidelobe
            if (bls[peak_index] > 0):
                fault_type = FAULT_OPEN
            else:
                fault_type = FAULT_SHORT
            
            fault = (fault_type, self.units_per_sample*(dev_index + self.terminal_pulse_width -zero_index))
        
        return fault
