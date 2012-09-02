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
from pox.forwarding.of_profiler_control import ExpControl, mylog
import time



SWITCH_PORT_LIST = [32, 34]



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
        packet = event.parse()
        
        if not self._is_relevant_packet(event, packet):
            return

        # Count packet-in events.
        with exp_control.lock:
            learning_switch = exp_control.learning
            exp_control.pkt_in_count += 1
        
        # Count number of packet-out events if the switch does not install
        # rules.
        if not learning_switch:
            with exp_control.lock:
                exp_control.pkt_out_count += 1
            self._drop(event)
            return
        
        outport = get_the_other_port(event.port)        
        
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
            

        
    def _install_rule(self, event, packet, outport, tp_dst=None, idle_timeout=0):
        """
        Installs a rule for any incoming packet, doing what a learning switch
        should do.
        
        """                
        msg = of.ofp_flow_mod()
        msg.match = of.ofp_match.from_packet(packet)
        msg.idle_timeout = idle_timeout
        msg.hard_timeout = 0
        msg.actions.append(of.ofp_action_output(port=outport))

        with exp_control.lock:
            exp_control.flow_mod_count += 1

        # When buffer ID is specified, the flow mod command is automatically
        # followed by a packet-out command.                
        if tp_dst is None:
            msg.buffer_id = event.ofp.buffer_id
            with exp_control.lock:
                exp_control.pkt_out_count += 1
            mylog("installing flow for %s.%i -> %s.%i" %
                   (packet.src, event.port, packet.dst, outport))
        else: 
            msg.match.tp_dst = tp_dst
            mylog('Installing rule for tp_dst =', tp_dst)
        
        current_time = time.time()
        
        with exp_control.lock:
            if exp_control.flow_mod_start_time is None:
                exp_control.flow_mod_start_time = current_time
            exp_control.flow_mod_end_time = current_time  
        
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


