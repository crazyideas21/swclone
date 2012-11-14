"""
Wrapper for tcpdump. 

"""
import re, time, subprocess
import util, pktgen


class TcpdumpResult:
    
    def __init__(self):
        self.recvd_pkt_count = 0
        self.dropped_pkt_count = 0
        
        


class Tcpdump:
    
    def __init__(self, config_obj):
        
        if config_obj:
            self.config = config_obj
        else:
            self.config = None
            assert False
    
    
    
    def start(self):        
        """ 
        Sniff traffic. Save the text output to check for kernel-dropped packets. 
        
        """    
        util.run_cmd('tcpdump -i ', self.config.sniff_iface,
                     ' -vnnxStt -s 96 -w ', self.config.tmp_pcap_file, 
                     ' udp > /tmp/tcpdump.log 2>&1')
        time.sleep(2)
    
    
    
    def stop_and_get_result(self):
        """ Returns the result as a TcpdumpResult object. """
        
        util.run_cmd('pkill tcpdump').wait()
        
        # Parse the number of packets dropped by the kernel.
                
        logf = open('/tmp/tcpdump.log')
        result = TcpdumpResult()
            
        for line in logf:
                    
            r = re.search('(\d+) packets received by filter', line)
            if r: 
                result.recvd_pkt_count = int(r.group(1))
                
            r = re.search('(\d+) packets dropped by kernel', line)
            if r: 
                result.dropped_pkt_count = int(r.group(1))
        
        logf.close()
    
        # Displays the result of tcpdump    

        if self.config.verbose:
            print 'TCPDUMP - received packets:',
            print result.recvd_pkt_count
            print 'dropped packets:',
            print result.dropped_pkt_count
            
        return result
    
    
    
    def parse_pkt(self, pkt_func):
        """
        Loops to parse output from tcpdump. An example would be:
    
        [recvd_time     ]                 [   ] <- (flow_id + pktgen.MIN_PORT)
        1329098408.055825 IP 192.168.1.20.10007 > 192.168.1.1.9: UDP, length 22
              0x0000:    4500 0032 066e 0000 2011 10e8 c0a8 0114 <- ignore
              0x0010:    c0a8 0101 2717 0009 001e 0000 be9b e955 <- ignore
              0x0020:    0000 066f 4f38 6ea6 000e 4402 0000 0000 
                         [seq_num] [tvsec  ] [tvusec ]
                        ... the rest of the lines can be ignored
    
        Each time a new packet arrives, invokes the pkt_func callback function.
        The pkt_func should have arguments (flow_id, seq_number, sent_time,
        recvd_time). This allows users to handle incoming packets, based on
        these four parameters, accordingly.
    
        """    
        # Initialize fields to extract.
        recvd_time = flow_id = seq_num = tvsec = tvusec = None
    
        # Regex applied on udp header to extract recvd_time and flow_id.
        regex_udp = re.compile('(\d+\.\d+) IP .*\.(\d+) >')
    
        # Regex applied on the pktgen payload.
        regex_pktgen = re.compile('0x0020:\s+(.{10})(.{10})(.{10})')
    
        # Parse with tcpdump -r
        p_tcpdump = util.run_cmd('tcpdump -nnxStt -r ', 
                                  self.config.tmp_pcap_file,
                                  stdout=subprocess.PIPE)
    
        for line in p_tcpdump.stdout:
    
            re_udp = regex_udp.search(line)
            if re_udp:
                recvd_time = float(re_udp.group(1))
                flow_id = int(re_udp.group(2)) - pktgen.Pktgen.MIN_PORT
                continue
    
            re_pktgen = regex_pktgen.search(line)
            if re_pktgen:
    
                # Here, the seq_num is a global value. We need to convert it to
                # a per-flow sequence number.
                seq_num = util.hex_to_int(re_pktgen.group(1))
                seq_num = seq_num / self.config.flow_count
    
                # Convert the recvd timestamp to float.
                tvsec = util.hex_to_int(re_pktgen.group(2))
                tvusec = util.hex_to_int(re_pktgen.group(3))
                sent_time = tvsec + tvusec / 1000000.0
    
                # We should have obtained all necessary fields to form a packet.
                assert None not in (recvd_time, flow_id)
                pkt_func(flow_id, seq_num, sent_time, recvd_time)
    
                # Reset all fields.
                recvd_time = flow_id = seq_num = tvsec = tvusec = None
                    
    
    
    

    

