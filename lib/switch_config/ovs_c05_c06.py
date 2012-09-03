'''
Created on Aug 26, 2012

@author: danny
'''

class OVS:
    
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

        self.source_ip = '10.65.6.1'
        self.dest_ip = '10.65.4.1'
        
        self.source_mac = '00:19:b9:f9:2c:26'
        self.dest_mac = '00:19:b9:f9:2c:59'
        
        # OpenFlow ports to which each machine is connected.
        self.source_of_port = '2'
        self.dest_of_port = '1'
        
        #===============================================================================
        # PKTGEN Settings
        #===============================================================================
        
        # Control IP
        self.pktgen_host = '172.22.14.206'
        
        # From where to send packets
        self.pktgen_iface = 'eth1'
        
        self.pktgen_proc = '/proc/net/pktgen/'
        
        # Must not be the real source IP, or else we will be flooded with ICMP messages.
        # Change the last number of the real source_ip to something else.
        self.source_ip_fake = '10.65.6.1'
        
        #===============================================================================
        # OpenFlow Settings
        #===============================================================================
        
        # Where can we run the OpenFlow control utilities (i.e. dpctl).
        self.ofctl_ip = '172.22.14.232' # This is the OVS box.
        
        # How can we connect to the switch
        self.sw_connection = 'br0'
        
        self.del_flow_cmd = 'ovs-ofctl del-flows ' + self.sw_connection + ' && echo del-flows OK'
        
        self.dump_flows_cmd = 'ovs-ofctl dump-flows ' + self.sw_connection
        
        self.add_rule_cmd = lambda rule: 'ovs-ofctl add-flow ' + self.sw_connection + ' \'' + rule + '\''
                                  
        # The port refers to the real UDP port, i.e. flow_id + 10,000.                                                        
        self.new_rule = lambda udp_port_num: 'cookie=0, priority=65536, idle_timeout=0,hard_timeout=0,udp,in_port=' + \
                        self.source_of_port + ',dl_vlan=0xffff,dl_vlan_pcp=0x00,dl_src=' + \
                        self.source_mac + ',dl_dst=' + self.dest_mac + ',nw_src=' + \
                        self.source_ip_fake + ',nw_dst=' + self.dest_ip + ',tp_src=' + \
                        self.str(udp_port_num) + ',tp_dst=9,actions=output:' + self.dest_of_port
        
        
        
        #===============================================================================
        # TCPDump Settings
        #===============================================================================
        
        self.sniff_iface = 'eth1'
        
        # Where to save the pcap output of tcpdump. We will need to parse this file
        # later.
        self.tmp_pcap_file = '/lib/init/rw/tcpdump.pcap'    
        
