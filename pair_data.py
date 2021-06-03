#pair_data.py

#pairs environmental data to sstdr measurments based on timestamp
#command line arguments, can be provided in any order:
#   -e [path] : provides path to environmental csv file (required)
#   -s [path] : provide path to sstdr csv file (required)
#   -o [path] : provide name of output file (OPTIONAL, defaults to "paired_data.csv")

#imports
import sys
import csv
import traceback
import numpy as np

#constants
USAGE_STRING = "Usage: python "+ sys.argv[0] +" -e [environment data csv path] -s [sstdr data csv path] -o [out path; optional]"
MAX_TIME_DIST = 1 #in seconds. maximum amount of time difference between an sstdr waveform and a set of environment measurements
SSTDR_WAVEFORM_LENGTH = 92

#functions
def pair_data(env_path, sstdr_path, out_path):
    try:
        #open files
        env_f = open(env_path,"r",encoding="latin-1")
        sstdr_f = open(sstdr_path,"r",encoding="latin-1")
        
        env_reader = csv.reader(env_f)
        sstdr_reader = csv.reader(sstdr_f)
        
        #setup: discarding boilerplate and reading headers
        env_f.readline() #discard first two useless rows
        env_f.readline()
        env_f.readline() #discard header row
        env_f.readline() #discard unit row (we know what units are which)
        
        #setup: write header line to out file
        with open(out_path,"w") as out_f:
            out_f.write("epoch time (seconds),illuminance (lux),(mw/cm2),temperature (degF),relative humidity(%),SSTDR correlation waveform\n")
        
            #begin
            prev_sstdr_time = 0 #in epoch time (seconds)
            prev_sstdr_row = ''
            for env_row in env_reader:
                best_sstdr_row = ''
                out_row = ''
                found_pair = False
                #assumes timestamps in env file are monotonically increasing. This is ok.
                #convert env timestamp to double
                env_time = convert_env_date_to_epoch(np.double(env_row[2]))
                #for each next sstdr row:
                header_row = True
                for sstdr_row in sstdr_reader:
                    if header_row:
                        continue
                    else:
                        header_row = False
                    #convert timestamp to double
                    sstdr_time = np.double(sstdr_row[2])
                    if (sstdr_time < env_time):
                        #if less than: store and keep going
                        prev_sstdr_time = sstdr_time
                        prev_sstdr_row = sstdr_row
                        continue
                    elif (sstdr_time >= env_time):
                        #if greater than: measure time distance from waveforms at lesser and greater times. use closest one.
                        current_diff = abs(env_time-sstdr_time)
                        prev_diff = abs(env_time-prev_sstdr_time)
                        if (prev_diff > MAX_TIME_DIST and current_diff > MAX_TIME_DIST):
                            #skip this environment row; we have no good sstdr waveform for it
                            #found_pair = False
                            break
                        else:
                            found_pair = True
                            if (prev_diff < current_diff):
                                best_sstdr_row = prev_sstdr_row
                            else:
                                best_sstdr_row = sstdr_row
                            break
                #assemble an output row with desired data
                if (found_pair):
                    out_row = best_sstdr_row[0] + ','
                    for i in [3,4,5,6]: #only want to keep these entries from the env row. omitted entries are redundant formatted time strings
                        out_row = out_row + env_row[i] + ','
                    for i,s in enumerate(best_sstdr_row[3:]):
                        out_row = out_row + s + ','
                    out_row = out_row[:-1] + '\n' #replace comma at EOL with newline
                    out_f.write(out_row)
        
        #done :)
        sstdr_f.close()
        env_f.close()
        print("Finished. Wrote paired data to: "+out_path)
        
    except:
        print(USAGE_STRING)
        print("Exception:")
        print('='*40)
        traceback.print_exc(file=sys.stdout)
        print('='*40)
        #return


def main():
    valid_input = True
    nargs = len(sys.argv)
    if nargs < 5 or nargs > 7 or nargs % 2 == 0 : #arg 0 is file name; want 4-6 more. need odd count: options need arguments, so their contribution is even, plus file name
        valid_input = False
    else:
        #environmental data csv path
        if '-e' in sys.argv:
            env_path = sys.argv[sys.argv.index('-e')+1]
        else:
            valid_input = False
        
        #sstdr csv path        
        if '-s' in sys.argv:
            sstdr_path = sys.argv[sys.argv.index('-s')+1]
        else:
            valid_input = False
        
        #output csv path        
        if '-o' in sys.argv:
            out_path = sys.argv[sys.argv.index('-o')+1]
        else:
            out_path = "paired_data.csv"
    
    if valid_input:
        pair_data(env_path, sstdr_path, out_path)
        
    else:
        print("Error: invalid input.")
        print(USAGE_STRING)

def convert_env_date_to_epoch(env_date):
    #converts the date format used by the TR-74U environmental sensor into epoch time.
    #accurate around january 2020: leap seconds may cause complications several years into the past/future
    #the sensor measures time as a serial number where 0 is midnight december 31, 1899
    #epoch time measures seconds from january 1, 1970: 0 is midnight jan 1, 1970.
    #to convert to epoch time, we subtract 70 years and one day...
    #70/4=17 of these years are multiples of 4. all but 1900 are leap years, so we also subtract 16 additional leap days.
    #then convert from days to seconds.
    #return (env_date - 1 - 356*70 - 16) * 24 * 60 * 60
    #for some reason, the above calculations are still a day ahead, so I've subtracted an extra day, though I'm not sure why.
    #maybe the sensor thinks 1900 was a leap year? or maybe since a leap day hasn't happened yet in 2020, something's off... I think these would both make the math a day behind, though.
    
    #FINALLY, the sensor has no concept of time zone. its time is set to the local time (Florida in january), but is actually supposed to be in GMT...
    #I think that's my fault, and I think it can be fixed later, but I don't want to corrupt temporally adjacent data at the moment, so I'm applying a quick hack and adding 5 hours to this time.
    
    return (env_date - 25569)*86400+5*3600

if __name__ == '__main__':
    main()
















