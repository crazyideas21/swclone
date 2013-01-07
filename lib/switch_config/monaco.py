'''
Created on Jan 6, 2013

@author: danny
'''

class Monaco:
    
    def __init__(self):
        
        self.verbose = True
        
        #===============================================================================
        # Experiment Parameters
        #===============================================================================
        
        # Bytes of a single UDP packet.
        self.pkt_size = 1500
        
        # Number of concurrent flows. Packets are sent in a round-robin fashion. For
        # example, for flow_count=N, packets of the following ports are sequentially
        # sent: 1, ..., N-1, 0, 1, ..., N-1, ....
        self.flow_count = 800
        
        # What aggregate bandwidth in Mbps we should send. Note the actual sent
        # bandwidth may be different. The aggregate bandwidth is independent of the
        # number of flows.
        self.target_bw_Mbps = 1000
        
        # For how long (seconds) pktgen should be sending packets.
        self.max_time = 10
            
        #===============================================================================
        # Network Settings. Source refers to the host where pktgen runs, and
        # dest where tcpdump runs.
        #===============================================================================

        self.source_ip = '192.168.100.67'
        self.dest_ip = '192.168.100.68'
        
        self.source_mac = '00:0e:1e:0a:15:98' # ofport 1
        self.dest_mac = '00:0e:1e:0a:13:b0' # ofport 2
        
        # OpenFlow ports to which each machine is connected.
        self.source_of_port = '1'
        self.dest_of_port = '2'
        
        #===============================================================================
        # PKTGEN Settings
        #===============================================================================
        
        # Control IP
        self.pktgen_host = '172.22.16.67'
        
        # From where to send packets
        self.pktgen_iface = 'eth1'
        
        self.pktgen_proc = '/proc/net/pktgen/'
        
        # Must not be the real source IP, or else we will be flooded with ICMP messages.
        # Change the last number of the real source_ip to something else.
        self.source_ip_fake = '192.168.100.167'
        
        
        #===============================================================================
        # TCPDump Settings
        #===============================================================================
        
        self.sniff_iface = 'eth1'
        
        # Where to save the pcap output of tcpdump. We will need to parse this file
        # later.
        self.tmp_pcap_file = '/lib/init/rw/tcpdump.pcap'    
        
