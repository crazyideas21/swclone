#!/usr/bin/python
'''
Asynchronous redis clients.

Created on Dec 11, 2012

@author: danny
'''
from multiprocessing import Queue, Process 


import time, socket, subprocess, random, sys, os, select
import cPickle as pickle
import lib.util as util


CONFIGURATION = 'hp'
FLOW_TYPE = 'mouse'
TWO_MACHINES = True

if CONFIGURATION == 'hp':
    # List of hosts available for the experiment, as seen by the experiment's
    # network (i.e. in-band).
    if TWO_MACHINES: 
        REDIS_SERVER_IN_BAND = '10.66.8.1' 
        REDIS_SERVER_OUT_OF_BAND = '172.22.14.207'
    else:
        REDIS_SERVER_IN_BAND = '10.81.20.1' 
        REDIS_SERVER_OUT_OF_BAND = '172.22.14.213'
        
    CPU_CORE_COUNT = 4

elif CONFIGURATION == 'tor':  # Top-of-rack switch as hardware baseline.
    if TWO_MACHINES:
        REDIS_SERVER_IN_BAND = '172.22.14.207'
        REDIS_SERVER_OUT_OF_BAND = '172.22.14.207'
    else:
        REDIS_SERVER_IN_BAND = '172.22.14.213'
        REDIS_SERVER_OUT_OF_BAND = '172.22.14.213'
    
    CPU_CORE_COUNT = 4

elif CONFIGURATION == 'mn':  # Mininet
    REDIS_SERVER_IN_BAND = '10.0.0.30'
    REDIS_SERVER_OUT_OF_BAND = '10.0.0.30'
    CPU_CORE_COUNT = 2
else:
    assert False    



if FLOW_TYPE == 'mouse':

    # Expected gap in milliseconds between successive requests. Actual value may
    # differ.
    EXPECTED_GAP_MS = 10 # Defaults to 50 
        
    # How many bytes to put/get on the redis server.
    DATA_LENGTH = 64 

    MAX_RUNNING_TIME = 130 # default 70
    INTERESTING_TIME_START = 60 # default 30
    INTERESTING_TIME_END = 120 # default 60  

elif FLOW_TYPE == 'elephant':

    EXPECTED_GAP_MS = 50  # Defaults to 50
    DATA_LENGTH = 1 * 1000 * 1000 

    MAX_RUNNING_TIME = 100
    INTERESTING_TIME_START = 20 
    INTERESTING_TIME_END = 90  

# How many hosts run the redis clients.
if TWO_MACHINES:
    REDIS_CLIENT_HOST_COUNT = 1
else:
    REDIS_CLIENT_HOST_COUNT = 8

REDIS_PORT = 6379



def main():
    
    if 'init_server' in sys.argv:
        init_redis_server()
    elif 'data' in sys.argv:
        data_analysis()
    elif 'redis' in sys.argv:
        redis_client_main()
    else:
        raise RuntimeError('Bad arguments:' + str(sys.argv))



def init_redis_server():
    """ Sets the variable we're going to get later. """

    arg_list = ['*3', 
                '$3', 'set', 
                '$1', 'x', 
                '$%s' % DATA_LENGTH, 'z' * DATA_LENGTH, '']
    arg_str = '\r\n'.join(arg_list)
        
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.connect((REDIS_SERVER_OUT_OF_BAND, REDIS_PORT))    
    sock.sendall(arg_str)
    
    assert sock.recv(1024) == '+OK\r\n'
    sock.close()
    
    #util.run_ssh('ulimit -n 65536', hostname=REDIS_SERVER_OUT_OF_BAND)
    
    print 'Init done. Data length =', DATA_LENGTH




def data_analysis():
    
    start_end_times = []
    
    for path in os.listdir('.'):
        if path.startswith('async-') and path.endswith('.tmp'):
            with open(path) as f:
                start_end_times += pickle.load(f)
            print 'Loaded', path
            
    # Extract steady state.
    min_time = min([start_time for (start_time, _) in start_end_times])
    def is_steady_state(start_end_time_tuple):
        (start_time, _) = start_end_time_tuple
        return min_time + INTERESTING_TIME_START <= start_time <= min_time + INTERESTING_TIME_END
    filtered_times = filter(is_steady_state, start_end_times)
    filtered_times.sort()    
    
    print 'Raw data size:', len(start_end_times),
    print 'Data at steady state:', len(filtered_times)
    
    # Figure out the actual gaps in milliseconds. 
    start_time_list = [start for (start, _) in filtered_times]
    gap_list = []
    for index in range(0, len(start_time_list) - 1):
        gap = start_time_list[index + 1] - start_time_list[index]
        gap_list.append(gap * 1000.0)
    gap_list.sort()
    print 'Client gap: (mean, stdev) =', util.get_mean_and_stdev(gap_list),
    print 'median =', gap_list[len(gap_list)/2]
    
    # Calculate latency and bandwidth.
    latency_list = []
    bandwidth_list = []
    for (start_time, end_time) in filtered_times:
        if end_time is None:
            latency = 1000
            bandwidth = 0
        else:
            latency = end_time - start_time  # seconds
            bandwidth = DATA_LENGTH / latency  # Bytes/s
        latency_list.append(latency * 1000.0)  # milliseconds
        bandwidth_list.append(bandwidth * 8.0 / 1000000.0)  # Mbps
    
    # Write to file.
    with open('data/async_redis_latency.csv', 'w') as f:
        for (v, p) in util.make_cdf_table(latency_list):
            print >> f, '%.10f,%.10f' % (v, p)
    with open('data/async_redis_bw.csv', 'w') as f:
        for (v, p) in util.make_cdf_table(bandwidth_list):
            print >> f, '%.10f,%.10f' % (v, p)
        















