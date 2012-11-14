'''
Investigates the relationship between the rate of incoming packets at the switch
and the rate of successful rule installations.

Created on Nov 5, 2012

@author: Danny Y. Huang

'''
from lib.exp_client import ExpControlClient
from lib.switch import Switch
from lib.pktgen import Pktgen
from lib.tcpdump import Tcpdump
import lib.config as config
import lib.util as util
import time




def main():
#
#    result = run(packet_per_second=100, pkt_size=64)
#    print '*' * 80
#    print result
#    return 

    with open('data/flow_mod_success_pps.txt', 'w') as data_f:
        for pkt_size in (64, 1500):
            for pps in (10, 30, 100, 300, 1000, 3000, 10000, 30000, 100000):            
                (pktgen_pps, pkt_in_pps, flow_mod_pps, flow_mod_pps_stdev, pkt_out_pps) = run(packet_per_second=pps, pkt_size=pkt_size)
                print >> data_f, pkt_size, pktgen_pps, pkt_in_pps, flow_mod_pps, flow_mod_pps_stdev, pkt_out_pps
                data_f.flush()





def run(packet_per_second=100, pkt_size=1500, run_time=220):
    """
    Returns (pktgen_pps, pkt_in_pps, flow_mod_pps, flow_mod_pps_stdev, pkt_out_pps), where
    pps_in is the actual number of packets/sec of pktgen, and flow_mod_pps and
    flow_mod_pps_stdev are the mean and stdev pps of successful flow
    installations at steady state.
    
    """
    util.ping_test()
    
    switch = Switch(config.active_config)
    switch.reset_flow_table()

    # Initialize the experimental controller so that POX would have the
    # necessary settings.
    control_client = ExpControlClient('mumu.ucsd.edu')
    control_client.execute(['RESET'])
    control_client.execute(['SET', 'flow_stat_interval', 20])
    control_client.execute(['SET', 'install_bogus_rules', True])
    control_client.execute(['SET', 'emulate_hp_switch', True])

    # Start capturing packets.
    tcpdump = Tcpdump(config.active_config)
    tcpdump.start()
    tcpdump_start_time = time.time()

    # Start firing packets.
    pktgen = Pktgen(config.active_config)
    gap = 1.0 / packet_per_second
    pkt_count = int(run_time * packet_per_second)
    pktgen.low_level_start(pkt_count=pkt_count, pkt_size=pkt_size, 
                           gap_ns=gap*1000*1000*1000, flow_count=1)

    pktgen_start_time = time.time()
    flow_mod_pps_list = []
    
    # How fast were rules successfully written into the hardware table? We take
    # statistics at steady state. Also display flow statistics once in a while.
    last_stat_time = [0]
    def callback(t_left):
        flow_stat_dict = control_client.execute(['GET',  'flow_count_dict'])
        for stat_time in sorted(flow_stat_dict.keys()):
            if stat_time > last_stat_time[0]:
                last_stat_time[0] = stat_time
                flow_count = flow_stat_dict[stat_time]
                print t_left, 'seconds left, with flows', flow_count
                if pktgen_start_time + 60 <= time.time() <= pktgen_start_time + 180:
                    flow_mod_pps_list.append(flow_count / 10.0)

    # Check the stat every 20 seconds.                     
    util.callback_sleep(run_time, callback, interval=20)
    
    # How fast were packets actually generated?
    pktgen_result = pktgen.stop_and_get_result()
    pktgen_pps = pktgen_result.sent_pkt_count / pktgen_result.running_time
    
    # How fast were pkt_out events?
    tcpdump_end_time = time.time()
    tcpdump_result = tcpdump.stop_and_get_result()
    pkt_out_pps = (tcpdump_result.dropped_pkt_count + tcpdump_result.recvd_pkt_count) / \
                    (tcpdump_end_time - tcpdump_start_time)
    
    # Calculate the mean and stdev of successful flow_mod pps.
    (flow_mod_pps, flow_mod_pps_stdev) = util.get_mean_and_stdev(flow_mod_pps_list)
    
    # How fast were pkt_in events arriving?
    pkt_in_count = control_client.execute(['GET', 'pkt_in_count'])
    pkt_in_start_time = control_client.execute(['GET', 'pkt_in_start_time'])
    pkt_in_end_time = control_client.execute(['GET', 'pkt_in_end_time'])
    pkt_in_pps = pkt_in_count / (pkt_in_end_time - pkt_in_start_time)
    
    return (pktgen_pps, pkt_in_pps, flow_mod_pps, flow_mod_pps_stdev, pkt_out_pps)




if __name__ == '__main__':
    main()