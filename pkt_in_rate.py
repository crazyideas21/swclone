'''
Plots rate of packet-in events versus the rate of unmatched packets arriving at
switch.

Created on Aug 27, 2012

@author: danny
'''
import time, sys

from lib.pktgen import Pktgen
from lib.switch import Switch
from lib.exp_client import ExpControlClient
import lib.util as util
import lib.config as config


def main():
    
    with open('data/pkt_in_rate.csv', 'w') as f:
    
        for pkt_size in [64]:        
            for gap_ms in [0.001, 0.01, 0.1] + range(1, 6):
                (pktgen_rate, pkt_in_rate) = run(pkt_size, gap_ms)
                print >> f, pkt_size, gap_ms, pktgen_rate, pkt_in_rate
                f.flush()



def run(pkt_size, gap_ms):
        
    util.ping_test()
    
    switch = Switch(config.active_config)
    switch.reset_flow_table()
    
    control_client = ExpControlClient('mumu.ucsd.edu')
    control_client.execute('RESET')
    control_client.execute('SET learning False')
    
    pktgen = Pktgen(config.active_config)
    pktgen.low_level_start(pkt_count=50000, flow_count=50000,
                           pkt_size=pkt_size, gap_ns=1000000*gap_ms)
    
    try:
        time.sleep(20)
    except KeyboardInterrupt:
        pktgen.stop_and_get_result()
        sys.exit(1)
    
    pktgen_result = pktgen.stop_and_get_result()
    pkt_in_count = control_client.execute('GET pkt_in_count')
    
    pktgen_rate = pktgen_result.sent_pkt_count / pktgen_result.running_time
    pkt_in_rate = pkt_in_count / pktgen_result.running_time
        
    control_client.execute('RESET')
    
    return (pktgen_rate, pkt_in_rate)




if __name__ == '__main__':
    main()