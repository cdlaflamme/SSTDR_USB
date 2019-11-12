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
METHOD_BASELINE_SUBTRACTION = 0
METHOD_DICTIONARY_LEARNING = 1

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
    def __init__(self, baseline = [], method = METHOD_BASELINE_SUBTRACTION):
        self.baseline = np.array(baseline)
        self.method = method
        #TODO need some characterization of cables... conversion of sample index to feet based on frequency and VOP
        self.VOP = 0.71
        self.units_per_sample = 3.63716 #from .lws file... doesn't seem extremely accurate
    
    def set_baseline(self, baseline):
        self.baseline = np.array(baseline)
    
    #returns a tuple: (fault type, distance to fault (in feet))
    def detect_faults(self, waveform):
        fault = (FAULT_NONE, 0)
        if self.method == METHOD_BASELINE_SUBTRACTION:
            #perform baseline subtraction and return a fault
            zero_index = np.argmax(self.baseline)
            wf = np.array(waveform)
            bls = wf-self.baseline
            abs_bls = np.abs(bls)
            for dev_index in range(len(self.baseline)):
                if (abs_bls[dev_index] >= 0.01*max(self.baseline)): break
            locs = scipy.signal.find_peaks(abs_bls)[0]
            locs = list(filter(lambda x: x >= dev_index, locs))
            fault_index = locs[1] #index 0 is a sidelobe
            if (bls[fault_index] > 0):
                fault_type = FAULT_OPEN
            else:
                fault_type = FAULT_SHORT
            
            fault = (fault_type, self.units_per_sample*(fault_index-zero_index))
        return fault
