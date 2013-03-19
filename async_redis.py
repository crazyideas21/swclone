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



class FlowType:
    mouse = 'mouse'
    elephant = 'elephant'

# ==============================================================================
CONFIGURATION = 'ovs'  # CHANGE THIS
FLOW_TYPE = FlowType.mouse  # CHANGE THIS
# ==============================================================================

REDIS_CLIENT_HOST_COUNT = 1
CPU_CORE_COUNT = 1

INFINITY = float('inf')


if CONFIGURATION == 'hp':
    REDIS_SERVER_IN_BAND = '192.168.100.2' 
    REDIS_SERVER_OUT_OF_BAND = '127.0.0.1'
    CLIENT_INTERFACE = 'eth1'
    SERVER_INTERFACE = 'eth2' 

elif CONFIGURATION == 'monaco':
    REDIS_SERVER_IN_BAND = '192.168.100.2'
    REDIS_SERVER_OUT_OF_BAND = '127.0.0.1'
    
        
elif CONFIGURATION == 'quanta':
    REDIS_SERVER_IN_BAND = '192.168.100.2'
    REDIS_SERVER_OUT_OF_BAND = '127.0.0.1'
    CLIENT_INTERFACE = 'eth4'
    SERVER_INTERFACE = 'eth6'

elif CONFIGURATION == 'ovs':
    REDIS_SERVER_IN_BAND = '192.168.100.4'
    REDIS_SERVER_OUT_OF_BAND = '127.0.0.1'
    CLIENT_INTERFACE = 'veth4'
    SERVER_INTERFACE = 'veth6'
    
else:
    assert False    



if FLOW_TYPE == FlowType.mouse:

    # Expected gap in milliseconds between successive requests. Actual value may
    # differ.
    EXPECTED_GAP_MS = 50 # Defaults to 50 
        
    # How many bytes to put/get on the redis server.
    DATA_LENGTH = 64 

    # Max number of flows to start.
    MAX_QUERY_COUNT = float('inf')

    MAX_RUNNING_TIME = 130 # default 70
    INTERESTING_TIME_START = 60 # default 30
    INTERESTING_TIME_END = 120 # default 60  
    
    # How long each Redis query time out.
    MAX_QUERY_SECONDS = 2
    
    # At least how fast a query should receive data.
    MIN_RECV_Mbps = 0
    
    # Number of concurrent connections
    MAX_CONCURRENT_CONNECTIONS = INFINITY
    
    RECV_BUF_SIZE = 32768
        
    SHOW_STATS = False

elif FLOW_TYPE == FlowType.elephant:

    EXPECTED_GAP_MS = 0
    DATA_LENGTH = 500 * 1000 * 1000 
    MAX_CONCURRENT_CONNECTIONS = 1000

    MAX_QUERY_COUNT = INFINITY

    MAX_RUNNING_TIME = 130
    INTERESTING_TIME_START = 60
    INTERESTING_TIME_END = 120

    MAX_QUERY_SECONDS = 3600
    MIN_RECV_Mbps = 0
    
    SHOW_STATS = True
    RECV_BUF_SIZE = 1048576


REDIS_PORT = 6379




def main():
    
    if 'init_server' in sys.argv:
        init_redis_server()
    elif 'data' in sys.argv:
        data_analysis()
    elif 'client' in sys.argv:
        redis_client_main()
    elif 'tcpdump' in sys.argv:
        tcpdump()
    else:
        raise RuntimeError('Bad arguments:' + str(sys.argv))



def init_redis_server():
    """ Sets the variable we're going to get later. """

    check_ulimit()
    
    print 'Initialzing the redis server...'

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



def tcpdump():
    
    client_p = subprocess.Popen('rm /tmp/client.pcap; tcpdump -i %s -w /tmp/client.pcap >/dev/null 2>&1' % CLIENT_INTERFACE, shell=True)
    server_p = subprocess.Popen('rm /tmp/server.pcap; tcpdump -vi %s -w /tmp/server.pcap' % SERVER_INTERFACE, shell=True)
    
    try:
        time.sleep(3600)
    except KeyboardInterrupt:
        pass
    
    # Send Control+C to both tcpdump processes.
    client_p.send_signal(2)
    server_p.send_signal(2)    

    print 'TCPDUMP completed.'




