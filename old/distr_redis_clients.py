#!/usr/bin/python

'''
Distributed redis clients across multiple hosts. There are two modes:

(1) 'controller': Controls the experiment. Coordinates the clients and collects
data. 

(2) 'redis': Runs the redis clients. Waits for controller's instructions to 
start sending requests to the redis server. 

Controller-client protocol:

Each client loops forever and tries to unpickle the experiment_state.pickle file,
which has the ExperimentState object pickled. Upon success, a client submits
requests to the redis server continuously, until instructed to stop by the
ExperimentState object. A client saves the result to a unqiue file identified by
the experiment ID.

Created on Oct 23, 2012

@author: Danny Y. Huang

'''
import socket, sys, subprocess, threading, time, traceback, random, os
import cPickle as pickle
import lib.util as util
from lib.parallelize import ThreadPool

#===============================================================================
# Client parameters  
#===============================================================================

REDIS_CLIENT_PROCESS_COUNT = 10
WORKER_THREAD_COUNT = 50
REDIS_PORT = 6379

#===============================================================================
# Controller parameters  
#===============================================================================

EXPERIMENT_STATE_FILE = 'experiment_state_pickle.tmp'

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
EXPECTED_GAP_MS = 50 # Mouse flows
#EXPECTED_GAP_MS = 1000 # Elephant flows

# How many bytes to put/get on the redis server.
DATA_LENGTH = 64 # Mouse flows
#DATA_LENGTH = 1*1000*1000 # Elephant flows

# How many hosts run the redis clients.
REDIS_CLIENT_HOST_COUNT = 8

class ExperimentState:
    
    def __init__(self):
        self.redis_server = None
        self.gap_ms = None
        self.data_length = None
        self.uid = None
        







class ControllerMode:

    def __init__(self):
            
        # Publish the value of x onto the redis server.
        self.init_redis_server()

        # Remove previous temp data files.
        for client_data_file in os.listdir('.'):
            if client_data_file.endswith('.tmp'):
                os.remove(client_data_file)

        # Construct the new experiment state, thereby starting the experiment.
        experiment_state = ExperimentState()
        experiment_state.data_length = DATA_LENGTH
        experiment_state.gap_ms = EXPECTED_GAP_MS * REDIS_CLIENT_PROCESS_COUNT * REDIS_CLIENT_HOST_COUNT
        experiment_state.redis_server = REDIS_SERVER_IN_BAND
        experiment_state.uid = str(random.random())[2:6]
        with open(EXPERIMENT_STATE_FILE, 'w') as f:
            f.write(pickle.dumps(experiment_state))

        # Wait and stop.
        print 'Experiment State:', experiment_state.__dict__
        util.verbose_sleep(130, 'Collecting data...')
        os.remove(EXPERIMENT_STATE_FILE)
        
        # Waiting for all data files to be ready. The number of files to expect
        # is equal to the number of *.dummy files with the current experiment
        # UID.
        data_file_count = 0
        for filename in os.listdir('.'):
            if filename.startswith('dummy-' + experiment_state.uid):
                data_file_count += 1
                
        client_data_file_list = []
        while len(client_data_file_list) < data_file_count:
            print 'Waiting for all data files to be ready.',
            print 'Current:', len(client_data_file_list),
            print 'Expected total:', data_file_count
            time.sleep(5)
            client_data_file_list = []
            for filename in os.listdir('.'):
                if filename.startswith('data-' + experiment_state.uid):
                    client_data_file_list += [filename]
        
        # Join data.
        start_end_times = []
        for client_data_file in client_data_file_list:
            print 'Reading', client_data_file
            with open(client_data_file) as f:
                client_data_list = pickle.loads(f.read())
                start_end_times += [(start_time, end_time, client_data_file) \
                                    for (start_time, end_time) in client_data_list]
        
        self.save_data(start_end_times)




    def save_data(self, start_end_times):
        """
        Calculates the actual request rate and prints as the first line. Saves
        the CDFs of latency and bandwidth betweeen 1-2 minutes to disk. Assumes
        that all redis client hosts report correct times.
        
        """
        # Save the CDF of the start times. TODO: Debug.
        with open('data/distr_redis_raw_start_time_cdf.txt', 'w') as f:
            start_time_list = [t for (t, _, _) in start_end_times]
            for (t, p) in util.make_cdf_table(start_time_list):
                print >> f, '%.5f' % t, p
                
        # Save the start end times list. TODO: Debug.
        with open('data/distr_redis_raw_start_end_times.txt','w') as f:
            for (start_time, end_time, data_file) in start_end_times:
                print >> f, '%.5f' % start_time, end_time, data_file
        
        # Filter out irrelevant time values. Focus on 60th-120th seconds.
        min_time = min([start_time for (start_time, _, _) in start_end_times])
        def is_steady_state(start_end_time_tuple):
            (start_time, _, _) = start_end_time_tuple
            return min_time + 60 <= start_time <= min_time + 120
        filtered_times = filter(is_steady_state, start_end_times)
        filtered_times.sort()
        
        print 'Raw data size:', len(start_end_times),
        print 'Data between 60-120th seconds:', len(filtered_times)
        
        # Figure out the actual gaps in milliseconds. 
        start_time_list = [start for (start, _, _) in filtered_times]
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
        for (start_time, end_time, _) in filtered_times:
            if end_time is None:
                latency = -1
                bandwidth = 0
            else:
                latency = end_time - start_time  # seconds
                bandwidth = DATA_LENGTH / latency  # Bytes/s
            latency_list.append(latency * 1000.0)  # milliseconds
            bandwidth_list.append(bandwidth * 8.0 / 1000000.0)  # Mbps
        
        # Write to file.
        with open('data/distr_redis_latency.txt', 'w') as f:
            for (v, p) in util.make_cdf_table(latency_list):
                print >> f, v, p
        with open('data/distr_redis_bw.txt', 'w') as f:
            for (v, p) in util.make_cdf_table(bandwidth_list):
                print >> f, v, p
        
        




    def init_redis_server(self):
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








