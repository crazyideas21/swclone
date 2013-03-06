'''
Created on Mar 1, 2013

@author: danny
'''
import threading, traceback, sys, time, random, struct
from Queue import PriorityQueue, Empty
import multiprocessing 
from pox.openflow.libopenflow_01 import ofp_packet_in, ofp_flow_mod
import async_redis
import pcap


REDIS_PORT = 6379

DELAY_PROFILE = 'quanta'

if DELAY_PROFILE == 'hp':
    MAGIC_OVERHEAD = 0.015
elif DELAY_PROFILE == 'monaco':
    MAGIC_OVERHEAD = 0.003
elif DELAY_PROFILE == 'quanta':
    MAGIC_OVERHEAD = 0.010
else:
    raise RuntimeError



overhead_f = open('ovs_overhead.tmp', 'w')


class DelayProfiler:
    
    
    def __init__(self, profile_file=None):
        """
        Loads file that contains the delays on the real switch. If not
        specified, there'd be no delays.
        
        """
        if profile_file is None:
            self._delay_bins = [0]
            self._bin_count = 1
            return

        # List of delays in seconds.
        raw_delay_list = []
        with open(profile_file) as f:
            for line in f:
                delay, _ = line.strip().split(None, 1)
                raw_delay_list += [ float(delay) / 1000.0 ]

        raw_delay_list.sort()
        
        # Chop up the delays into equal-sized bins.
        delay_count = len(raw_delay_list)
        bin_size = int(delay_count / 100)
        
        self._delay_bins = []
        for index in range(0, delay_count, bin_size):
            self._delay_bins += [ raw_delay_list[index] ]
        self._bin_count = len(self._delay_bins)
        
        print 'Loaded', self._bin_count, 'bins from', profile_file
        
    
    
    def get_delay(self):
        
        p = random.randint(0, self._bin_count - 1)
        return self._delay_bins[p]


    



class DelayedAction(threading.Thread):
    
    def __init__(self):
                
        threading.Thread.__init__(self)

        # Job queue
        self._pq = PriorityQueue()
        self._pq_lock = threading.RLock()
        self._exec_lock = threading.RLock()

        # Capture ingress SYN/ACK traffic into queue in a separate process.
        self._pkt_queue = multiprocessing.Queue()
        pcap_p = multiprocessing.Process(target=_pcap_process,
                                         args=(self._pkt_queue,))
        pcap_p.daemon = True
        pcap_p.start()
        
        # Introduce packet delays based on real performance.
        self._pkt_in_profiler = DelayProfiler('./profile/%s-pkt-in.csv' % DELAY_PROFILE)
        self._flow_mod_profiler = DelayProfiler('./profile/%s-flow-mod.csv' % DELAY_PROFILE)
        
        # Part of the ovs overhead that has not been accounted for.
        self._unused_ovs_overhead = 0
        
        # Start loop that executes jobs and that processes tcpdump output.
        self.daemon = True
        self.start()

        print '*' * 80
        print 'Delayed Action, using profile "%s".' % DELAY_PROFILE
        print '*' * 80




    def _get_delay(self, filter_obj):

        if isinstance(filter_obj, ofp_packet_in):
            return self._pkt_in_profiler.get_delay()
            
        elif isinstance(filter_obj, ofp_flow_mod):
            return self._flow_mod_profiler.get_delay()
        
        return 0    
        
        
        
        
                
    def add_job(self, filter_obj, func, *args, **kwargs):
                
        delay = self._get_delay(filter_obj) - MAGIC_OVERHEAD

        if delay <= 0.002:
            return self._execute(func, *args, **kwargs)
        elif delay > 5:
            return # Drop straight away

        current_time = time.time()                

        # Compensate for OVS overhead, but only for packet-in events.
        if isinstance(filter_obj, ofp_packet_in):
            pkt_in = args[1]
            (src_port, dst_port) = _get_tcp_src_dst_ports(pkt_in.data)
            if src_port and dst_port:
                ovs_overhead = self._get_ovs_overhead(src_port, dst_port, current_time)
                ovs_overhead += self._unused_ovs_overhead
                delay = delay - ovs_overhead
                if delay <= 0:
                    #self._unused_ovs_overhead += 0.0 - delay TODO: xxx 
                    return self._execute(func, *args, **kwargs)

        # Add event to job queue.
        with self._pq_lock:
            self._pq.put((delay + current_time, func, args, kwargs))
                
        
        
        
    def run(self):
        
        while True:
        
            # Peek
            current_time = time.time()    
            try:
                with self._pq_lock:
                    (next_time, _, _, _) = self._pq.queue[0]
                if current_time < next_time:
                    raise IndexError
                
            except IndexError:
                time.sleep(0.001)
                continue 
                            
            # Pop
            try:
                with self._pq_lock:
                    (_, func, args, kwargs) = self._pq.get_nowait()
            except Empty:
                continue

            # Run the job.            
            self._execute(func, *args, **kwargs)
            
    
    
    
    
    def _get_ovs_overhead(self, src_port, dst_port, current_time):
        """
        Continuously asks if pcap has seen <src_port, dst_port>. Stops when it
        appears in the pcap history. Extract the pcap time. Based on the current
        time, we can compute and return the overhead as a result of OVS.
        
        """
        # Average loop count is around 2.
        for _ in range(5):
            
            try:
                (timestamp, src, dst) = self._pkt_queue.get_nowait()
            except Empty:
                return 0
            
            if src == src_port and dst == dst_port:
                return current_time - timestamp  + 0.001 # Magic number 
    
        return 0

            
    
    def _execute(self, func, *args, **kwargs):
        
        try:
            with self._exec_lock:
                func(*args, **kwargs)
        except Exception, err:
            print >> sys.stderr, 'DelayedAction exception:', err
            print >> sys.stderr, traceback.format_exc()
        
    


