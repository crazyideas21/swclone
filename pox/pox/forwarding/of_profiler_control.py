'''
Provides a way through which external processes can interact with the OF
profiler.

Created on Aug 28, 2012

@author: danny
'''
import os, time, datetime, threading, socket, traceback, sys
from lib.session_sock import SessionSocket, ConnectionClosed

LOG_FILE = 'of_profiler.log'

if os.path.isfile(LOG_FILE):
    os.remove(LOG_FILE)
base_time = time.time()



def mylog(*log_str_args):

    log_str_args = [str(e) for e in log_str_args]
    log_str = ' '.join(log_str_args)

    with open(LOG_FILE, 'a') as f:
        print >> f, '%.3f' % (time.time() - base_time),
        print >> f, datetime.datetime.today().strftime('%m-%d %H:%M:%S'), 
        print >> f, '>', log_str




#===============================================================================
# Experiment Controller
#===============================================================================



class ExpControl:
    """ 
    Listens for commands that sets the learning switch state and gathers its
    statistics.
    
    """
    
    def __init__(self):
        
        self.lock = threading.Lock()
        self._init_state()
        
        self.server_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.server_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.server_sock.bind(('0.0.0.0', 16633))
        self.server_sock.listen(5)
        
        server_thread = threading.Thread(target=self._accept_loop)
        server_thread.daemon = True
        server_thread.start()
        


    def _init_state(self):
        """ Experiment state and statisitics. """

        self.lock.acquire()
        
        self.learning = True
        
        self.pkt_in_count = 0
        self.flow_mod_count = 0
        self.pkt_out_count = 0        

        self.pkt_in_start_time = None
        self.pkt_in_end_time = None
        
        self.flow_mod_start_time = None
        self.flow_mod_end_time = None

        self.flow_stat_interval = 0
        self.flow_count_dict = {} # time -> flow_count

        self.auto_install_rules = True
        self.manual_install_active = False
        self.manual_install_gap_ms = 1
        self.manual_install_tp_dst_range = [0, 65530]
    
        self.install_bogus_rules = False
        
        self.emulate_hp_switch = False
        
        self.lock.release()
        

    
    def _accept_loop(self):
        
        while True:
            (conn, addr) = self.server_sock.accept()
            conn = SessionSocket(conn)
            conn_thread = threading.Thread(target=self._handle_connection,
                                           args=(conn, addr))
            conn_thread.daemon = True
            conn_thread.start()
            
    
    
    def _handle_connection(self, conn, addr):
        
        try:
            mylog('ExpControl accepted connection:', addr)
            while True:
                try:
                    cmd = conn.recv()
                except ConnectionClosed:
                    mylog('Connection closed:', addr)
                    return
                result = self._handle_command(cmd)
                conn.send(result)
                mylog('ExpControl command:', cmd, '->', result)

        except:
            mylog('ExpControl', addr, 'crashed:', traceback.format_exc())
            print >> sys.stderr, '\n' * 80, 'ExpControl crashed:', traceback.format_exc()
            
            
            
    def _handle_command(self, cmd):
        """ Command and arguments are space-separated. """
                
        if cmd[0] == 'GET':
            with self.lock:
                return getattr(self, cmd[1])
        
        if cmd[0] == 'SET':
            with self.lock: 
                setattr(self, cmd[1], cmd[2])
            return 'OK'
        
        if cmd[0] == 'GETALL':
            with self.lock:
                return self.__dict__
            
        if cmd[0] == 'RESET':
            self._init_state()
            return 'OK'
        
        raise Exception('Bad command: ' + repr(cmd))
            



