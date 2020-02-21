#read_waveforms.py

#reads waveforms from NREL tests. returns grouped waveform lists.

import fault_detection as fd
import matplotlib.pyplot as plt
import numpy as np

cable_length = 74.583 #in feet
panel_count = 26
fft_size = 1024
CUTOFF = fft_size//4//4 #sample rate 24Mhz*4, center freq is 12MHz

#FEET_PER_SAMPLE = 3.6679 #194' cable in warm old florida
FEET_PER_SAMPLE = 3.8479 #calculated manually from second NREL test
FEET_PER_SPLINE_SAMPLE = FEET_PER_SAMPLE*92/1000

#read waveforms from one of the files. group waveforms based on log number.
#wfs_all = fd.read_wfs("NREL_sequence_LG_1.csv")
wfs_all = fd.read_wfs("NREL_sequence_canadian_2.csv")
bl_index = 4

N = len(wfs_all)
wfs_0 = np.zeros((N,92))
for group in wfs_all:
    wfs_0[group] = wfs_all[group][0]

#calibrate distances based on cable length
#zero_index = np.argmax(wfs_0[0]) #commented out b/c in second NREL test the cable end reflection is actually higher amplitude than first reflection
zero_index = 9
feet_vector = (np.arange(0,92)-zero_index)*FEET_PER_SAMPLE
spline_feet_vector = (np.arange(0,1000)-zero_index/92*1000)*FEET_PER_SPLINE_SAMPLE

wfs_process = wfs_0


#low pass filter
filter = np.zeros(fft_size//2+1,dtype=np.cdouble)
filter[0:CUTOFF] = 1   #looks like: ----____________
#filter = filter + np.flip(filter) #force symmetry: ----________---- #this is now done by using rfft

wfs_rfft = np.zeros((N,fft_size//2+1),dtype=np.cdouble)
wfs_filtered = np.zeros_like(wfs_process)
for i,wf in enumerate(wfs_process):
    wfs_rfft[i] = np.fft.rfft(wf, fft_size)
    #wfs_fft[i] = wfs_fft[i] + np.conj(np.flip(wfs_fft[i])) #force conjugate symmetry for real reconstructed signal.... this shouldn't be necessary; our fully calculated fft should be conjugate symmetric anyways.
    wfs_filtered[i] = np.fft.irfft(filter*wfs_rfft[i], fft_size)[0:len(wf)]
wfs_process = wfs_filtered

#spline interpolation
wfs_i = np.zeros((N, 1000))
for i,wf in enumerate(wfs_process):
    wfs_i[i] = fd.spline_interpolate(wf)
wfs_process = wfs_i


#did just cables, negative lead, positive lead, full string, then disconnect sequence around the loop.
bl = np.array(wfs_process[bl_index])
bls = np.zeros((N, 1000))

#plot baseline subtractions
for r,row in enumerate(wfs_process):
    if r > 1 and r <= 13:#panel_count/2+3:
        bls[r] = np.array(row - bl)
        plt.plot(spline_feet_vector, bls[r], label=str(r))
#plt.plot([cable_length, cable_length],[-15000,15000],label='cable_end')
plt.plot([cable_length, cable_length],[-1000,1000],label='cable_end')
plt.legend()
plt.show()

def plot_bls():
    #plot baseline subtractions
    for r,row in enumerate(wfs_process):
        if r > 1 and r <= 13:#panel_count/2+3:
            bls[r] = np.array(row - bl)
            plt.plot(spline_feet_vector, bls[r], label=str(r))
    plt.plot([cable_length, cable_length],[-1000,1000],label='cable_end')
    plt.legend()
    plt.show()


def plot_groups():
    for group in wfs_all:
        for wf in wfs_all[group]:
            plt.plot(wf)
        plt.show()
    
