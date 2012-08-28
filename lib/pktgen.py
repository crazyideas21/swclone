"""
Wrapper functions for pktgen. Note: If one sets the flow count == packet count
== N, then pktgen first sends UDP packets of ports 1 through N-1, followed by
UDP port 0.

"""

import subprocess, time, re
import lib.config as config
import lib.util as util



class PktgenResult:
    
    def __init__(self):
        self.running_time = 0
        self.sent_pkt_count = 0




class Pktgen:


    MIN_PORT = 10000


    def __init__(self, config_obj):
        
        self.run_time = 0
        self.sent_pkt_count = 0
        
        # This hack forces Eclipse to give hints based on the properties of the
        # HPSwitch object.
        if config:
            self.config = config_obj
        else:
            self.config = config.HPSwitch() 



    def start(self):
        """ Start sending packets using parameters from config. """
        
        target_bw_bps = self.config.target_bw_Mbps * 1000 * 1000
        pkt_size_b = self.config.pkt_size * 8
        pkt_count = target_bw_bps * self.config.max_time / pkt_size_b
        gap_ns = pkt_size_b * (10**9) / target_bw_bps # nanoseconds

        return self._start_low_level(pkt_count, self.config.pkt_size, gap_ns, 
                                     self.config.flow_count)            



    def _start_low_level(self, pkt_count=56, pkt_size=1400, delay=0, flow_count=1):
        """
        Sends packets with low-level params. Returns a Popen handle. Avoid using
        this.
        
        """        
        f = open('./script/pktgen_wrapper_template.sh')
        pktgen_script = f.read()
        f.close()
        
        # Replace the place-holders in pktgen_wrapper.sh with actual parameters.
        
        replacement_dict = {'[PKTGEN_PROC]': self.config.pktgen_proc,
                            '[PKTGEN_IFACE]': self.config.pktgen_iface,
                            '[PKT_COUNT]': str(pkt_count),
                            '[PKT_SIZE]': str(pkt_size),
                            '[DELAY]': str(delay),
                            '[MIN_PORT]': str(Pktgen.MIN_PORT),
                            '[MAX_PORT]': str((flow_count + Pktgen.MIN_PORT)),
                            '[SRC_IP]': self.config.source_ip_fake,
                            '[DST_IP]': self.config.dest_ip,
                            '[DST_MAC]': self.config.dest_mac
                            }
        pktgen_script = self._replace_string_with_dict(pktgen_script, replacement_dict)
        
        f = open('/tmp/pktgen_wrapper.sh', 'w')
        f.write(pktgen_script)
        f.close()
    
        # Copy the file to pktgen host's tmp.
        
        p = util.run_cmd('scp -q /tmp/pktgen_wrapper.sh ',
                         'root@', self.config.pktgen_host, ':/tmp; ',
                         'rm /tmp/pktgen_wrapper.sh')
        p.wait()
    
        # Execute the script remotely.
        
        util.run_ssh('chmod +x /tmp/pktgen_wrapper.sh; ', 
                     '/tmp/pktgen_wrapper.sh', 
                     hostname=self.config.pktgen_host)
    



    def stop_and_get_result(self):
        """ 
        Terminates the pktgen process and parses the pktgen result. Returns the
        PktgenResult object.
        
        """
        util.run_ssh('pkill -2 pktgen_wrapper',
                     hostname=self.config.pktgen_host).wait()
        time.sleep(2)
        return self._parse_result()
            
        
    
    
    def _parse_result(self):
        """
        Parses the pktgen result file in /proc, extracts the actual run time (in
        second) and packet count and returns them as a PktgenResult object..
    
        We want to match the following line:
        Result: OK: 8648151(c650366+d7997785) nsec, 87129 (1400byte,0frags)
                    [     ] <-exp time in us        [   ] <- pkt sent
    
        """
        p_proc = util.run_ssh('cat ', self.config.pktgen_proc, 
                              self.config.pktgen_iface,
                              hostname=self.config.pktgen_host,
                              stdout=subprocess.PIPE)
    
        result_regex = re.compile('OK: (\d+)\(.*\) nsec, (\d+) \(.*\)')
    
        for line in p_proc.stdout:
    
            r_obj = result_regex.search(line)
            if r_obj:
                print 'Parsing pktgen result:', line
                result = PktgenResult()
                result.running_time = int(r_obj.group(1)) / 1000000.0
                result.sent_pkt_count = int(r_obj.group(2))
                return result
    
        raise Exception('Unable to parse pktgen result.')
    




    def _replace_string_with_dict(self, in_str, in_dict):
        """
        Helper for send(). Replace keys with values in the string.
        
        """
        out_str = in_str
        for key in in_dict:
            out_str = out_str.replace(key, in_dict[key])
        return out_str


    
    





