'''
Basic sanity test that generates packets and receives them with tcpdump.

Created on Aug 27, 2012

@author: danny
'''
from lib.pktgen import Pktgen
from lib.tcpdump import Tcpdump
import lib.config as config

import time

def handle_pkt(flow_id, seq_number, sent_time, recvd_time):
    print 'flow_id = %s, seq_number = %s' % (flow_id, seq_number)



def main():

    pktgen_obj = Pktgen(config.active_config)
    tcpdump_obj = Tcpdump(config.active_config)

    tcpdump_obj.start()    
    pktgen_obj.start()
    
    time.sleep(config.active_config.max_time)
    
    pktgen_result = pktgen_obj.stop_and_get_result()
    print pktgen_result.__dict__
    
    time.sleep(2)
    tcpdump_result = tcpdump_obj.stop_and_get_result()
    print tcpdump_result.__dict__
    
    time.sleep(2)
    tcpdump_obj.parse_pkt(handle_pkt)
    


if __name__ == '__main__':
    main()
    
    