def _pcap_process(pkt_queue):
    """
    Continuously adds captured packet tuples (time, src_port, dst_port) into the
    queue.
    
    """
    # Captures the first 64 bytes of all Redis SYN-SYNACK traffic. This is
    # sufficient for us to decipher the TCP src and dst ports.
    
    client_po = pcap.pcapObject()
    client_po.open_live(async_redis.CLIENT_INTERFACE, 64, 0, 100) 
    client_po.setfilter('(tcp[13] & 2 == 2) and (dst port %d)' % REDIS_PORT, 0, 0) 

    server_po = pcap.pcapObject()
    server_po.open_live(async_redis.SERVER_INTERFACE, 64, 0, 100) 
    server_po.setfilter('(tcp[13] & 2 == 2) and (src port %d)' % REDIS_PORT, 0, 0)     

    # Keep reading from pcap
    while True:
        for po in (client_po, server_po):
            pkt = po.next()
            if pkt:
                (_, data, timestamp) = pkt
                (src_port, dst_port) = _get_tcp_src_dst_ports(data)
                pkt_queue.put((timestamp, src_port, dst_port))




def _get_tcp_src_dst_ports(raw_pkt):
    """ Returns (src_port, dst_port). """

    ret = struct.unpack('!HH', raw_pkt[34:38])
    if REDIS_PORT in ret:
        return ret
    else:
        return (None, None)
    
    
    
    
    
    
    
    
    
    
    
    












#    
#def get_delay_hp(filter_obj):
#    
#    p = random.random()
#    
#    if isinstance(filter_obj, ofp_packet_in):
#        if p < 0.60:
#            return random.uniform(0.001, 0.019)
#        elif p < 0.80:
#            return random.uniform(0.019, 0.030)
#        elif p < 0.90:
#            return random.uniform(0.030, 0.042)
#        else:
#            return random.uniform(0.042, 0.120)
#        
#    elif isinstance(filter_obj, ofp_flow_mod):
#        if p < 0.10:
#            return random.uniform(0.025, 0.040)
#        elif p < 0.80:
#            return random.uniform(0.040, 0.090)
#        elif p < 0.90:
#            return random.uniform(0.090, 0.100)
#        else:
#            return random.uniform(0.100, 0.170)
#        
#    return 0
#
#
#
#
#
#
#def get_delay_monaco(filter_obj):
#    
#    p = random.random()
#    
#    if isinstance(filter_obj, ofp_packet_in):
#        if p < 0.55:
#            return random.uniform(0.001, 0.008)
#        else:
#            return random.uniform(0.008, 0.036)
#        
#    elif isinstance(filter_obj, ofp_flow_mod):
#        if p < 0.60:
#            return random.uniform(0.006, 0.013)
#        elif p < 0.70:
#            return random.uniform(0.013, 0.033)
#        else:
#            return random.uniform(0.033, 0.050)
#        
#    return 0
#
#
#
#    
#def get_delay_quanta(filter_obj):
#    
#    if isinstance(filter_obj, ofp_packet_in):
#        return random.uniform(0.001, 0.060)
#        
#    elif isinstance(filter_obj, ofp_flow_mod):
#        return random.uniform(0.005, 0.080)
#        
#    return 0
#
#
#
#
#
#
#
#
