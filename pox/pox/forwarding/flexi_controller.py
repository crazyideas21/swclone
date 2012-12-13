"""
Controller that helps to profile the interactions between OF commands and OF
switches. Works for only two switch ports.

Arguments: --of_port_1 [OF Port 1] --of_port_2 [OF Port 2].

Sample invocation at command line:
~/swclone/pox# python pox.py --no-cli openflow.of_01 --port=45678 forwarding.flexi_controller --of_port_1=32 --of_port_2=34

Written by: Danny Y. Huang

Nov 14, 2012

"""
from pox.core import core
import pox.openflow.libopenflow_01 as of
from pox.lib.revent import *
from pox.lib.util import dpidToStr
from pox.lib.util import str_to_bool
import time, random, traceback, threading, re
from lib.util import dictify, Logger, func_cache, pretty_dict, run_ssh
from lib.state_proxy import StateProxyServer
from lib.looper import Looper
import subprocess



mylog = Logger('flexi_controller.log')

SWITCH_PORT_LIST = []
IDLE_TIMEOUT = 10  # Default: 10
HARD_TIMEOUT = 30  # Default: 30

# If a pkt arrives with the following dst port, it is saved for subsequent use.
TRIGGER_PORT = 32767

USE_LIMITER = False # Default: False
if USE_LIMITER:
    from lib.limiter import DynamicLimiter, Limiter

FLOW_TABLE_FILE = 'flow_table.repr'



def get_the_other_port(this_port):
    
    assert this_port in SWITCH_PORT_LIST and len(SWITCH_PORT_LIST) == 2
    
    port_list = SWITCH_PORT_LIST[:]
    port_list.remove(this_port)
    return port_list[0]
    








#===============================================================================
# Modified 'Learning' Switch
#===============================================================================




class LearningSwitch (EventMixin):


    
    def __init__ (self, connection, transparent):
        
        self.lock = threading.Lock()
        
        # To make sure only one thread is using the socket.
        self.socket_lock = threading.Lock()

        # Switch we'll be adding L2 learning switch capabilities to
        self.connection = connection
        self.transparent = transparent

        # We want to hear PacketIn messages, as well as flow-stat messages.
        self.listenTo(connection)
        core.openflow.addListenerByName("FlowStatsReceived", self.handle_flow_stats)

        # Initialize internal state.
        self.reset()
        
        # Constantly checks for table stats.
        stat_t = threading.Thread(target=self.flow_stat_thread)
        stat_t.daemon = True
        stat_t.start()

        # To allow the experiment's main program to access all the internal
        # state of this controller.
        StateProxyServer(self, self.lock, self.reset).start()
        
        
        

    def reset(self):
        
        self.lock.acquire()

        if USE_LIMITER:
            self.flow_mod_limiter = Limiter(50)
            self.dyn_limiter = DynamicLimiter()
        
        # OF event stats, in the form of (pkt_count, start_time, end_time).        
        self.pkt_in_stat = (0, None, None)
        self.flow_mod_stat = (0, None, None)
        self.pkt_out_stat = (0, None, None)

        # Maps time at which switch is polled for stats to flow_count.
        self.flow_stat_interval = 5
        self.flow_count_dict = {} 
        
        # A special packet that "triggers" the special operations. Subsequent
        # special flow-mod or pkt-out operations will match against this packet.
        self.trigger_event = None

        # How long should our garbage pkt-out packets be?
        self.pkt_out_length = 1500
        
        self.lock.release()
        
        
        

    def _of_send(self, msg):
        """ Sends OpenFlow message, thread-safe. """
        with self.socket_lock:
            self.connection.send(msg)
             





    def _drop(self, event):
        if event.ofp.buffer_id != -1:
            msg = of.ofp_packet_out()
            msg.buffer_id = event.ofp.buffer_id
            msg.in_port = event.port
            self._of_send(msg)



    def _is_relevant_packet(self, event, packet):
        """ 
        Sanity check to make sure we deal with experimental traffic only.
        Otherwise, returns False.
        
        """        
        mylog('zzzz inport =', event.port)
        
        if not self.transparent:
            if packet.type == packet.LLDP_TYPE or packet.dst.isBridgeFiltered():
                mylog('pkt_in: Rejected packet LLDP or BridgeFiltered:', packet, repr(packet), dictify(packet))
                self._drop(event)
                return False

        if event.port not in SWITCH_PORT_LIST:
            mylog('pkt_in: Rejected packet: invalid port', packet, repr(packet), dictify(packet))
            self._drop(event)
            return False

        if packet.dst.isMulticast():
            self.do_pkt_out(event) 
            return False
                
        return True
    
    
        

    def handle_flow_stats(self, event):
        """
        Each flow in event.stats has the following properties if recursively
        dictified:
        
        {'priority': 32768, 'hard_timeout': 30, 'byte_count': 74, 'length': 96,
        'actions': [<pox.openflow.libopenflow_01.ofp_action_output object at
        0x7f1420685350>], 'duration_nsec': 14000000, 'packet_count': 1,
        'duration_sec': 0, 'table_id': 0, 'match': {'_nw_proto': 6, 'wildcards': 1,
        '_dl_type': 2048, '_dl_dst': {'_value': '\x00\x19\xb9\xf8\xea\xf8'},
        '_nw_src': {'_value': 17449482}, '_tp_dst': 58811, '_dl_vlan_pcp': 0,
        '_dl_vlan': 65535, '_in_port': 0, '_nw_dst': {'_value': 17318410},
        '_dl_src': {'_value': '\x00\x19\xb9\xf9-\xe2'}, '_nw_tos': 0, '_tp_src':
        5001}, 'cookie': 0, 'idle_timeout': 10}
        
        nw_proto = 17 ==> UDP
        nw_proto = 6 ==> TCP
        
        Adds time->flow_count into the flow_count dictionary.
        
        """
        flow_count_list = [len([f for f in event.stats if f.table_id == i]) \
                           for i in [0,1,2]]
        mylog('flow_count_list =', flow_count_list)
        with self.lock:
            self.flow_count_dict[time.time()] = flow_count_list[0]
            (flow_mod_count, _, _) = self.flow_mod_stat

        # Find how many rules were promoted.        
        current_hw_table = set([(f.match._tp_src, f.match._tp_dst) for f in event.stats if f.table_id == 0])
        current_sw_table = set([(f.match._tp_src, f.match._tp_dst) for f in event.stats if f.table_id == 2])
        if not hasattr(self, 'prev_sw_table'):
            self.prev_sw_table = set()
        promoted_set = self.prev_sw_table & current_hw_table
        self.prev_sw_table = current_sw_table 
        
        # Find how many packets sent/received on eth1
        sender_output = run_ssh('ifconfig eth1', hostname='172.22.14.208', stdout=subprocess.PIPE, stderr=subprocess.PIPE, verbose=False).communicate()[0]
        sent_KB = int(re.search('TX bytes:(\d+)', sender_output).group(1)) / 1000
        receiver_output = run_ssh('ifconfig eth1', hostname='172.22.14.207', stdout=subprocess.PIPE, stderr=subprocess.PIPE, verbose=False).communicate()[0]
        received_KB = int(re.search('RX bytes:(\d+)', receiver_output).group(1)) / 1000

        # Print space-separated result
        print time.time(), len(current_hw_table), len(current_sw_table), len(promoted_set), sent_KB, flow_mod_count, received_KB

