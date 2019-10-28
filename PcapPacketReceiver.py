"""
PcapPacketReceiver.py
Cody LaFlamme
"""
import queue

"""
if this program is executed by itself, it expects a file path input.
the file at the given path will be read as a pcap file, the packets will be
parsed as USB packets, as the resulting packet block list will be saved as a
pickle file.
"""
def main():
    import sys
    import pickle
    
    if (len(sys.argv) < 2):
        print("Please supply input file path, and optionally an output file path.")
    
    out_path = "PPR_out.pickle"
    in_path = sys.argv[1]
    if (len(sys.argv) >= 3):
        out_path = sys.argv[2]
    
    with open(in_path, "rb") as in_file:
        receiver = PcapPacketReceiver(in_file)
        receiver.run()
    pBlocks = list(receiver.q.queue)
    
    with open(out_path, "wb") as out_file:
        pickle.dump(pBlocks, out_file)
    
    print("pickled packet data saved into '" + out_path + "'.")
    
##############################################################################

class PacketBlock:
    """Protocol agnostic packet block. Contains header info and raw data."""
    def __init__(self, pBytes = None, endianness = 'little'):
        self.ts_sec = 0
        self.ts_usec = 0
        self.incl_len = 0
        self.orig_len = 0
        self.data = b''
        self.packet = None #a reference to an object that may explain raw data        

        if (pBytes != None and len(pBytes) >= 4*4): #if we have a full header
            self.ts_sec     = int.from_bytes(pBytes[0:4], endianness)
            self.ts_usec    = int.from_bytes(pBytes[4:8], endianness)
            self.incl_len   = int.from_bytes(pBytes[8:12], endianness)
            self.orig_len   = int.from_bytes(pBytes[12:16], endianness)
            self.data = pBytes[16:]

class USBPacket:
    """USB specific packet data layout. Interprets the data of a PacketBlock."""
    def __init__(self, blockDataBytes=None, endianness = 'little'):
        #default values
        self.IRP = b''
        self.status = 0
        self.function = 0
        self.info = 0
        self.bus = 0
        self.address = 0
        self.endpoint = 0
        self.transfer_type = 0
        self.data_length = 0
        self.transfer_stage = -1 #only used for CONTROL_TRANSFER_EX; function == 9
        self.payload = b''
        
        if (blockDataBytes!=None):
            self.IRP = blockDataBytes[2:10]
            self.status     = int.from_bytes(blockDataBytes[10:14], endianness)
            self.function   = int.from_bytes(blockDataBytes[14:16], endianness)
            self.info       = int.from_bytes(blockDataBytes[16:17], endianness)
            self.bus        = int.from_bytes(blockDataBytes[17:19], endianness)
            self.address    = int.from_bytes(blockDataBytes[19:21], endianness)
            self.endpoint   = int.from_bytes(blockDataBytes[21:22], endianness)
            self.transfer_type = int.from_bytes(blockDataBytes[22:23], endianness)
            self.data_length = int.from_bytes(blockDataBytes[23:27], endianness)
            
            if (self.transfer_type == 2):
                self.transfer_stage = int.from_bytes(blockDataBytes[27:28], endianness)
                if (self.data_length > 0):
                    self.payload = blockDataBytes[28:28+self.data_length]
            else:
                self.transfer_stage = -1
                if (self.data_length > 0):
                    self.payload = blockDataBytes[27:27+self.data_length]

class PcapPacketReceiver:
    """    
    Receives packets from a pcap input stream, and places them into a Queue.
    
    The input stream is intended to provide the binary contents of a pcap file.
    This stream can be from a file, a live network, or stdin.
    "loop" should be true if reading from a stream with no known end, and false
    if reading from a file.
    "halt_event" is a threading.event that can be set from another thread to
    tell the receiver's run() function to stop running (used when loop is true)
    
    Packets are assembled into a Queue of Packet objects. This Queue can be
    read from at any time (python Qs are thread safe).
    
    Usage:
    Declare a PacketReceiver object, giving it an input stream.
    Call this object's run() function.
    
    If multithreading, packets will be put into the q as they are received, and
    one can safely call get() on the Q. If the Q is empy, these calls will
    block. Before ending the program, one should call the receiver's stop()
    function. When it returns, one can safely close the passed in_stream.
    
    If not multithreading, one should be using loop=False (as run() will never
    naturally terminate otherwise). The queue can then be read when run()
    returns, and the given in_stream can be closed.
    """
    def __init__(self, in_stream, loop=False, halt_event = None):
        self.in_stream = in_stream
        self.q = queue.Queue()
        self.loop = loop
        self.halt_event = halt_event
            
    def run(self):
        
        #read first few bytes to consume pcap header (6 4-byte values)
        #we don't use this information, and instead assume our data is little
        #endian, and that timestamps have usec resolution
        self.in_stream.read(6*4)

        pHeader = self.in_stream.read(4*4) #read first packet header: 4 4-byte values
        
        while(self.halt_event==None or not self.halt_event.is_set()):
            while(pHeader != b'' and (self.halt_event==None or not self.halt_event.is_set())):
                #loop until we've read every packet available
                pLen = int.from_bytes(pHeader[8:12], 'little')
                pData = self.in_stream.read(pLen)
                block = PacketBlock(pHeader + pData)
                block.packet = USBPacket(block.data)
                
                #q cannot currently become full. we'll run out of memory first.  
                self.q.put(block)
                #read header for next block.
                #if empty, we wait for more (if loop) or finish execution.
                pHeader = self.in_stream.read(4*4)
            if (self.loop == False):
                break #I miss do-whiles
        
    def halt(self):
        self.halt_event.set()

##############################################################################

def concat_payloads(payloads, little_endian=True, signed=True):
    endianness = 'little' if little_endian else 'big'
    
    vals = [int.from_bytes(v, endianness) for v in payloads if v != b'']
    N = int(len(vals)/2)
    concat = [0]*N
    for i in range(N):
        v1 = vals[2*i]
        v2 = vals[2*i+1]
        #combine according to endianness
        value = ((v2<<8)+v1) if little_endian else ((v1<<8)+v2)
        #convert to signed integer
        if (signed and value & 0x8000 != 0):
            value = value - 2**16
        concat[i] = value
    return concat


def concat_block_payloads(blocks, little_endian=True, signed=True):
    payloads = [blocks[i].packet.payload for i in range(len(blocks))]
    return concat_payloads(payloads, little_endian, signed)

##############################################################################

if __name__ == '__main__':
    main()
    
 
    
        