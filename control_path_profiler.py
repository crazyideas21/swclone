"""
Profiles the entire control path. In particular:

* ingress pkt rate vs pkt_in rate
* flow_mod rate vs successful rule installation rate
* pkt_out rate vs egress pkt rate

Each of these tests are modularized. They can be permutated arbitrarily to
simulate emergent behaviors.

Written by: Danny Y. Huang

Nov 14, 2012

"""
from lib.packet_sender_receiver import PacketSender, PacketReceiver
from lib.switch import Switch
from lib.pktgen import Pktgen
from lib.tcpdump import Tcpdump
from lib.state_proxy import StateProxyClient
import lib.config as config
import lib.util as util
import time



MAX_RUNNING_TIME = 300
TRIGGER_PORT = 32767

FLEXI_CONTROLLER_HOST = '132.239.17.35'


def send_trigger_packet(length):
    """ 
    Sends a reference packet to the controller, from which flow-mods or pkt-outs
    can be constructed. Blocks until the packet is sent.
    
    """
    util.run_ssh('iperf -u -c ', config.active_config.dest_ip, 
                 ' -p ', TRIGGER_PORT, ' -t 2 -l ', length,  
                 verbose=True, 
                 hostname=config.active_config.source_ip).wait()
    

def start_controller():
    """ Returns a Popen object. """
    
    cmd = ['export PYTHONPATH="/home/danny/swclone:/home/danny/swclone/lib";',
           'cd ~/swclone;',
           'python pox/pox.py --no-cli openflow.of_01 --port=45678 forwarding.flexi_controller --of_port_1=32 --of_port_2=34;'
           ]
    
    return util.run_ssh(*cmd, verbose=True, hostname=FLEXI_CONTROLLER_HOST, user='danny')





class GenerateIngress(PacketSender):
    
    def __init__(self, expected_pps, _, packet_size=1400):
        self._pktgen = Pktgen(config.active_config)
        self._pkt_size = packet_size
        self._sent_pps = None
        PacketSender.__init__(self, expected_pps)
        
    def start(self):
        gap = 1.0 / self._expected_pps
        gap_ns = gap * 1000 * 1000 * 1000
        max_pkt_count = int(MAX_RUNNING_TIME * self._expected_pps)
        self._pktgen.low_level_start(pkt_count=max_pkt_count, 
                                     pkt_size=self._pkt_size, 
                                     gap_ns=gap_ns, flow_count=1)
        PacketSender.start(self)
        
    def stop(self):
        pktgen_result = self._pktgen.stop_and_get_result()
        self._sent_pps = pktgen_result.sent_pkt_count / pktgen_result.running_time
        PacketSender.stop(self)

    def get_sent_pps(self):
        return self._sent_pps



class ReceivePktIn(PacketReceiver):
    
    def __init__(self, state_proxy_client):
        PacketReceiver.__init__(self)
        self._proxy_client = state_proxy_client
        self._pkt_in_pps = None
        
    def start(self):
        self._proxy_client.set('pkt_in_stat', (0, None, None))
        PacketReceiver.start(self)
        
    def stop(self):
        (self._recvd_count, start, end) = self._proxy_client.get('pkt_in_stat')
        self._pkt_in_pps = self._recvd_count / (end - start)
        PacketReceiver.stop(self)
        
    def get_received_pps(self):
        return self._pkt_in_pps
        
        
        


class GenerateFlowMod(PacketSender):

    def __init__(self, expected_pps, state_proxy_client, packet_size=None):
        PacketSender.__init__(self, expected_pps)
        self._proxy_client = state_proxy_client
        self._flow_mod_pps = None
        
    def start(self):
        assert self._proxy_client.run('trigger_event_is_ready') 
        self._proxy_client.set('flow_mod_stat', (0, None, None))
        self._proxy_client.run('start_loop_flow_mod', 1.0/self._expected_pps, MAX_RUNNING_TIME)
        PacketSender.start(self)
        
    def stop(self):
        self._proxy_client.run('stop_loop_flow_mod')
        (self._sent_count, start, end) = self._proxy_client.get('flow_mod_stat')
        self._flow_mod_pps = self._sent_count / (end - start)
        PacketSender.stop(self)

    def get_sent_pps(self):
        return self._flow_mod_pps





