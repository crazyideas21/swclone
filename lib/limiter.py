'''
Lets packets pass or drop to limit the packet rate.

Created on Nov 7, 2012

@author: danny
'''
import numpy as np
import time, csv, random
try:
    from scipy.interpolate import griddata #@UnresolvedImport
except:
    pass



def load_lookup_table(csv_file_name, pkt_in_col, pkt_out_col, output_col):

    # Initialize the grid
    grid_x, grid_y = np.mgrid[0:1001, 0:1001]
    
    # Load known points and values.
    points, values = [], []
    with open(csv_file_name) as csv_file:
        reader = csv.reader(csv_file)
        for row in reader:
            points.append([int(float(row[i])) for i in [pkt_in_col, pkt_out_col]])
            values.append(float(row[output_col]))    

    # Interpolate!
    points, values = np.array(points), np.array(values)    
    return griddata(points, values, (grid_x, grid_y))
                


class DynamicLimiter:
    """ Dynamically limits packet-rate based on a look-up table. """
    
    class PacketType:
        PktIn = 'PktIn'
        PktOut = 'PktOut'
    
    def __init__(self):
        
        self._window_dict = {}
        
        self._lookup_table = {}
        self._lookup_table[DynamicLimiter.PacketType.PktIn] = load_lookup_table('lookup-table/hp-full-frame.csv', 0, 2, 3)
        self._lookup_table[DynamicLimiter.PacketType.PktOut] = load_lookup_table('lookup-table/hp-full-frame.csv', 0, 2, 5)
        
        self._ovs_table = {}
        self._ovs_table[DynamicLimiter.PacketType.PktIn] = load_lookup_table('lookup-table/ovs-full-frame.csv', 3, 2, 0)
        self._ovs_table[DynamicLimiter.PacketType.PktOut] = load_lookup_table('lookup-table/ovs-full-frame.csv', 3, 2, 5)

    
    

    def get_packet_rate(self, pkt_type, add_current_to_window=False):
        
        current_time = time.time()    
        
        # Add pkt to window
        if not self._window_dict.has_key(pkt_type):
            self._window_dict[pkt_type] = []
        window = self._window_dict[pkt_type]
        if add_current_to_window:
            window.append(current_time)
        
        # Remove times more than 5 seconds ago from window.
        min_time = current_time - 5 
        while window:
            if window[0] < min_time:
                window.pop(0)
            else:
                break

        return len(window) / 5.0
        
        
    
    def to_forward_packet(self, pkt_type):
        
        PktIn = DynamicLimiter.PacketType.PktIn
        PktOut = DynamicLimiter.PacketType.PktOut

        # Compute the observed pkt rate at the controller.
        pkt_in_rate = int(self.get_packet_rate(PktIn, pkt_type == PktIn))    
        pkt_out_rate = int(self.get_packet_rate(PktOut, pkt_type == PktOut))
        
        if pkt_in_rate < 100 or pkt_out_rate < 100:
            return True

        # Deduce the ingress rate at OVS.
        ingress_rate = self._ovs_table[PktIn][pkt_in_rate][pkt_out_rate]
        if ingress_rate == np.nan:
            ingress_rate = pkt_in_rate
        ingress_rate = int(ingress_rate)

        # Based on the deduced ingress and observed pkt-out, what should HP's
        # pkt-in rate be?
        if pkt_type == PktIn:
            hp_pkt_in_rate = self._lookup_table[PktIn][ingress_rate][pkt_out_rate]
            if hp_pkt_in_rate == np.nan:
                return True
            return random.random() < hp_pkt_in_rate / pkt_in_rate 

        # Based on the deduced ingress and observed pkt-out, how much of OVS's
        # egress is lost?
        egress_rate = self._lookup_table[PktOut][pkt_in_rate][pkt_out_rate]
        if egress_rate == np.nan:
            egress_delivered = 1.0
        else:
            egress_delivered = egress_rate / pkt_out_rate 
        
        # Because of this loss, we need to deliver more pkt-outs to achieve HP's
        # egress.
        hp_egress = self._lookup_table[PktOut][ingress_rate][pkt_out_rate]
        if hp_egress == np.nan:
            return True
        return random.random() < hp_egress / egress_delivered / pkt_out_rate    
    
        
        


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
    import code
    z = load_lookup_table('hp-full-frame.csv', 0, 2, 5)
    code.interact(banner='Panda!', local=locals())
    return
    
    print 'With limiter:'
    test_run(with_limiter=True)

    print 'Without limiter:'
    test_run(with_limiter=False)













if __name__ == '__main__':
    test()
    
    
    
    