#        # Also write all the flow entries to file.
#        flow_entries = [(time.time(), f.table_id, f.match._tp_src, f.match._tp_dst, flow_mod_count) for f in event.stats]
#        with open(FLOW_TABLE_FILE, 'a') as table_f:
#            print >> table_f, repr(flow_entries)



    def flow_stat_thread(self):

        while True:

            self._of_send(of.ofp_stats_request(body=of.ofp_flow_stats_request()))
            
            sleep_time = 0
            while True:
                time.sleep(2)
                sleep_time += 2
                with self.lock:
                    if sleep_time >= self.flow_stat_interval:
                        break
            


#===============================================================================
# PACKET HANDLERS
#===============================================================================



    def _handle_PacketIn(self, event):
        """
        Handles packet in messages from the switch to implement above algorithm.
        """
        try:
            return self._handle_pkt_in_helper(event)
        except Exception:
            mylog('*' * 80)
            mylog('Pkt_in crashed:', traceback.format_exc())
            
            
        
        
    def _handle_pkt_in_helper(self, event):
        
        packet = event.parse()
        current_time = time.time() 
                            
        # There are just packets that we don't care about.
        if not self._is_relevant_packet(event, packet):
            return

        # Count packet-in events only if they're from the pktgen.
        match = of.ofp_match.from_packet(packet)
        if (not USE_LIMITER) or (USE_LIMITER and self.dyn_limiter.to_forward_packet(DynamicLimiter.PacketType.PktIn)):
            if match.tp_src == 10000 and match.tp_dst == 9:
                with self.lock:
                    (count, start, _) = self.pkt_in_stat
                    if start is None: start = current_time
                    self.pkt_in_stat = (count + 1, start, current_time)
                
        # Learn the packet as per normal if there are no trigger events saved.
        with self.lock:
            no_trigger_event = self.trigger_event is None
        if no_trigger_event:
            self.do_flow_mod(event)


        
        
    def do_flow_mod(self, event=None):
        """
        If the event is not specified, then issues a flow mod with random src
        and dst ports; all the other fields will match against the trigger event
        saved earlier. Does not issue pkt_out.
        
        Otherwise, does a normal flow_mod.
        
        """
        msg = of.ofp_flow_mod()

        # Normal flow-mod
        if event:
            msg.match = of.ofp_match.from_packet(event.parse())
            msg.actions.append(of.ofp_action_output(port=get_the_other_port(event.port)))
            msg.buffer_id = event.ofp.buffer_id
            
            # Save the trigger event for later matching.
            if msg.match.tp_dst == TRIGGER_PORT:
                with self.lock:
                    self.trigger_event = event
                mylog('Received trigger event. Trigger event.parse() =', pretty_dict(dictify(event.parse())))
            
            mylog('Installed flow:', pretty_dict(dictify(msg.match)))
            
        # Special flow-mod that generates random source/dst ports.
        else:
            with self.lock:
                assert self.trigger_event
                trigger_packet = func_cache(self.trigger_event.parse)
                msg.match = of.ofp_match.from_packet(trigger_packet)
                msg.actions.append(of.ofp_action_output(port=get_the_other_port(self.trigger_event.port)))
            msg.match.tp_dst = random.randint(10, 65000)
            msg.match.tp_src = random.randint(10, 65000)

            
        current_time = time.time()
        with self.lock:
            (count, start, _) = self.flow_mod_stat
            if start is None: start = current_time
            self.flow_mod_stat = (count + 1, start, current_time)

        msg.idle_timeout = IDLE_TIMEOUT
        msg.hard_timeout = HARD_TIMEOUT

        if (not USE_LIMITER) or (USE_LIMITER and self.flow_mod_limiter.to_forward_packet()):
            self._of_send(msg)
        




    def do_pkt_out(self, event=None):

        msg = of.ofp_packet_out()            
        
        # Normal pkt-out
        if event:
            if event.ofp.buffer_id == -1:
                mylog("Not flooding unbuffered packet on", dpidToStr(event.dpid))
                return
            msg.actions.append(of.ofp_action_output(port=get_the_other_port(event.port)))
            msg.buffer_id = event.ofp.buffer_id
            msg.in_port = event.port
            mylog('Normal packet-out: ', msg)
            
        # Special pkt-out that generates a packet that is exactly the same as
        # the trigger packet. Unfortunately, only 114 bytes of the original
        # ingress packet are forwarded into the controller as pkt-in. We need to
        # make up for the truncated length, if needed. The checksum will be
        # wrong, but screw that.
        else:
            raw_data = func_cache(self.trigger_event.parse).raw
            if len(raw_data) < self.pkt_out_length:
                raw_data += 'z' * (self.pkt_out_length - len(raw_data))
            msg._data = raw_data
            msg.buffer_id = -1
            with self.lock:
                assert self.trigger_event
                msg.actions.append(of.ofp_action_output(port=get_the_other_port(self.trigger_event.port)))
                msg.in_port = self.trigger_event.port

            # Stat collection for special pkt-out only.
            current_time = time.time()
            with self.lock:
                (count, start, _) = self.pkt_out_stat
                if start is None: start = current_time
                self.pkt_out_stat = (count + 1, start, current_time)
        
        if (not USE_LIMITER) or (USE_LIMITER and self.dyn_limiter.to_forward_packet(DynamicLimiter.PacketType.PktOut)):
            self._of_send(msg)        
        







