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
from lib.pktgen import Pktgen
from lib.tcpdump import Tcpdump
from lib.state_proxy import StateProxyClient
import lib.config as config
import lib.util as util
import time



MAX_RUNNING_TIME = 70
TRIGGER_PORT = 32767

FLEXI_CONTROLLER_HOST = '132.239.17.35'
FLEXI_CONTROLLER_SSH_PORT = 2222
FLEXI_CONTROLLER_SSH_USERNAME = 'root'


POX_CMD = 'python pox/pox.py --no-cli log.level --CRITICAL openflow.of_01 --port=45678 forwarding.flexi_controller --of_port_1=32 --of_port_2=34;'
#POX_CMD = 'python pox/pox.py --no-cli log.level --CRITICAL openflow.of_01 --port=56789 forwarding.flexi_controller --of_port_1=1 --of_port_2=2;'


def send_trigger_packet():
    """ 
    Sends a reference packet to the controller, from which flow-mods or pkt-outs
    can be constructed. Blocks until the packet is sent.
    
    """
    util.ping_test(how_many_pings=4, dest_host=config.active_config.source_ip)
    util.run_ssh('iperf -u -c ', config.active_config.dest_ip, 
                 ' -p ', TRIGGER_PORT, ' -t 1 -l 12',
                 hostname=config.active_config.source_ip).wait()
    

def start_controller():
    """ Returns a Popen object. """
    
    cmd = ['cd ~/swclone;',
           'export PYTHONPATH=$PYTHONPATH:`pwd`;',
           'cd ~/swclone/lib;',
           'export PYTHONPATH=$PYTHONPATH:`pwd`;',
           'cd ~/swclone;',
           POX_CMD
           ]
    
    return util.run_ssh(*cmd, verbose=True, hostname=FLEXI_CONTROLLER_HOST, 
                        user=FLEXI_CONTROLLER_SSH_USERNAME, port=FLEXI_CONTROLLER_SSH_PORT)





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
        self._proxy_client.set('pkt_in_stat', (0, None, None))
        self._pkt_in_pps = None
        
    def start(self):
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
        self._proxy_client.set('flow_mod_stat', (0, None, None))
        self._flow_mod_pps = None
        
    def start(self):
        assert self._proxy_client.run('trigger_event_is_ready') 
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
    
    def __init__(self, state_proxy_client, flow_stat_interval=7, steady_state_start=30, steady_state_end=60):
        PacketReceiver.__init__(self)
        self._flow_stat_interval = flow_stat_interval
        self._steady_state_start = steady_state_start
        self._steady_state_end = steady_state_end
        self._proxy_client = state_proxy_client
        self._proxy_client.set('flow_stat_interval', self._flow_stat_interval)
        self._proxy_client.set('flow_count_dict', {})        
        
    def start(self):
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
        self._proxy_client.set('pkt_out_length', self._pkt_size)
        self._proxy_client.set('pkt_out_stat', (0, None, None))
        
        
    def start(self):
        assert self._proxy_client.run('trigger_event_is_ready') 
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
        self._tcpdump = Tcpdump(config.active_config, 
                                filter='udp and dst port ' + str(TRIGGER_PORT))
        
    def start(self):
        self._tcpdump.start()
        PacketReceiver.start(self)
        
    def stop(self):
        PacketReceiver.stop(self)
        result = self._tcpdump.stop_and_get_result()
        self._recvd_count = result.recvd_pkt_count



def main():
    
    for pkt_size in [1500,64]:
        run(pkt_size)



def run(packet_size=1500):
    
    # Writer initial header to file.
    result_file = './data/hp_sensitivity_%d_byte.csv' % packet_size
    with open(result_file, 'w') as f:
        print >> f, 'ingress_pps,flow_mod_pps,pkt_out_pps,pkt_in_pps,rule_pps,egress_pps,expected_ingress,expected_flow_mod,expected_pkt_out'
    
    input_list = [10, 100, 400, 700, 1000]  # HP
    #input_list = [10, 100, 1000]  # OVS
    
    for ingress_pps in input_list:
        for flow_mod_pps in input_list:
            for pkt_out_pps in input_list:

                start_controller()
                
                while True:
                    try:
                        proxy_client = StateProxyClient(FLEXI_CONTROLLER_HOST)
                        proxy_client.hello()
                        break
                    except:
                        print 'Waiting for controller...'
                        time.sleep(2)
                
                proxy_client.reset()
                print proxy_client.getall()
                send_trigger_packet()

                # Confirm trigger.
                while not proxy_client.run('trigger_event_is_ready'):
                    print proxy_client.getall()
                    print 'Waiting for trigger...'
                    time.sleep(2)

                # Set up the pkt generators    
                ingress = GenerateIngress(ingress_pps, proxy_client, packet_size=packet_size)    
                flow_mod = GenerateFlowMod(flow_mod_pps, proxy_client)    
                pkt_out = GeneratePktOut(pkt_out_pps, proxy_client, packet_size=packet_size)

                # Set up pkt receivers.
                pkt_in = ReceivePktIn(proxy_client)
                check_rule = CheckRuleInstallationRate(proxy_client)
                egress = ReceiveEgress(proxy_client)
                
                print proxy_client.getall()
                
                # Start receiving and sending.
                for obj in [pkt_in, check_rule, egress, ingress, flow_mod, pkt_out]:
                    obj.start()

                # Wait.
                prompt = '(ingress_pps, flow_mod_pps, pkt_out_pps) = '
                prompt += str((ingress_pps, flow_mod_pps, pkt_out_pps))
                util.verbose_sleep(MAX_RUNNING_TIME, prompt)
                    
                # Stop sending and receiving.
                for obj in [ingress, flow_mod, pkt_out, pkt_in, check_rule, egress]:
                    obj.stop()
                    
                # Gather data.
                data_list = [ingress.get_sent_pps(),
                             flow_mod.get_sent_pps(),
                             pkt_out.get_sent_pps(),
                             pkt_in.get_received_pps(),
                             check_rule.get_received_pps(),
                             egress.get_received_pps(),
                             ingress_pps,
                             flow_mod_pps,
                             pkt_out_pps]
                
                # Write csv data.
                data = ','.join(['%.4f' % pps for pps in data_list])  
                with open(result_file, 'a') as f:
                    print >> f, data
                    
                print '*' * 80
                print data
                print '*' * 80
                
                proxy_client.exit()
                
                util.verbose_sleep(5, 'Waiting for the next experiment...')
                
                


def test():
    """ Sanity check. """
    
    proxy_client = StateProxyClient(FLEXI_CONTROLLER_HOST)
    proxy_client.reset()
    send_trigger_packet()
    
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
#
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

    pkt_out = GeneratePktOut(200, proxy_client, packet_size=1500)
    egress = ReceiveEgress(proxy_client)

    egress.start()
    pkt_out.start()
    util.verbose_sleep(5, 'pkt-out -> egress')
    pkt_out.stop()
    egress.stop()
    
    print 'sent pps:', pkt_out.get_sent_pps()
    print 'recvd pps:', egress.get_received_pps()



    #controller_p.kill()

        

if __name__ == '__main__':
    main()
    
    
    
    