def data_analysis():

    start_end_times = []
    
    # Load experiment data file
    try:
        data_file = 'async-' + os.environ['EXP_NAME']
    except KeyError:
        data_file = None
    for path in os.listdir('data'):
        if (path == data_file) or \
            (data_file is None and path.startswith('async-') and path.endswith('.tmp')):
            with open('data/' + path) as f:
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
    
    # Save start_time list and gap list.
    with open('data/start_times.csv', 'w') as start_time_f:
        for start_time_v in start_time_list:
            print >> start_time_f, '%.8f' % start_time_v
    with open('data/gaps.csv', 'w') as gap_f:
        for (v, p) in util.make_cdf_table(gap_list):
            print >> gap_f, '%f,%f' % (v, p)
    
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
    print 'Writing to data/async_redis_latency.csv...'
    with open('data/async_redis_latency.csv', 'w') as f:
        for (v, p) in util.make_cdf_table(latency_list):
            print >> f, '%.10f,%.10f' % (v, p)
            
    print 'Writing to data/async_redis_bw.csv...'
    with open('data/async_redis_bw.csv', 'w') as f:
        for (v, p) in util.make_cdf_table(bandwidth_list):
            print >> f, '%.10f,%.10f' % (v, p)
    
    # Analyze timings of OF events.
    
    subprocess.call('cp of_timings.csv data/; cp /tmp/client.pcap /tmp/server.pcap data/', shell=True)

    
    import timing_analysis
    timing_analysis.main('data/client.pcap', 'data/of_timings.csv', 'data/server.pcap')








def check_ulimit():
    """ Make sure that ulimit is set manually before experiment. """
    
    p = subprocess.Popen('ulimit -n', shell=True, stdout=subprocess.PIPE)
    limit_n = p.communicate()[0]
    assert limit_n.strip() == '65536'





def redis_client_main():

    check_ulimit()
    try:
        exp_name = os.environ['EXP_NAME']
    except KeyError:
        exp_name = str(random.random()) + '.tmp'
    
    print 'Starting client main(), using flow type "%s" and configuration "%s".' % (FLOW_TYPE, CONFIGURATION)
    print 'Experiment name:', exp_name

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
    subprocess.call('rm -f data/async-*.tmp', shell=True)
    with open('data/async-' + exp_name, 'w') as f:
        pickle.dump(start_end_times_list, f)
    
    print 'Done'
    sys.exit(0)
        





