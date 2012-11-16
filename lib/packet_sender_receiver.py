'''
Defines the interface for packet senders and receivers.

Created on Nov 14, 2012

@author: Danny Y. Huang

'''
import time

class StateController:
    """ Any object that can be started and stopped. """
    
    def __init__(self):
        self._start_time = None
        self._stop_time = None
    
    def start(self):
        self._start_time = time.time()
        
    def stop(self):
        self._stop_time = time.time()
        
    def get_running_time(self):
        return self._stop_time - self._start_time



class PacketSender(StateController):
    """ Base class for any packet senders. """
        
    def __init__(self, expected_pps):
        self._expected_pps = expected_pps
        self._sent_count = None
        StateController.__init__(self)
    
    def get_sent_pps(self):
        return self._sent_count / self.get_running_time()



class PacketReceiver(StateController):
    """ Base class for any packet receivers. """
    
    def __init__(self):
        self._recvd_count = None
        StateController.__init__(self)
        
    def get_received_pps(self):
        return self._recvd_count / self.get_running_time()
        
