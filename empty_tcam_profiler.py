'''
Observes the relationship between flow-mod events and the number of rules added
to an empty TCAM.

Created on Aug 28, 2012

@author: danny

'''
from lib.switch import Switch
from lib.exp_client import ExpControlClient
import lib.config as config
import lib.util as util
import socket


def main():
    
    with open('data/empty_tcam_profiler.csv', 'w') as f:
        for flow_mod_gap_ms in [2,4,6,8,10]:        
            (tcam_rule_count, total_rule_count, flow_mod_rate) = run(flow_mod_gap_ms)
            print >> f, tcam_rule_count, total_rule_count, flow_mod_rate, flow_mod_gap_ms
            f.flush()
            





def run(flow_mod_gap_ms):

    util.ping_test()
    
    switch = Switch(config.active_config)
    switch.reset_flow_table()
    
    control_client = ExpControlClient('mumu.ucsd.edu')
    control_client.execute('RESET')
    control_client.execute('SET auto_install_rules False')
    control_client.execute('SET manual_install_gap_ms %s' % flow_mod_gap_ms)
    control_client.execute('SET manual_install_active True')
    
    # Send a starter packet to trigger packet-in. Doesn't matter what port it
    # goes to, as long as it has the IP address of what would have been the
    # pktgen host.
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.sendto('Hi', (config.active_config.source_ip, 12345))
    
    # Let the whole system run for a while. We cannot check for TCAM status;
    # that'd sometimes take forever when the switch is busily processing flow-
    # mods, and it'd probably affect the flow-mods. We check the TCAM
    # afterwards.
    util.verbose_sleep(60)
    control_client.execute('SET manual_install_active False')
    
    # Gather stats about flow-mod. The flow-mod gap may not be accurate.
    flow_mod_count = control_client.execute('GET flow_mod_count')
    flow_mod_start_time = control_client.execute('GET flow_mod_start_time')
    flow_mod_end_time = control_client.execute('GET flow_mod_end_time')
    flow_mod_rate = flow_mod_count / (flow_mod_end_time - flow_mod_start_time)
    
    # Wait for the switch to stabilize before asking it for stats.
    util.verbose_sleep(80)
    print 'Dumping table...'
    
    # Parse flow tables. Search up to the last point of a TCAM-write, which
    # signifies a full TCAM. Up to that point, we count the total number of
    # rules added.
    rule_list = switch.dump_tables(filter_str='')
    tcam_rule_count = 0
    total_rule_count = 0
    print 'Parsing', len(rule_list), 'rules...'
    for rule in rule_list:
        total_rule_count += 1
        if 'table_id=0' in rule:
            tcam_rule_count += 1
        if tcam_rule_count == 1500:
            break
    
    control_client.execute('RESET')
    switch.reset_flow_table()
    util.verbose_sleep(5)
    
    return (tcam_rule_count, total_rule_count, flow_mod_rate)
    



if __name__ == '__main__':
    main()