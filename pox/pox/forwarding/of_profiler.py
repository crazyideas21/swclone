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
import os, time, threading



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
        print >> f, log_str







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
        
        # End of inline. Now sanity check to make sure we're dealing with the
        # two relevant ports only.
        
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


