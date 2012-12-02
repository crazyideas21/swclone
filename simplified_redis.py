#!/usr/bin/python

'''
Created on Nov 29, 2012

@author: danny
'''
import multiprocessing, time, socket, subprocess, random, sys, os
import cPickle as pickle
import lib.util as util


CONFIGURATION = 'mn'

if CONFIGURATION == 'hp':
    # List of hosts available for the experiment, as seen by the experiment's
    # network (i.e. in-band). 
    REDIS_SERVER_IN_BAND = '10.81.20.1' 
    REDIS_SERVER_OUT_OF_BAND = '172.22.14.213'

elif CONFIGURATION == 'tor':  # Top-of-rack switch as hardware baseline.
    REDIS_SERVER_IN_BAND = '172.22.14.213'
    REDIS_SERVER_OUT_OF_BAND = '172.22.14.213'
    
elif CONFIGURATION == 'mn':  # Mininet
    REDIS_SERVER_IN_BAND = '10.0.0.30'
    REDIS_SERVER_OUT_OF_BAND = '10.0.0.30'

else:
    assert False    

# Expected gap in milliseconds between successive requests. Actual value may
# differ.
#EXPECTED_GAP_MS = 50 # Mouse flows
EXPECTED_GAP_MS = 50 # Elephant flows

# How many bytes to put/get on the redis server.
#DATA_LENGTH = 64 # Mouse flows
DATA_LENGTH = 1*1000*1000 # Elephant flows

# How many hosts run the redis clients.
REDIS_CLIENT_HOST_COUNT = 8

MAX_RUNNING_TIME = 100
INTERESTING_TIME_START = 20 # 30 for mouse flows, 20 for elephant
INTERESTING_TIME_END = 90  # 60 for mouse flows, 90 for elephant


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
        if path.startswith('simplified-') and path.endswith('.tmp'):
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
            latency = -1
            bandwidth = 0
        else:
            latency = end_time - start_time  # seconds
            bandwidth = DATA_LENGTH / latency  # Bytes/s
        latency_list.append(latency * 1000.0)  # milliseconds
        bandwidth_list.append(bandwidth * 8.0 / 1000000.0)  # Mbps
    
    # Write to file.
    with open('data/simplified_redis_latency.csv', 'w') as f:
        for (v, p) in util.make_cdf_table(latency_list):
            print >> f, '%.10f,%.10f' % (v, p)
    with open('data/simplified_redis_bw.csv', 'w') as f:
        for (v, p) in util.make_cdf_table(bandwidth_list):
            print >> f, '%.10f,%.10f' % (v, p)
        



def redis_client_main():

    assert subprocess.call('ulimit -n 65536', shell=True) == 0

    start_time = time.time()
    start_end_times_queue = multiprocessing.Queue()
    client_proc_list = []
    
    while time.time() - start_time <= MAX_RUNNING_TIME:

        overhead_time_start = time.time()

        client_proc = multiprocessing.Process(target=redis_process,
                                              args=(start_end_times_queue,))
        client_proc.daemon = True
        client_proc.start()

        client_proc_list.append(client_proc)
        client_proc_list = filter(lambda p: p.is_alive(), client_proc_list)
        
        sleep_time = EXPECTED_GAP_MS / 1000.0 * REDIS_CLIENT_HOST_COUNT - (time.time() - overhead_time_start)
        time.sleep(random.uniform(sleep_time * 0.8, sleep_time * 1.2))

    for p in client_proc_list:
        os.kill(p.pid, 9)
        
    start_end_times_list = []
    while not start_end_times_queue.empty():
        start_end_times_list.append(start_end_times_queue.get())
        
    with open('simplified-' + str(random.random()) + '.tmp', 'w') as f:
        pickle.dump(start_end_times_list, f)
    
    print 'Done'




def redis_process(start_end_times_queue):
                        
    start_time = time.time()
    end_time = None
    
    try:
        # Connect to server
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.connect((REDIS_SERVER_IN_BAND, REDIS_PORT))
        sock.sendall('get x\r\n')
            
        # Make sure we get all the data. We check this lazily.
        recv_length = 0
        while True: 
            data = sock.recv(32768)
            recv_length += len(data)
            if recv_length > DATA_LENGTH and data.endswith('\r\n'):
                break
        
        end_time = time.time()            
        sock.close()
        
    except Exception:
        pass

    start_end_times_queue.put([start_time, end_time])




if __name__ == '__main__':
    main()