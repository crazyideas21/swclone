'''
Profiles and analyzes the timing of events along the control path. 

Arguments: [pcap at redis client] [csv of events at pox] [pcap at redis server]

Created on Feb 22, 2013

@author: danny
'''

import subprocess, sys
import lib.util
from pprint import pprint

def main(client_pcap=None, pox_csv=None, server_pcap=None):

    if None in (client_pcap, pox_csv, server_pcap):
        (client_pcap, pox_csv, server_pcap) = sys.argv[1:]
    
    # A list of (event_id, time, event_type).
    event_list = []
    
    # Maps event_id to a list of [(time, event_type)]
    event_dict = {} 
    
    for (time, src_port, dst_port) in parse_pcap(client_pcap):
        if dst_port == 6379: 
            event_list += [ (src_port, time, 'ingress_from_client') ]
        elif src_port == 6379: 
            event_list += [ (dst_port, time, 'egress_to_client') ]

    for (time, src_port, dst_port) in parse_pcap(server_pcap):
        if dst_port == 6379: 
            event_list += [ (src_port, time, 'egress_to_server') ]
        elif src_port == 6379: 
            event_list += [ (dst_port, time, 'ingress_from_server') ]
            
    with open(pox_csv) as pox_f:
        for line in pox_f:
            if 'None' in line:
                continue
            (time, event, src_port, dst_port) = line.strip().split(',')
            time = float(time)
            src_port = int(src_port)
            dst_port = int(dst_port)
            if dst_port == 6379:
                event_list += [ (src_port, time, event + '_from_client_to_server') ]
            elif src_port == 6379:
                event_list += [ (dst_port, time, event + '_from_server_to_client') ]
 
    # Focus on the 60th - 120th seconds
    index = 0
    min_time = min([time for (_, time, _) in event_list])
    while index < len(event_list):
        (_, time, _) = event_list[index]
        if time < min_time + 60 or time > min_time + 120:
            del event_list[index]
        else:
            index += 1
        
    # Construct event_dict from event_list.
    for (event_id, time, event_type) in event_list:
        event_dict.setdefault(event_id, []).append((time, event_type))

    # Extract event timings.
    pkt_in_durations = []
    flow_mod_durations = []

    for event_id in event_dict:
        
        event_list = event_dict[event_id]
        event_list.sort()

        for (start_event, end_event) in [('ingress_from_client', 'pkt_in_from_client_to_server'),
                                         ('ingress_from_server', 'pkt_in_from_server_to_client')]:
        
            try:
                pkt_in_start = filter(lambda (t, e): e == start_event, event_list)[0][0]
                pkt_in_end   = filter(lambda (t, e): e == end_event,   event_list)[0][0]
                assert pkt_in_end > pkt_in_start
                pkt_in_durations.append((pkt_in_end - pkt_in_start) * 1000.0)
            except (IndexError, AssertionError):
                pkt_in_durations.append(1000000 * 1000.0) # Lost packet
            
        for (start_event, end_event) in [('flow_mod_from_client_to_server', 'egress_to_server'),
                                         ('flow_mod_from_server_to_client', 'egress_to_client')]:

            try:        
                flow_mod_start = filter(lambda (t, e): e == start_event, event_list)[0][0]
                flow_mod_end   = filter(lambda (t, e): e == end_event,   event_list)[0][0]
                assert flow_mod_end > flow_mod_start
                flow_mod_durations.append((flow_mod_end - flow_mod_start) * 1000.0)
            except (IndexError, AssertionError):
                flow_mod_durations.append(1000000 * 1000.0) # Lost packet

    #pprint(event_dict)

    print 'Writing to data/pkt_in_durations.csv...'
    with open('data/pkt_in_durations.csv', 'w') as pkt_in_f:
        for (v, p) in lib.util.make_cdf_table(pkt_in_durations):
            print >> pkt_in_f, '%.4f,%.4f' % (v, p)
    
    print 'Writing to data/flow_mod_durations.csv...',
    with open('data/flow_mod_durations.csv', 'w') as flow_mod_f:
        for (v, p) in lib.util.make_cdf_table(flow_mod_durations):
            print >> flow_mod_f, '%.4f,%.4f' % (v, p)
    
    
    
def parse_pcap(pcap_file):
    """
    Returns a list of (time, src_port, dst_port).
    
    """
    p = subprocess.Popen('tcpdump -ttn -r %s' % pcap_file, shell=True, stdout=subprocess.PIPE)
    
    result_list = []
    
    for line in p.communicate()[0].split('\n'):
        if 'IP' not in line: continue
        line = line.strip()
        if line:
            fields = line.split(' ')
            time = float(fields[0])
            src_port = int(fields[2].split('.')[-1])
            dst_port = int(fields[4].split('.')[-1][0:-1])
            result_list += [(time, src_port, dst_port)]
        
    return result_list




if __name__ == '__main__':
    main()