"""
Wrapper functions for the OpenFlow switch.

"""
import sys, time, subprocess, re
import lib.config as config
import lib.util as util


class Switch:
    
    def __init__(self, config_obj):
        
        if config_obj:
            self.config = config_obj
        else:
            self.config = config.HPSwitch()


    def reset_flow_table(self):
        """
        Removes all entries from all the flow tables.
        
        """
        p = util.run_ssh(self.config.del_flow_cmd,
                         hostname=self.config.ofctl_ip)
        p.wait()
        
        # Let system stabilize.
        time.sleep(4)
        
    
    
    
    def del_rules(self, flow_id_list, base_port_number=10000, wait_and_verify=True):
        """
        Removes the list of flow_id rules from the flow table.
        
        """
        initial_rule_count = None
        if wait_and_verify:
            initial_rule_count = len(self.dump_tables(filter='udp'))
        
        flow_id_list_copy = flow_id_list[:]
        
        while flow_id_list_copy:
    
            # Remove flows in batches of ten.
    
            ten_flow_id_list = flow_id_list_copy[0 : 10]
            flow_id_list_copy = flow_id_list_copy[10 : ]
        
            cmd_str = ''
            
            for flow_id in ten_flow_id_list:
                cmd_str += self.config.del_one_rule_cmd(flow_id + base_port_number) + '; '
            
            p = util.run_ssh(cmd_str, hostname=self.config.ofctl_ip,
                               stdout=subprocess.PIPE, verbose=False)
            p.wait()
            
            sys.stdout.write('\r del_rules: %d left' % (len(flow_id_list_copy)))
            sys.stdout.flush()
            
        print ''
            
        if wait_and_verify:
            
            time.sleep(2)
            
            final_rule_count = len(self.dump_tables(filter='udp'))
            assert initial_rule_count == final_rule_count + len(flow_id_list)
    
            print 'del_rules verified'
            
    
    
    def dump_tables(self, filter_str='table_id=0'):
        """
        Returns a list of rules in the TCAM (table_id = 0).
        
        """
        p = util.run_ssh(self.config.dump_flows_cmd,
                         hostname=self.config.ofctl_ip, stdout=subprocess.PIPE,
                         verbose=False)
        return [line for line in p.stdout if line.find(filter_str) >= 0]
    
    
    
    def get_flow_distribution_dict(self, table_id_str='table_id'):
        """
        Returns a dictionary that maps table IDs to lists of tp_src for which
        the corresponding rule is in that table.
        
        """
        dist_dict = {}        
        table_id_regex = re.compile(table_id_str + '=(\d+)')
        tp_src_regex = re.compile('tp_src=(\d+)')
        
        for rule in self.dump_tables(filter_str=''):
            
            table_id_search = table_id_regex.search(rule)
            tp_src_search = tp_src_regex.search(rule)
            
            if table_id_search and tp_src_search:
                table_id = int(table_id_search.group(1))
                tp_src = int(tp_src_search.group(1))
                if table_id not in dist_dict:
                    dist_dict[table_id] = []
                dist_dict[table_id].append(tp_src)
                
        return dist_dict
        
        
    
    
    def add_rules(self, rule_count, 
                      wait_and_verify=True, 
                      base_port_number=10000, 
                      table_id_filter='table_id=0'):
        """
        Adds specified number of rules into the TCAM (table_id = 0). Ensures that
        fewer than 8 rules are added every second. Returns the number of rules added
        to the TCAM from this function call.
        
        TODO: For wait-and-verify, impose a checkpoint upon every verification. If
        verification fails, we can delete the newly added rules, roll back to the
        checkpoint, and re-try.
        
        """
        initial_flow_count = len(self.dump_tables(filter=table_id_filter))
        p_list = []
        
        for flow_id in range(rule_count):
            
            port = flow_id + base_port_number
            p = util.run_ssh(self.config.add_rule_cmd(self.config.new_rule(port)),
                               hostname=self.config.ofctl_ip, stdout=subprocess.PIPE,
                               verbose=False)
    
            if wait_and_verify: 
                
                p.wait()
            
                # Verifies the TCAM for every ten rules added.
                if flow_id % 10 == 0:
                    assert len(self.dump_tables(filter=table_id_filter)) - initial_flow_count == flow_id + 1
                    
                    sys.stdout.write('\radd_rules: %d left' % (rule_count - flow_id))                                
                    sys.stdout.flush()
                        
            else:
    
                sys.stdout.write('\radd_rules: %d left' % (rule_count - flow_id))                                
                sys.stdout.flush()
                
                p_list += [p]
                time.sleep(0.3)
    
        print ''
    
        # Wait for all processes to finish        
        for p in p_list:
            p.wait()
                            
        return len(self.dump_tables(filter=table_id_filter)) - initial_flow_count



def main():
    """ Command-line utility. """

    if 'dump' in sys.argv:
        sw_cmd = config.active_config.dump_flows_cmd
    elif 'del' in sys.argv:
        sw_cmd = config.active_config.del_flow_cmd
    else:
        print 'Enter "dump" or "del".'
        exit(1)
        
    p = util.run_ssh(sw_cmd,
                       hostname=config.active_config.ofctl_ip)
    p.wait()    

    
    
if __name__ == '__main__':
    main()
    
    