def redis_client_main():

    assert subprocess.call('ulimit -n 65536', shell=True) == 0

    result_queue = Queue()
    sleep_time = EXPECTED_GAP_MS / 1000.0 * REDIS_CLIENT_HOST_COUNT * CPU_CORE_COUNT
    client_proc_list = []   
    
    # Start client processes, one per CPU core.
    for _ in range(CPU_CORE_COUNT):
        client_proc = Process(target=_redis_client_process, args=(sleep_time, result_queue))
        client_proc.daemon = True
        client_proc.start()
        client_proc_list.append(client_proc)
    
    # Get results from finished processes. 
    start_end_times_list = []
    finished_process_count = 0
    while finished_process_count < CPU_CORE_COUNT: 
        if result_queue.empty():
            time.sleep(2)
        else:
            start_end_times_list += result_queue.get()
            finished_process_count += 1
        
    # Write start-end times to file.
    subprocess.call('rm -f async-*.tmp', shell=True)
    with open('async-' + str(random.random()) + '.tmp', 'w') as f:
        pickle.dump(start_end_times_list, f)
    
    print 'Done'
    sys.exit(0)
        





def _redis_client_process(gap, result_queue):
    """ Spawns redis clients with 'gap' second intervals. """

    master_start_time = time.time()
    last_redis_start_time = 0
    select_timeout_start_time = None
    
    conn_list = []
    start_end_time_list = []
    
    while True:
        
        # Check for exit conditions.
        current_time = time.time()
        if current_time - master_start_time > MAX_RUNNING_TIME:
            conn_list = []
            print os.getpid(), 'Max running time reached.'
            break
        
        # Make sure that at least a given number of seconds (i.e. 'gap) have
        # elapsed since we last started a new client connection.
        if current_time - last_redis_start_time >= gap:
            conn_list.append(RedisClientConnection())
            last_redis_start_time = current_time
        
        # Async I/O
        if _redis_client_select(conn_list, start_end_time_list):
            select_timeout_start_time = None
        else:
            # Check for select timeout (10 sec).
            if select_timeout_start_time is None:
                select_timeout_start_time = current_time
            if current_time - select_timeout_start_time > 10: 
                print >> sys.stderr, os.getpid(), 'selected timed out on', len(conn_list), 'connections'
                break
        
    # Send the start-end time list back to the main process.
    result_queue.put(start_end_time_list)
    
    print os.getpid(), 'Client process done.'
    
    
    
def _redis_client_select(conn_list, start_end_time_list):
    """ Returns False if select() times out. """
    
    (finished_conns, rlist, wlist) = ([], [], [])
    
    # Who wants I/O?
    for conn in conn_list:
        if conn.want_to_read():
            rlist.append(conn)
        elif conn.want_to_write():
            wlist.append(conn)
        else:
            finished_conns.append(conn)

    (rlist, wlist, xlist) = select.select(rlist, wlist, rlist + wlist, 0.002)

    # Select times-out.                                                            
    if len(rlist + wlist + xlist) == 0:
        return False
    
    # Bad sockets.
    finished_conns += xlist

    # Handle I/O.
    [conn.handle_read() for conn in rlist]
    [conn.handle_write() for conn in wlist]
            
    # Clean up. Record start-end times.
    for conn in finished_conns:
        start_end_time_list.append((conn.start_time, conn.end_time))
        conn_list.remove(conn)
    
    return True
    



class RedisClientConnection:
    
    def __init__(self):
        
        self.rbuf = ''
        self.wbuf = 'get x\r\n'
        
        self.start_time = time.time()
        self.end_time = None
        
        self.closed = False
        
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.sock.setblocking(0)
        self.sock.connect_ex((REDIS_SERVER_IN_BAND, REDIS_PORT))

    
    def fileno(self):
        return self.sock.fileno()


    def want_to_write(self):
        if self.closed:
            return False
        else:
            return len(self.wbuf) > 0


    def handle_write(self):
        try:
            sent = self.sock.send(self.wbuf)
            self.wbuf = self.wbuf[sent:]
        except IOError:
            self.closed = True


    def want_to_read(self):
        if self.closed or self.want_to_write():
            return False
        else:
            return not self._done_reading() 
    
    
    def handle_read(self):
        try:
            data = self.sock.recv(32768)
        except IOError:
            self.closed = True
            return

        if data:
            self.rbuf += data
            if self._done_reading():
                self.end_time = time.time()
                self.closed = True                    
        else:
            self.closed = True
    
    
    def _done_reading(self):
        return self.rbuf > DATA_LENGTH and self.rbuf.endswith('\r\n')
            
    
    def __del__(self):
        self.sock.close()
    
    








if __name__ == '__main__':
    main()