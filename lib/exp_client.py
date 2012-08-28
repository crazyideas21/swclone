'''
Client that talks to the ExpControl at our modified learning switch.

Created on Aug 27, 2012

@author: danny

'''

import socket


class ExpControlClient:
    
    
    def __init__(self, controller_host, controller_port=16633):        
    
        self.sock = socket.create_connection((controller_host, controller_port))
        
    
    
    def execute(self, cmd):
        
        self.sock.sendall(str(cmd) + '\n\n')
        
        result = ''
        while not result.endswith('\n\n'):
            result += self.sock.recv(4096)
            
        return eval(result)
    
    