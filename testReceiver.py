import PcapPacketReceiver as ppr
in_file = open("test_short.pcap", "rb")
r = ppr.PcapPacketReceiver(in_file)
r.run()


print("done")
