'''
A test meant to demonstrate realistic behaviors of Redis when there are
thousands of client requests and each rule times out.

For scalability, this test spawns a number of processes, each of which creates
threads in which to make the connection to the Redis server.

Created on Sep 8, 2012

@author: Danny Y. Huang

'''
import socket, time, sys, traceback
import lib.util as util
import lib.config as config
from lib.switch import Switch
from multiprocessing import Process, Queue
import threading


REDIS_PORT = 6379
REDIS_HOST_OF = '10.66.10.1'      # C08
REDIS_HOST_TOR = '172.22.14.208'  # C08
CLIENT_BASE_PORT = 10000
TOTAL_CLIENT_COUNT = 50000






class RedisClientProcess:
    
    def __init__(self, thread_count, data_length, redis_host, 
                        worker_status_queue, client_id_queue, result_queue):
    
        self.thread_count = thread_count 
        self.data_length = data_length
        self.redis_host = redis_host
        self.worker_status_queue = worker_status_queue
        self.client_id_queue = client_id_queue
        self.result_queue = result_queue
    
        # Starts the required number of worker threads.
   
        for _ in range(thread_count):
            t = threading.Thread(target=self._worker_thread)
            t.daemon = True     
            t.start()

        # Run forever. Doesn't matter because this is a daemon process.
        
        while True:
            time.sleep(3600)
        


    def _worker_thread(self):

        # Notify the main process once started.
        self.worker_status_queue.put(None)
        
        while True:
            
            client_id = self.client_id_queue.get(True)
            start_time = time.time()
            
            try:
                sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
                sock.bind(('0.0.0.0', CLIENT_BASE_PORT + client_id))
                sock.connect((self.redis_host, REDIS_PORT))                       
                sock.sendall('get x\r\n')
                
                recv_length = 0
                while True: 
                    data = sock.recv(32768)
                    recv_length += len(data)
                    if recv_length > self.data_length and data.endswith('\r\n'):
                        break
                    
                end_time = time.time()    
                sock.close()
                result = [client_id, start_time, end_time]
            except:
                #print >> sys.stderr, '*' * 80, '\n\n', traceback.format_exc(), '*' * 80
                result = [client_id, start_time, None]
            finally:
                self.result_queue.put(result)
                
                
            




def redis_set(data_length):
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




def start_processes(process_count, worker_thread_per_process, 
                      client_count, gap_ms, data_length, redis_host):

    switch = Switch(config.active_config)
    data_length = int(data_length)
    total_workers = process_count * worker_thread_per_process
    redis_set(data_length)
        
    worker_status_queue = Queue(maxsize=total_workers)
    client_id_queue = Queue(maxsize=client_count)
    result_queue = Queue(maxsize=client_count)

    # Starts the worker processes that spawn individual worker threads.
    
    for _ in range(process_count):
        p = Process(target=RedisClientProcess,
                    args=(worker_thread_per_process, data_length, redis_host,
                          worker_status_queue, client_id_queue, result_queue))
        p.daemon = True
        p.start()

    # Wait for all worker threads to start.
        
    while True:
        started_count = worker_status_queue.qsize()
        if started_count < total_workers:
            print total_workers - started_count, 'workers yet to start.'
            time.sleep(1)
        else:
            break    
        
    # Send requests in a different thread.

    util.ping_test(dest_host=redis_host, how_many_pings=2)
        
    def requests():
        for client_id in range(client_count):
            client_id_queue.put(client_id)
            time.sleep(gap_ms / 1000.0)
    t = threading.Thread(target=requests)
    t.daemon = True
    t.start()
        
    # Monitor the changes for the first minute.

    base_time = time.time()
    
    while True:    
        current_count = result_queue.qsize()
        remaining_count = client_count - current_count 
        print 'Current:', current_count, 'Remaining:', remaining_count
        if remaining_count > 0 and time.time() - base_time < 120:
            try:
                time.sleep(10)
            except KeyboardInterrupt:
                break            
            if redis_host == REDIS_HOST_OF:
                rule_list = switch.dump_tables(filter_str='')
                print 't =', time.time() - base_time, 
                print '; tcam_size =', len([rule for rule in rule_list if 'table_id=0' in rule]), 
                print '; table_1_size =', len([rule for rule in rule_list if 'table_id=1' in rule]),
                print '; table_2_size =', len([rule for rule in rule_list if 'table_id=2' in rule]),
                print '; total_size =', len([rule for rule in rule_list if 'cookie' in rule])
        else:
            break
        
    # Extract the result into local lists. All time values are expressed in ms.
    # We're only interested in results between 30-60 seconds.
        
    print 'Analyzing the result...'
    start_time_list = []
    completion_time_list = []
    while not result_queue.empty():
        (_, start_time, end_time) = result_queue.get()
        if start_time - base_time >= 60:
            start_time_list.append(start_time * 1000.0)
            if end_time is None:
                completion_time = -100.0 # Not to be plotted.
            else:
                completion_time = (end_time - start_time) * 1000.0
            completion_time_list.append(completion_time)
        
    # Calculate the actual request gap.
    
    start_time_list.sort()
    gap_list = []
    for index in range(0, len(start_time_list) - 1):
        gap_list.append(start_time_list[index + 1] - start_time_list[index])
    print 'Client gap: (mean, stdev) =', util.get_mean_and_stdev(gap_list)
    
    # Calculate the CDF of completion times.
    
    cdf_list = util.make_cdf(completion_time_list)
    with open('data/realistic_redis_completion_times.txt', 'w') as f:
        for (x, y) in zip(completion_time_list, cdf_list):
            print >> f, x, y
    


def new_wildcard_rules():
    
    conf = config.active_config
    switch = Switch(conf)    
    switch.reset_flow_table()
    
    new_tcp_rule1 = 'cookie=0, priority=32768, idle_timeout=3600,hard_timeout=3600,tcp,in_port=' + \
                    conf.source_of_port + ',dl_src=' + \
                    conf.source_mac + ',dl_dst=' + conf.dest_mac + ',nw_src=' + \
                    conf.source_ip + ',nw_dst=' + conf.dest_ip + \
                    ',actions=output:' + conf.dest_of_port
    new_tcp_rule2 = 'cookie=0, priority=32768, idle_timeout=3600,hard_timeout=3600,tcp,in_port=' + \
                    conf.dest_of_port + ',dl_src=' + \
                    conf.dest_mac + ',dl_dst=' + conf.source_mac + ',nw_src=' + \
                    conf.dest_ip + ',nw_dst=' + conf.source_ip + \
                    ',actions=output:' + conf.source_of_port
                    
    for rule in [new_tcp_rule1, new_tcp_rule2]:                    
        add_rule_cmd = conf.add_rule_cmd(rule)                     
        util.run_ssh(add_rule_cmd, hostname=conf.ofctl_ip, verbose=True)



def main():
    
    conf = config.active_config
    switch = Switch(conf)    
    switch.reset_flow_table()    
    
    #new_wildcard_rules()
    start_processes(200, 50, TOTAL_CLIENT_COUNT, 10.0, 10*1000*1000, REDIS_HOST_OF)



if __name__ == '__main__':
    main()
    
