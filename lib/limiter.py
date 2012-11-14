'''
Lets packets pass or drop to limit the packet rate.

Created on Nov 7, 2012

@author: danny
'''

import time

class Limiter:
    """ Lets packets pass or drop to limit the packet rate. """
    
    def __init__(self, max_pps, granularity=1):
        """ 
        max_pps: sets the maximum packet per second.
        
        granularity: the number of seconds we look back to the past in which to
        check the packet rate; i.e. the length of the sliding window.
        
        """
        self._time_window = []
        self._time_window_size = granularity
        self._max_pkt_count_per_window = max_pps * granularity



    def to_forward_packet(self):
        """ Whether to forward the current packet. """

        # Purge items that are older than the size of the time window.
        current_time = time.time()
        min_time = current_time - self._time_window_size
        self._time_window = filter(lambda t: t >= min_time, self._time_window)

        # Within this window, we have sent fewer packets than desired. We don't
        # drop the packet.
        if len(self._time_window) < self._max_pkt_count_per_window:
            self._time_window.append(current_time)
            return True
        else:
            return False



def test_run(with_limiter=True):
    
    import random
    
    # Target: at most 100 pps (or at least 10 ms gaps).
    limiter = Limiter(100, granularity=0.2)
    pkt_time_list = []
    base_time = time.time()
    
    # Simulates the packet handling function.
    def pkt_arrives():
        if with_limiter:
            if limiter.to_forward_packet():
                pkt_time_list.append(time.time() - base_time)
        else:
            pkt_time_list.append(time.time() - base_time)
    
    # Simulates slow pps. Make the gaps more than 10 ms.
    for _ in range(200):
        time.sleep(random.uniform(0,30)/1000.0)
        pkt_arrives()
    print 'Slow pps:', len(pkt_time_list) / (max(pkt_time_list) - min(pkt_time_list))
    
    pkt_time_list = []
    
    # Simulates fast pps.
    for _ in range(400):
        time.sleep(random.uniform(0,7)/1000.0)
        pkt_arrives()
    print 'Fast pps:', len(pkt_time_list) / (max(pkt_time_list) - min(pkt_time_list))

        

def test():
    
    print 'With limiter:'
    test_run(with_limiter=True)

    print 'Without limiter:'
    test_run(with_limiter=False)













if __name__ == '__main__':
    test()