def _redis_client_process(gap, result_queue):
    """ Spawns redis clients with 'gap' second intervals. """

    # Prevent all client processes to start at the same time.
    if CPU_CORE_COUNT > 1:
        time.sleep(random.uniform(1,3))

    master_start_time = time.time()
    last_redis_start_time = 0
    last_query_timeout_check_time = 0
    select_timeout_start_time = None
    
    query_count = 0
    
    conn_list = []
    start_end_time_list = []
    
    # Maps a connection to start_bytes, which record the number of
    # bytes the connection receives at the beginning of the steady state.
    conn_start_bytes_dict = {}

    # Similar, records the number of bytes at the end of the steady state.
    conn_end_bytes_dict = {}
    
    while True:
        
        # Check for exit conditions.
        current_time = time.time()
        if current_time - master_start_time > MAX_RUNNING_TIME:
            conn_list = []
            print os.getpid(), 'Max running time reached.'
            break

        # Make sure that at least a given number of seconds (i.e. 'gap) have
        # elapsed since we last started a new client connection.
        if (current_time - last_redis_start_time >= gap and \
            query_count < MAX_QUERY_COUNT and \
            len(conn_list) < MAX_CONCURRENT_CONNECTIONS):
            
            if FLOW_TYPE == FlowType.elephant:
                # Fast start.
                start_count = MAX_CONCURRENT_CONNECTIONS - len(conn_list)
            else:
                start_count = 1
            
            for _ in range(start_count):
                conn_list.append(RedisClientConnection(query_count))
                last_redis_start_time = current_time
                query_count += 1
                if SHOW_STATS:
                    print 'Started query #', (query_count - 1)
        
        # Async I/O
        if _redis_client_select(conn_list, start_end_time_list):
            select_timeout_start_time = None
        else:
            # Check for select timeout (10 sec).
            if select_timeout_start_time is None:
                select_timeout_start_time = current_time
            if current_time - select_timeout_start_time > 10: 
                print >> sys.stderr, os.getpid(), 'select timed out on', len(conn_list), 'connections'
                break

        # We only permit a maximum of MAX_QUERY_SECONDS per client query, and some
        # minimum recv rate. Check every five seconds.
        if current_time - last_query_timeout_check_time >= 5:
            last_query_timeout_check_time = current_time
            removed_cxn_id_list = []
            for conn in conn_list[:]:
                if (current_time - conn.start_time >= MAX_QUERY_SECONDS) or\
                    (conn.rbuf_length > 0 and (conn.rbuf_length - conn.rbuf_last_length) * 8 / 5.0 / 1000000 < MIN_RECV_Mbps):
                    conn.closed = True
                    removed_cxn_id_list += [conn.cxn_id]
                else:
                    conn.rbuf_last_length = conn.rbuf_length
                    
            if removed_cxn_id_list:
                print >> sys.stderr, os.getpid(), 'removed %s timed out queries.' % len(removed_cxn_id_list)
                if SHOW_STATS:
                    print >> sys.stderr, 'Removed', removed_cxn_id_list
        
        # Sample the throughput at the beginning and end of steady state.
        if FLOW_TYPE == FlowType.elephant:
            
            # Start of steady state:
            if ((len(conn_start_bytes_dict) == 0) and \
                (current_time - master_start_time >= INTERESTING_TIME_START)):
                for conn in conn_list:
                    conn_start_bytes_dict[conn] = conn.rbuf_length
                    
            # End of steady state:
            if ((len(conn_end_bytes_dict) == 0) and \
                (current_time - master_start_time >= INTERESTING_TIME_END)):
                for conn in conn_list:
                    conn_end_bytes_dict[conn] = conn.rbuf_length

    # Combine the two conn_*_bytes_dict. Calculate the Mbps.
    if FLOW_TYPE == FlowType.elephant:
        common_conn = set(conn_start_bytes_dict.keys()) & set(conn_end_bytes_dict.keys())
        Mbps_list = []
        for conn in common_conn:
            bytes_received = conn_end_bytes_dict[conn] - conn_start_bytes_dict[conn]
            Bps = bytes_received / (INTERESTING_TIME_END - INTERESTING_TIME_START)
            Mbps = Bps * 8.0 / 1000000.0
            Mbps_list += [Mbps]
        Mbps_list += [0] * (MAX_CONCURRENT_CONNECTIONS - len(Mbps_list))
        with open('data/elephant-throughput.csv', 'w') as f:
            for (v, p) in util.make_cdf_table(Mbps_list):
                print >> f, '%f,%f' % (v, p)
        
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
        conn.close()
        conn_list.remove(conn)
        if SHOW_STATS:
            if conn.end_time:
                time_delta = conn.end_time - conn.start_time
                print 'Query', conn.cxn_id, 'done in', int(time_delta), 'seconds at', 
                print '%.3f Mbps.' % (DATA_LENGTH * 8 / time_delta / 1000000.0)
            else:
                print 'Query', conn.cxn_id, 'timed out.' 
    
    return True
    



class RedisClientConnection:
    
    def __init__(self, cxn_id):
        
        self.cxn_id = cxn_id
        
        self.wbuf = 'get x\r\n'        
        self.rbuf_length = 0
        self.rbuf_last_read = ''
        
        self.rbuf_last_length = 0 # Used to calculate recv speed
        
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
            data = self.sock.recv(RECV_BUF_SIZE)
        except IOError:
            self.closed = True
            return

        if data:
            # Keep only the last 1024 bytes into the read buffer.
            self.rbuf_last_read += data
            self.rbuf_last_read = self.rbuf_last_read[-1024:]
            self.rbuf_length += len(data)
            #print 'zzzz Connection', self.cxn_id, 'got', len(data), 'bytes'
            if self._done_reading():
                self.end_time = time.time()
                self.closed = True                    
        else:
            self.closed = True
    
    
    def _done_reading(self):
        return self.rbuf_length > DATA_LENGTH and self.rbuf_last_read.endswith('\r\n')
            
    
    def __del__(self):
        self.sock.close()
    
    
    def close(self):
        self.sock.close()
    








if __name__ == '__main__':
    main()