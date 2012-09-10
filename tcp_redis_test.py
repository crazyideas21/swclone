"""
Starts multiple redis clients to talk to the server using short, bursty TCP
flows.

Created on August 31, 2012

@author: Danny Y. Huang

"""
import socket, time, random, sys, subprocess
import lib.util as util
import lib.config as config
from lib.switch import Switch
from multiprocessing import Process, Queue



FLOW_TABLE_FILTER = 'table_id=0'
REDIS_PORT = 6379
REDIS_HOST_OF = '10.66.10.1'      # C08
REDIS_HOST_TOR = '172.22.14.208'  # C08
#REDIS_HOST_OF = '10.66.6.1'      # C06
#REDIS_HOST_TOR = '172.22.14.206' # C06
DATA_LENGTH = 64 #8 * 1000 * 1000
CLIENT_COUNT = 3000
CLIENT_BASE_PORT = 10000


def redis_set(data_length=DATA_LENGTH):
    """ Sets the variable we're going to get later via the TOR switch. """

    arg_list = ['*3', 
                '$3', 'set', 
                '$1', 'x', 
                '$%s' % data_length, 'z' * data_length, '']
    arg_str = '\r\n'.join(arg_list)
        
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.connect((REDIS_HOST_TOR, REDIS_PORT))    
    sock.sendall(arg_str)
    
    assert sock.recv(1024) == '+OK\r\n'
    sock.close()
    
    


def redis_client_process(client_id, redis_host, delay_queue, 
                          data_length=DATA_LENGTH):    
    
    #time.sleep(random.uniform(1, 17))
    
    start_time = time.time()
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    sock.bind(('0.0.0.0', CLIENT_BASE_PORT + client_id))
    try:
        sock.connect((redis_host, REDIS_PORT))
    except:
        delay_queue.put([client_id, None])
        return
           
    sock.sendall('get x\r\n')
    
    recv_length = 0
    while True: 
        data = sock.recv(32768)
        recv_length += len(data)
        if recv_length > data_length and data.endswith('\r\n'):
            break
        
    total_time = time.time() - start_time    
    sock.close()
    
    delay_queue.put([client_id, total_time])
    



def new_wildcard_rules():
    
    conf = config.active_config
    switch = Switch(conf)    
    switch.reset_flow_table()
    
    new_tcp_rule1 = 'cookie=0, priority=32768, idle_timeout=0,hard_timeout=0,tcp,in_port=' + \
                    conf.source_of_port + ',dl_src=' + \
                    conf.source_mac + ',dl_dst=' + conf.dest_mac + ',nw_src=' + \
                    conf.source_ip + ',nw_dst=' + conf.dest_ip + \
                    ',actions=output:' + conf.dest_of_port
    new_tcp_rule2 = 'cookie=0, priority=32768, idle_timeout=0,hard_timeout=0,tcp,in_port=' + \
                    conf.dest_of_port + ',dl_src=' + \
                    conf.dest_mac + ',dl_dst=' + conf.source_mac + ',nw_src=' + \
                    conf.dest_ip + ',nw_dst=' + conf.source_ip + \
                    ',actions=output:' + conf.source_of_port
                    
    for rule in [new_tcp_rule1, new_tcp_rule2]:                    
        add_rule_cmd = conf.add_rule_cmd(rule)                     
        util.run_ssh(add_rule_cmd, hostname=conf.ofctl_ip, verbose=True)




