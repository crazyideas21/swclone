'''
Client that talks to the ExpControl at our modified learning switch.

Created on Aug 27, 2012

@author: danny

'''

import socket
from lib.session_sock import SessionSocket


class ExpControlClient:
    
    
    def __init__(self, controller_host, controller_port=16633):        
    
        raw_sock = socket.create_connection((controller_host, controller_port))
        self.sock = SessionSocket(raw_sock)
        
    
    
    def execute(self, cmd):
        
        self.sock.send(cmd)
        return self.sock.recv()
    
    