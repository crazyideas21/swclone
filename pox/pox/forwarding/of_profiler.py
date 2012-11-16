"""
Controller that helps to profile the interactions between OF commands and OF
switches. Works for only two switch ports.

Arguments: --of_port_1 [OF Port 1] --of_port_2 [OF Port 2].

Sample invocation at command line:
~/swclone/pox# python pox.py --no-cli openflow.of_01 --port=45678 forwarding.of_profiler --of_port_1=32 --of_port_2=34

Written by: Danny Y. Huang

"""
from pox.core import core
import pox.openflow.libopenflow_01 as of
from pox.lib.revent import *
from pox.lib.util import dpidToStr
from pox.lib.util import str_to_bool
from pox.lib.addresses import EthAddr
from pox.forwarding.of_profiler_control import ExpControl, mylog
import time, random, traceback
from lib.util import dictify, pretty_dict
from lib.limiter import Limiter



SWITCH_PORT_LIST = []
IDLE_TIMEOUT = 10  # Default: 10
HARD_TIMEOUT = 30  # Default: 30


def get_the_other_port(this_port):
    
    assert this_port in SWITCH_PORT_LIST and len(SWITCH_PORT_LIST) == 2
    
    port_list = SWITCH_PORT_LIST[:]
    port_list.remove(this_port)
    return port_list[0]
    




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

        # When was the last time we asked the switch about its flow table?
        self.last_flow_stat_time = 0
        
        # Throttle pkt_in and flow_mod events.
        self.limiter_pkt_in = Limiter(100)
        self.limiter_flow_mod = Limiter(50)
        self.limiter_pkt_out = Limiter(50)
        
        


    def _packet_out(self, event):
        """ Floods the packet """
        if event.ofp.buffer_id == -1:
            mylog("Not flooding unbuffered packet on", dpidToStr(event.dpid))
            return
        msg = of.ofp_packet_out()            
        msg.actions.append(of.ofp_action_output(port=get_the_other_port(event.port)))
        msg.buffer_id = event.ofp.buffer_id
        msg.in_port = event.port
        self.connection.send(msg)



    def _drop(self, event):
        if event.ofp.buffer_id != -1:
            msg = of.ofp_packet_out()
            msg.buffer_id = event.ofp.buffer_id
            msg.in_port = event.port
            self.connection.send(msg)



    def _is_relevant_packet(self, event, packet):
        """ 
        Sanity check to make sure we deal with experimental traffic only.
        Otherwise, returns False.
        
        """        
        mylog('zzzz inport =', event.port)
        
        
        
        if not self.transparent:
            if packet.type == packet.LLDP_TYPE or packet.dst.isBridgeFiltered():
                self._drop(event)
                return False

        if event.port not in SWITCH_PORT_LIST:
            self._drop(event)
            return False

        if packet.dst.isMulticast():
            self._packet_out(event) 
            return False
        
        outport = get_the_other_port(event.port)
        
        if outport == event.port: 
            mylog("Same port for packet from %s -> %s on %s. Drop." %
                  (packet.src, packet.dst, outport), dpidToStr(event.dpid))
            self._drop(event)
            return False
        
        return True
        



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
                
        with exp_control.lock:
            flow_stat_interval = exp_control.flow_stat_interval       
        
        # Obtain flow stats once in a while.                
        if flow_stat_interval:     
            if current_time - self.last_flow_stat_time > flow_stat_interval:
                self.last_flow_stat_time = current_time
                self.connection.send(of.ofp_stats_request(body=of.ofp_flow_stats_request()))
            
        # There are just packets that we don't care.
        if not self._is_relevant_packet(event, packet):
            mylog('pkt_in: Rejected packet:', packet, repr(packet), dictify(packet))
            return

        # Throttle packet-in events if need be.
        if exp_control.emulate_hp_switch:
            if not self.limiter_pkt_in.to_forward_packet():
                return

        # Count packet-in events.
        with exp_control.lock:
            learning_switch = exp_control.learning
            exp_control.pkt_in_count += 1
            if exp_control.pkt_in_start_time is None:
                exp_control.pkt_in_start_time = current_time
            exp_control.pkt_in_end_time = current_time
        
        # Count number of packet-out events if the switch does not install
        # rules.
        if not learning_switch:
            with exp_control.lock:
                exp_control.pkt_out_count += 1
            self._drop(event)
            return
        
        outport = get_the_other_port(event.port)        
        
        # Throttle flow-mod events and pkt-out events if need be.
        if exp_control.emulate_hp_switch:
            if self.limiter_flow_mod.to_forward_packet():
                # flow-mod and pkt-out at 50 pps
                pass
            else:
                # pkt-out at 50 pps, so regardless, total pkt-out at 100 pps
                if self.limiter_pkt_out.to_forward_packet():
                    self._packet_out(event)
                return
        
        # Automatically learns new flows, as a normal learning switch would do.
        if exp_control.auto_install_rules:
            self._install_rule(event, packet, outport)            
            return
        
        # Manually install rules in the port range.
        with exp_control.lock:
            tp_dst_range = exp_control.manual_install_tp_dst_range[:]
            gap_ms = exp_control.manual_install_gap_ms
                    
        for tp_dst in range(*tp_dst_range):
                        
            # Keep going until the exp_control client decides to stop it.
            with exp_control.lock:
                manual_active = exp_control.manual_install_active
            if not manual_active:
                break

            self._install_rule(event, packet, outport, tp_dst)
            time.sleep(gap_ms / 1000.0)
            

        
    def _install_rule(self, event, packet, outport, tp_dst=None, idle_timeout=IDLE_TIMEOUT):
        """
        Installs a rule for any incoming packet, doing what a learning switch
        should do.
        
        """                
        msg = of.ofp_flow_mod()
        msg.match = of.ofp_match.from_packet(packet)
        msg.idle_timeout = idle_timeout
        msg.hard_timeout = HARD_TIMEOUT
        msg.actions.append(of.ofp_action_output(port=outport))

        with exp_control.lock:
            exp_control.flow_mod_count += 1
            install_bogus_rules = exp_control.install_bogus_rules

        # Install a rule with a randomly generated dest mac address that no
        # one will ever match against.
        if install_bogus_rules:
            #mac_addr_list = ['0' + str(random.randint(1,9)) for _ in range(6)]
            #msg.match.dl_src = EthAddr(':'.join(mac_addr_list))
            msg.match.tp_dst = random.randint(10, 65000)
            msg.match.tp_src = random.randint(10, 65000)
            msg.buffer_id = event.ofp.buffer_id
            mylog('Installing a bogus flow.')

        # Create a rule that matches with the incoming packet. When buffer ID is
        # specified, the flow mod command is automatically followed by a packet-
        # out command.
        elif tp_dst is None:
            msg.buffer_id = event.ofp.buffer_id
            with exp_control.lock:
                exp_control.pkt_out_count += 1
            mylog("installing flow for %s.%i -> %s.%i" %
                   (packet.src, event.port, packet.dst, outport))
            
        # Create a rule with a specific dest port.        
        else: 
            msg.match.tp_dst = tp_dst
            mylog('Installing rule for tp_dst =', tp_dst)
        
        current_time = time.time()        
        with exp_control.lock:
            if exp_control.flow_mod_start_time is None:
                exp_control.flow_mod_start_time = current_time
            exp_control.flow_mod_end_time = current_time  
        
        mylog('Flow_mod:', pretty_dict(dictify(msg)))
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




def handle_flow_stats (event):
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
    
    Adds time->flow_count into the flow_count dictionary.
    
    """
    flow_count_0 = len([f for f in event.stats if f.table_id == 0])
#    flow_count_1 = len([f for f in event.stats if f.table_id == 1])
#    flow_count_2 = len([f for f in event.stats if f.table_id == 2])
    with exp_control.lock:
        exp_control.flow_count_dict[time.time()] = flow_count_0





def launch (transparent=False, of_port_1='32', of_port_2='34'):
    """
    Starts an L2 learning switch.
    """
    SWITCH_PORT_LIST.append(int(of_port_1))
    SWITCH_PORT_LIST.append(int(of_port_2))
    
    core.registerNew(l2_learning, str_to_bool(transparent))
    core.openflow.addListenerByName("FlowStatsReceived", handle_flow_stats)