#===============================================================================
# LOOPERS
#===============================================================================

    def trigger_event_is_ready(self):
        with self.lock:
            return self.trigger_event is not None

    def start_loop_flow_mod(self, interval, max_run_time):
        self._flow_mod_looper = Looper(self.do_flow_mod, interval, max_run_time)
        self._flow_mod_looper.start()
        
    def stop_loop_flow_mod(self):
        self._flow_mod_looper.stop()
        
    def start_loop_pkt_out(self, interval, max_run_time):
        self._pkt_out_looper = Looper(self.do_pkt_out, interval, max_run_time)
        self._pkt_out_looper.start()
        
    def stop_loop_pkt_out(self):
        self._pkt_out_looper.stop()
    



class l2_learning (EventMixin):
    """
    Waits for OpenFlow switches to connect and makes them learning switches.
    """
    def __init__ (self, transparent):
        self.listenTo(core.openflow)
        self.transparent = transparent

    def _handle_ConnectionUp (self, event):
        LearningSwitch(event.connection, self.transparent)









def launch (transparent=False, of_port_1='32', of_port_2='34', rate_limit=False):
    """
    Starts an L2 learning switch.
    """
    SWITCH_PORT_LIST.append(int(of_port_1))
    SWITCH_PORT_LIST.append(int(of_port_2))
    
    global USE_LIMITER
    USE_LIMITER = rate_limit
    
    core.registerNew(l2_learning, str_to_bool(transparent))
    