def new_exact_match_rules(wait_and_verify=True, reset_flow_table=True,
                             rule_count=CLIENT_COUNT, 
                             flow_table_filter=FLOW_TABLE_FILTER,
                             client_base_port=CLIENT_BASE_PORT):
        
    conf = config.active_config
    switch = Switch(conf)    
    if reset_flow_table: switch.reset_flow_table()
    
    # From client to redis server.
    new_tcp_rule1 = lambda client_id: \
                    'cookie=0,idle_timeout=0,hard_timeout=0,tcp,nw_tos=0x00,' + \
                    'dl_vlan=0xffff,dl_vlan_pcp=0x00,dl_src=' + \
                    conf.dest_mac + ',dl_dst=' + conf.source_mac + ',nw_src=' + \
                    conf.dest_ip + ',nw_dst=' + conf.source_ip + \
                    ',tp_src=' + str(client_id + client_base_port) + \
                    ',tp_dst=' + str(REDIS_PORT) + \
                    ',actions=output:' + conf.source_of_port
                    
    # From server back to client.
    new_tcp_rule2 = lambda client_id: \
                    'cookie=0,idle_timeout=0,hard_timeout=0,tcp,nw_tos=0x00,' + \
                    'dl_vlan=0xffff,dl_vlan_pcp=0x00,dl_src=' + \
                    conf.source_mac + ',dl_dst=' + conf.dest_mac + ',nw_src=' + \
                    conf.source_ip + ',nw_dst=' + conf.dest_ip + \
                    ',tp_dst=' + str(client_id + client_base_port) + \
                    ',tp_src=' + str(REDIS_PORT) + \
                    ',actions=output:' + conf.dest_of_port

    initial_rule_count = len(switch.dump_tables(filter_str=flow_table_filter))

    for client_id in range(rule_count):
        
        # Add the rules first.
        for rule_f in [new_tcp_rule1, new_tcp_rule2]:
            proc = util.run_ssh(conf.add_rule_cmd(rule_f(client_id)), 
                                hostname=conf.ofctl_ip, verbose=True, 
                                stdout=subprocess.PIPE)
            if wait_and_verify or (client_id % 5 == 0): 
                proc.wait()
        
        # Then verify if the correct number of rules have been added.
        if wait_and_verify and (client_id % 5 == 0 or client_id + 1 == rule_count):
            current_rule_count = len(switch.dump_tables(filter_str=flow_table_filter))
            try:
                assert current_rule_count - initial_rule_count == (client_id + 1) * 2
            except:
                print current_rule_count, initial_rule_count, client_id
                raise
    


def new_software_table_rules(rule_count=CLIENT_COUNT, 
                                 client_base_port=CLIENT_BASE_PORT):
    
    conf = config.active_config
    switch = Switch(conf)    
    
    # Fill up TCAM
    try:
        new_exact_match_rules(rule_count=1510, client_base_port=0)
    except AssertionError:
        if len(switch.dump_tables(filter_str=FLOW_TABLE_FILTER)) < 1500:
            raise

    # Any new rules will go into the software table.
    new_exact_match_rules(wait_and_verify=False, reset_flow_table=False, 
                          rule_count=CLIENT_COUNT,  
                          client_base_port=client_base_port)








def run(redis_host, delay_ms):
        
    util.ping_test(dest_host=redis_host)
        
    delay_queue = Queue()
    proc_list = []
    
    for client_id in range(CLIENT_COUNT):
        print 'Starting client', client_id
        p = Process(target=redis_client_process, 
                    args=(client_id, redis_host, delay_queue))
        p.daemon = True
        p.start()
        proc_list.append(p)
        time.sleep(delay_ms / 1000.0)
        
    counter = 0    
    for p in proc_list:
        p.join()
        counter += 1
        print CLIENT_COUNT - counter, 'left.'

    delay_list = []
    while not delay_queue.empty():
        (_, delay) = delay_queue.get()
        if delay is None:
            delay_ms = 0
        else:
            delay_ms = delay * 1000.0
        delay_list.append(delay_ms)
    
    cdf_list = util.make_cdf(delay_list)    
    with open('data/redis_delay.txt', 'w') as f:
        for (x, y) in zip(delay_list, cdf_list):
            print >> f, x, y




def main():
    
    redis_set()
    
    #new_exact_match_rules(wait_and_verify=True)
    #new_wildcard_rules()
    #new_software_table_rules()
    
    run(REDIS_HOST_OF, 1)
    
    
    
    
if __name__ == '__main__':
    if 'new_rules_only' in sys.argv:
        new_exact_match_rules()
    else:
        main()