class CheckRuleInstallationRate(PacketReceiver):
    
    def __init__(self, state_proxy_client, flow_stat_interval=20, steady_state_start=60, steady_state_end=120):
        PacketReceiver.__init__(self)
        self._proxy_client = state_proxy_client
        self._flow_stat_interval = flow_stat_interval
        self._steady_state_start = steady_state_start
        self._steady_state_end = steady_state_end
        
    def start(self):
        self._proxy_client.set('flow_stat_interval', self._flow_stat_interval)
        self._proxy_client.set('flow_count_dict', {})
        PacketReceiver.start(self)

    def get_received_pps(self):
        """ Returns the average rate of successful flow_mod at steady state """
        flow_count_dict = self._proxy_client.get('flow_count_dict')
        steady_flow_count_list = []
        steady_time_start = min(flow_count_dict.keys()) + self._steady_state_start
        steady_time_end = min(flow_count_dict.keys()) + self._steady_state_end
        for stat_time in flow_count_dict:
            if steady_time_start <= stat_time <= steady_time_end:
                steady_flow_count_list.append(flow_count_dict[stat_time])
        return sum(steady_flow_count_list) / 10.0 / len(steady_flow_count_list)
        
        





class GeneratePktOut(PacketSender):

    def __init__(self, expected_pps, state_proxy_client, packet_size=1500):
        PacketSender.__init__(self, expected_pps)
        self._proxy_client = state_proxy_client
        self._pkt_size = packet_size
        self._pkt_out_pps = None
        
    def start(self):
        assert self._proxy_client.run('trigger_event_is_ready') 
        self._proxy_client.set('pkt_out_length', self._pkt_size)
        self._proxy_client.set('pkt_out_stat', (0, None, None))
        self._proxy_client.run('start_loop_pkt_out', 1.0/self._expected_pps, MAX_RUNNING_TIME)
        PacketSender.start(self)
        
    def stop(self):
        self._proxy_client.run('stop_loop_pkt_out')
        (self._sent_count, start, end) = self._proxy_client.get('pkt_out_stat')
        self._pkt_out_pps = self._sent_count / (end - start)
        PacketSender.stop(self)
        
    def get_sent_pps(self):
        return self._pkt_out_pps





class ReceiveEgress(PacketReceiver):
    
    def __init__(self, _):
        PacketReceiver.__init__(self)
        self._tcpdump = Tcpdump(config.active_config)
        
    def start(self):
        self._tcpdump.start()
        PacketReceiver.start(self)
        
    def stop(self):
        PacketReceiver.stop(self)
        result = self._tcpdump.stop_and_get_result()
        self._recvd_count = result.recvd_pkt_count




def test():
    """ Sanity check. """
    
#    controller_p = start_controller()
#    util.verbose_sleep(25, 'Controller is starting...')
#    
    proxy_client = StateProxyClient(FLEXI_CONTROLLER_HOST)
    send_trigger_packet(1500)
    
#    print '*' * 80
#    print 'ingress -> pkt-in'
#    print '*' * 80
#    
#    ingress = GenerateIngress(300, proxy_client)
#    pkt_in = ReceivePktIn(proxy_client)
#    
#    pkt_in.start()
#    ingress.start()
#    util.verbose_sleep(20, 'Ingress -> pkt_in...')
#    ingress.stop()
#    pkt_in.stop()
#    
#    print 'sent pps:', ingress.get_sent_pps()
#    print 'recvd pps:', pkt_in.get_received_pps()

#    print '*' * 80
#    print 'flow-mod -> rules'
#    print '*' * 80
#
#    flow_mod = GenerateFlowMod(200, proxy_client)
#    check_rule = CheckRuleInstallationRate(proxy_client, flow_stat_interval=10, steady_state_start=30, steady_state_end=60)
#    
#    check_rule.start()
#    flow_mod.start()
#    util.verbose_sleep(60, 'flow-mod -> rules')
#    flow_mod.stop()
#    check_rule.stop()
#
#    print 'sent pps:', flow_mod.get_sent_pps()
#    print 'recvd pps:', check_rule.get_received_pps()

    print '*' * 80
    print 'pkt-out -> egress'
    print '*' * 80

    pkt_out = GeneratePktOut(200, proxy_client)
    egress = ReceiveEgress(proxy_client)

    egress.start()
    pkt_out.start()
    util.verbose_sleep(20, 'pkt-out -> egress')
    pkt_out.stop()
    egress.stop()
    
    print 'sent pps:', pkt_out.get_sent_pps()
    print 'recvd pps:', egress.get_received_pps()



    #controller_p.kill()

        

if __name__ == '__main__':
    test()