class RedisMode:
    
    def __init__(self):

        # Open child processes.
        is_child = (len(sys.argv) == 3 and sys.argv[2] == 'child')        
        if not is_child:
            for _ in range(REDIS_CLIENT_PROCESS_COUNT - 1):
                subprocess.Popen('./distr_redis_clients.py redis child', shell=True)
            
        # Attempt to deconstruct the experiment state.
        experiment_state = None
        while experiment_state is None:
            try:
                with open(EXPERIMENT_STATE_FILE) as f:
                    experiment_state = pickle.loads(f.read())
            except (IOError, pickle.UnpicklingError):
                time.sleep(2)
                                
        try:
            self.handle_experiment(experiment_state)
        except KeyboardInterrupt:
            return
        except:
            with open('run.log', 'a') as f:
                print >> f, 'Redis client crashed:', traceback.format_exc()
                


                
    def handle_experiment(self, experiment_state):

        self.lock = threading.Lock()
        self.last_request_start_time = 0
        last_request_start_time = -1 

        run_id = str(random.random())[2:6]
        run_start_time = time.time()
        print 'Experiment', experiment_state.uid, '-', run_id, 'begins.'


        # Create a dummy file so that the controller knows how many result files
        # to expect.
        dummy_filename = 'dummy-' + experiment_state.uid + '-' + run_id + '.tmp'        
        with open(dummy_filename, 'w') as f:
            print >> f, '0' * 65536
        subprocess.call('touch %s; sync' % dummy_filename, shell=True)
                        
        # List of (start_time, end_time).
        start_end_times = [] 
                
        # Bombard the redis server.        
        pool = ThreadPool(max_threads=WORKER_THREAD_COUNT, 
                          block_on_busy_workers=True)       
        
        # Record actual sleep time. TODO: Debug.
        sleep_f = open('sleep-time-' + run_id + '.tmp', 'w')
        
        while True:
            
            # The main loop times out after a while.
            current_time = time.time()
            if current_time - run_start_time > 140:
                break

            # How long to sleep? The time to sleep depends on when the last job
            # was started. But first, we need to make sure we're not using the
            # same last_request_start_time value repeatedly.
            self.lock.acquire()
            if last_request_start_time == self.last_request_start_time:
                # Blocks until we obtain an updated value (i.e. a new job
                # started.)
                self.lock.release()
                time.sleep(0.001)
                continue
            else:
                # A fresh new job has indeed started.
                last_request_start_time = self.last_request_start_time
                self.lock.release()
                            
            time_elapsed_ms = (current_time - last_request_start_time) * 1000.0                             
            if time_elapsed_ms < experiment_state.gap_ms:
                sleep_time_ms = experiment_state.gap_ms - time_elapsed_ms
                sleep_time_ms = random.uniform(sleep_time_ms * 0.9, sleep_time_ms * 1.1)                
                time.sleep(sleep_time_ms / 1000.0)
            else:
                sleep_time_ms = 0
            
            print >> sleep_f, '%.3f' % last_request_start_time, '%.0f' % time_elapsed_ms, '%.0f' % sleep_time_ms
            
            # Parallelize the request. This may block if all worker threads are
            # busy.
            pool.run(self.send_redis_request, experiment_state, start_end_times)            
        
        sleep_f.close()
        
        # Save results to a randomly named file with a common prefix per experiment.
        result_file = 'data-' + experiment_state.uid + '-' + run_id + '.tmp'
        with open(result_file, 'w') as f:
            f.write(pickle.dumps(start_end_times))
        subprocess.call('touch %s; sync' % result_file, shell=True)

        print 'Experiment', experiment_state.uid, 'ended.'
        pool.close()
            


    def send_redis_request(self, experiment_state, start_end_times):
                        
        start_time = time.time()
        end_time = None
        
        with self.lock:
            self.last_request_start_time = start_time
                                        
        try:
            # Connect to server
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.connect((experiment_state.redis_server, REDIS_PORT))
            sock.sendall('get x\r\n')
                
            # Make sure we get all the data. We check this lazily.
            recv_length = 0
            while True: 
                data = sock.recv(32768)
                recv_length += len(data)
                if recv_length > experiment_state.data_length and data.endswith('\r\n'):
                    break
            
            end_time = time.time()            
            sock.close()
            
        except Exception:
            pass

        # Submit result. Jobs that didn't finish have None as the end_time.
        with self.lock:
            start_end_times += [(start_time, end_time)]

            
            
                
    


def main():
    
    if 'controller' in sys.argv:
        ControllerMode()
    elif 'redis' in sys.argv:
        RedisMode()
    else:
        print >> sys.stderr, 'Wrong arguments.'



if __name__ == '__main__':
    main()