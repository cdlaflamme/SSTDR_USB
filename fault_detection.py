#fault_detection.py
#a collection of fault detection methods and constants for PV array fault detection
#in several cases, an enum would be more appropriate, but the python implementation of enums is headache-inducing

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
        self.baseline = baseline
        self.method = method
        #TODO need some characterization of cables... conversion of sample index to feet based on frequency and VOP
        
    #returns a tuple: (fault type, distance to faule (in feet))
    def detect_faults(self, waveform):
        fault = (FAULT_NONE, 5)
        if self.method == METHOD_BASELINE_SUBTRACTION:
            #TODO perform baseline subtraction and return a fault
            pass
        return fault
