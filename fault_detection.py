#fault_detection.py
#a collection of fault detection methods and constants for PV array fault detection
#in several cases, an enum would be more appropriate, but the python implementation of enums is headache-inducing

import scipy.signal
import scipy.interpolate
import numpy as np
import csv

SPLINE_LENGTH = 1000 #signals will be interpolated to this length
#FEET_PER_SAMPLE = 3.63716 #from .lws file... accuracy not verified. (florida cable)
FEET_PER_SAMPLE = 3.8479 #calculated manually from second NREL test
SPLINE_FEET_PER_SAMPLE = FEET_PER_SAMPLE*92/SPLINE_LENGTH
SPLINE_FEET_VECTOR = np.arange(0,SPLINE_LENGTH)*SPLINE_FEET_PER_SAMPLE
FFT_SIZE = 1024
LPF_CUTOFF_INDEX = FFT_SIZE//4//4 #fs = 24Mhz*4; cutoff frequency is equal to fs divided by the same factor that fft size is divided by
LOW_PASS_FILTER = [1+0j if i < LPF_CUTOFF_INDEX else 0+0j for i in range(FFT_SIZE//2+1)] #ideal LPF to be applied in the frequency domain
Z_INDEX_THRESHOLD = 10000
#FAULT_THRESHOLD = 50

#constants representing fault type. returned by "detect_faults()"
FAULT_NONE = 0
FAULT_OPEN = 1
FAULT_SHORT = 2
FAULT_GROUND = 3
FAULT_ARC = 4

#fake enum of methods for fault detection
METHOD_NONE = -1
METHOD_BLS_PEAKS = 0
METHOD_BLS_DEVIATION_CORRECTION = 1
METHOD_DICTIONARY_LEARNING = 2
METHOD_LOW_PASS_PEAKS = 3

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

def spline_interpolate(y, N = SPLINE_LENGTH):
    x = range(len(y))
    tck = scipy.interpolate.splrep(x, y)
    x_i = np.linspace(min(x), max(x), N)
    spl = scipy.interpolate.splev(x_i, tck)
    return spl

def read_csv(file_path):
    rows = {}
    with open(file_path, "r") as f:
        reader = csv.reader(f)
        for row_raw in reader:
            if (reader.line_num == 1): continue
            i = int(row_raw[1])
            row = np.array(row_raw, dtype='int')
            if not (i in rows.keys()):
                rows[i] = []
            rows[i].append(row)
    return rows

def read_csv_ungrouped(file_path):
    rows = []
    with open(file_path, "r") as f:
        reader = csv.reader(f)
        for row_raw in reader:
            if (reader.line_num == 1): continue
            row = np.array(row_raw, dtype='int')
            rows.append(row)
    return rows

def read_wfs(file_path):
    wfs = {}
    with open(file_path, "r") as f:
        reader = csv.reader(f)
        for row_raw in reader:
            if (reader.line_num == 1): continue
            i = int(row_raw[1])
            row = np.array(row_raw[3:], dtype='int')
            if not (i in wfs.keys()):
                wfs[i] = []
            wfs[i].append(row)
    return wfs

def remove_spikes(wf, bl):
    #there are annoying small-amplitude (~250) spikes in the data received via USB.
    #these small spikes are significant enough to mess up Mashad's method, as they are
    #generally >1% the max value in a waveform (~20000).
    #these spikes are not present in values saved by livewire software, so I'm assuming
    #livewire software removes them as well, and that I'm not introducing (net) errors in the data.
    spike_thresh = 200
    N = len(wf)
    bls = np.array(wf)-np.array(bl) #baseline subtraction
    bls_padded = np.concatenate([[0, 0], bls, [0]]) #pad bls so we can reach negative indices
    y = wf.copy()
    #for every sample in waveform
    for i in range(1,N):
        j = i+2 #index padded bls with j so bl[i] == bl_padded[j]
        #determine if this sample is part of a 2-sample spike: two adjacent samples with huge deviation from the baseline in opposite directions
        b = bls_padded[j]
        a = bls_padded[j-1]
        z = bls_padded[j-2]
        if (abs(a) > spike_thresh and abs(b) > spike_thresh and a*b < 0):
            #set both samples in spike to be near their neighbors in the bls domain, using linear interpolation
            y[i-1] = bl[i-1] + 2/3*bls_padded[j-2] + 1/3*bls_padded[j+1]
            y[i]   = bl[i]   + 1/3*bls_padded[j-2] + 2/3*bls_padded[j+1]
        elif(i >= 2 and abs(z) > spike_thresh and abs(b) > spike_thresh and b*z < 0):
            y[i-2] = bl[i-2] + 1/3*bls_padded[j-3] + 1/3*bls_padded[j+1]
            y[i]   = bl[i]   + 1/3*bls_padded[j-3] + 2/3*bls_padded[j+1]
    return y

def low_pass_filter(wf):
    rfft = np.fft.rfft(wf, FFT_SIZE)
    wf_filtered = np.fft.irfft(rfft*LOW_PASS_FILTER, FFT_SIZE)[0:len(wf)] #thank you Fourier, I love you
    return wf_filtered

class Detector:
    def __init__(self, method = METHOD_BLS_PEAKS):
        #constants
        self.VOP = 0.71 #from .lws file, not Scurrently used
        self.units_per_sample = FEET_PER_SAMPLE*92/SPLINE_LENGTH #convert feet per sample for spline length
        self.bls_deviation_thresh = 0.10 #(B)ase(L)ine (S)ubtraction deviation threshold: percent variations smaller than this in the baseline-subtracted waveform will be ignored
        self.fault_threshold = 45
        #init of internal variables
        self.processed_baseline = None
        self.raw_baseline = None
        self.last_processed_waveform = np.zeros(SPLINE_LENGTH) #stores the last evaluated waveform, processed in whatever way required for fault detection (not used in this class, just used for plotting from outside)
        self.method = method
        self.terminal_dev_index = 0
        self.terminal_peak_index = 0
        self.terminal_pulse_width = 0
        self.zero_index = 0
        self.spline_zero_index = 0
        self.spline_feet_offset = 0
    
    #takes as input a waveform from a healthy system
    def set_baseline(self, bl):
        self.raw_baseline = np.array(bl)
        #self.zero_index = np.argmax(self.baseline) #commented out b/c in some cases the cable reflection is actually greater...
        locs = np.argwhere(bl > Z_INDEX_THRESHOLD)
        if len(locs > 0):
            self.zero_index = locs[0][0] #argwhere returns an array of arrays representing index sets; we want the first index "set" which is one index, so we take the first element of it
        else:
            self.zero_index = 0
        self.spline_zero_index = self.zero_index/92*SPLINE_LENGTH
        self.spline_feet_offset = self.spline_zero_index * SPLINE_FEET_PER_SAMPLE
        if (self.method == METHOD_LOW_PASS_PEAKS):
            #apply low-pass filter to baselnie before interpolating.
            self.processed_baseline = spline_interpolate(low_pass_filter(bl))
        else:
            #interpolate.
            self.processed_baseline = spline_interpolate(bl)
        
    #takes as input a waveform with a disconnect just before any solar panels (the "panel terminal", commonly called A+)
    def set_terminal(self, waveform):
        #locate first non-sidelobe peak in raw waveform, find P(A) and D(A) as in Mashad's method (BLS_DEVIATION_CORRECTION)
        print("setting terminal locations...")
        if (self.raw_baseline is None): return
        #wf = spline_interpolate(range(len(waveform)), waveform, self.spline_length)
        wf = np.array(waveform)
        bls = wf-self.processed_baseline
        abs_bls = np.abs(bls)
        print("finding deviation index...")
        for dev_index in range(len(self.processed_baseline)):
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
        return fault; #XXX hack to skip interpolation code
        if self.raw_baseline is None:
            self.last_processed_waveform = spline_interpolate(waveform)
            return fault
        
        #newest method: low pass filter, then peak location, with correction based on panel electrical length
        if self.method == METHOD_LOW_PASS_PEAKS:
            if (self.raw_baseline is None): return fault
            #filter the signal, perform baseline subtraction, and return located faults
            self.last_processed_waveform = spline_interpolate(low_pass_filter(waveform))
            bls = self.last_processed_waveform-self.processed_baseline
            fault_index = np.argmax(bls)
            if (bls[fault_index] >= self.fault_threshold):
                #fault detected. set fault info. DOES NOT CORRECT FOR PANEL LENGTH.
                fault = (FAULT_OPEN, self.units_per_sample*(fault_index-self.spline_zero_index))
            #else: pass
        
        #basic baseline subtraction; just look at peak locations
        if self.method == METHOD_BLS_PEAKS:
            #perform baseline subtraction and return a fault
            if (self.baseline is None): return fault
            #wf = spline_interpolate(range(len(waveform)), waveform, self.spline_length)
            wf = spline_interpolate(waveform)
            self.last_processed_waveform = np.array(waveform)
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
            
            fault = (fault_type, self.units_per_sample*(fault_index-self.zero_index))
        
        #Mashad's method: uses width of pulse from disconnect at panel terminal to correct other disconnect locations
        if self.method == METHOD_BLS_DEVIATION_CORRECTION:
            if (self.baseline is None): return fault
            #wf = spline_interpolate(range(len(waveform)), waveform, self.spline_length)
            wf = spline_interpolate(waveform)
            self.last_processed_waveform = wf
            bls = wf-self.baseline
            abs_bls = np.abs(bls)
            for dev_index in range(len(self.baseline)):
                if (abs_bls[dev_index] >= self.bls_deviation_thresh*max(self.baseline)): break
            if (dev_index >= len(wf)-1): return fault
            #determine type of fault using sign of BLS peak; need to locate BLS peak
            locs = scipy.signal.find_peaks(abs_bls)[0]
            locs = list(filter(lambda x: x >= dev_index, locs))
            peak_index = locs[1] #index 0 is a sidelobe
            if (bls[peak_index] > 0):
                fault_type = FAULT_OPEN
            else:
                fault_type = FAULT_SHORT
            fault = (fault_type, self.units_per_sample*(dev_index + self.terminal_pulse_width-self.zero_index))
        return fault
