"""
Controller that helps to profile the interactions between OF commands and OF
switches. Works for only two switch ports.

Written by: Danny Y. Huang

"""
from pox.core import core
import pox.openflow.libopenflow_01 as of
from pox.lib.revent import *
from pox.lib.util import dpidToStr
from pox.lib.util import str_to_bool
import os, time, threading, socket, traceback, sys, datetime



SWITCH_PORT_LIST = [32, 34]
LOG_FILE = 'of_profiler.log'


def get_the_other_port(this_port):
    
    assert this_port in SWITCH_PORT_LIST and len(SWITCH_PORT_LIST) == 2
    
    port_list = SWITCH_PORT_LIST[:]
    port_list.remove(this_port)
    return port_list[0]
    


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
        
        with self.lock:
            self.learning = True
            self.pkt_in_count = 0
            self.pkt_out_count = 0        

        
    
    def _accept_loop(self):
        
        while True:
            (conn, addr) = self.server_sock.accept()
            conn_thread = threading.Thread(target=self._handle_connection,
                                           args=(conn, addr))
            conn_thread.daemon = True
            conn_thread.start()
            
    
    
    def _handle_connection(self, conn, addr):
        
        try:
            mylog('ExpControl accepted connection:', addr)
            while True:
                cmd = ''
                while not cmd.endswith('\n\n'):
                    data = conn.recv(4096)
                    if data:
                        cmd += data
                    else:
                        mylog('Connection closed:', addr)
                        return
                result = repr(self._handle_command(cmd))
                conn.sendall(result + '\n\n')                
                mylog('ExpControl command:', cmd.strip(), '->', result)

        except:
            mylog('ExpControl', addr, 'crashed:', traceback.format_exc())
            print >> sys.stderr, '\n' * 80, 'ExpControl crashed:', traceback.format_exc()
            
            
            
    def _handle_command(self, cmd):
        """ Command and arguments are space-separated. """
        
        try:
            (cmd, arg) = cmd.split(' ', 1)
        except ValueError:
            arg = ''
        
        cmd = cmd.strip()
        arg = arg.strip()
        
        if cmd == 'GET':
            with self.lock:
                return getattr(self, arg)
        
        if cmd == 'SET':
            (attr, value) = arg.split(' ', 1)
            with self.lock: 
                setattr(self, attr, eval(value))
            return 'OK'
        
        if cmd == 'GETALL':
            with self.lock:
                return self.__dict__
            
        if cmd == 'RESET':
            self._init_state()
            return 'OK'
        
        raise Exception('Bad command: ' + repr(cmd))
            




exp_control = ExpControl()







#===============================================================================
# Modified 'Learning' Switch
#===============================================================================



class LearningSwitch (EventMixin):


    
    def __init__ (self, connection, transparent):
        
        # Switch we'll be adding L2 learning switch capabilities to
        self.connection = connection
        self.transparent = transparent

        # We want to hear PacketIn messages, so we listen
        self.listenTo(connection)

        
        

    def _handle_PacketIn (self, event):
        """
        Handles packet in messages from the switch to implement above algorithm.
        """
        packet = event.parse()

        def packet_out ():
            """ Floods the packet """
            if event.ofp.buffer_id == -1:
                mylog("Not flooding unbuffered packet on", dpidToStr(event.dpid))
                return
            msg = of.ofp_packet_out()            
            msg.actions.append(of.ofp_action_output(port=get_the_other_port(event.port)))
            msg.buffer_id = event.ofp.buffer_id
            msg.in_port = event.port
            self.connection.send(msg)


        def drop():
            if event.ofp.buffer_id != -1:
                msg = of.ofp_packet_out()
                msg.buffer_id = event.ofp.buffer_id
                msg.in_port = event.port
                self.connection.send(msg)
        
        # End of inline functions. 
        
        # Now sanity check to make sure we're dealing with the two relevant
        # ports only.
        
        if not self.transparent:
            if packet.type == packet.LLDP_TYPE or packet.dst.isBridgeFiltered():
                drop()
                return

        if event.port not in SWITCH_PORT_LIST:
            drop()
            return

        if packet.dst.isMulticast():
            packet_out() 
            return

        # End of sanity check. The packet-in is relevant.

        with exp_control.lock:
            learning_switch = exp_control.learning
            exp_control.pkt_in_count += 1
        
        if not learning_switch:
            with exp_control.lock:
                exp_control.pkt_out_count += 1
            drop()
            return
        
        outport = get_the_other_port(event.port)        
        if outport == event.port: 
            mylog("Same port for packet from %s -> %s on %s. Drop." %
                  (packet.src, packet.dst, outport), dpidToStr(event.dpid))
            drop()
            return
        
        # Finally, passed sanity checks. Install the rule.
        
        mylog("installing flow for %s.%i -> %s.%i" %
              (packet.src, event.port, packet.dst, outport))
        
        msg = of.ofp_flow_mod()
        msg.match = of.ofp_match.from_packet(packet)
        msg.idle_timeout = 200
        msg.hard_timeout = 300
        msg.actions.append(of.ofp_action_output(port=outport))
        msg.buffer_id = event.ofp.buffer_id 
        self.connection.send(msg)




class l2_learning (EventMixin):
    """
    Waits for OpenFlow switches to connect and makes them learning switches.
    """
    def __init__ (self, transparent):
        self.listenTo(core.openflow)
        self.transparent = transparent

    def _handle_ConnectionUp (self, event):
        LearningSwitch(event.connection, self.transparent)





def launch (transparent=False):
    """
    Starts an L2 learning switch.
    """
    core.registerNew(l2_learning, str_to_bool(transparent))


