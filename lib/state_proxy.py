'''
Proxy server for local state. Allows the local state to be accessed remotely.
The local object should have an internal variable called "lock" that prevents
concurrent accesses of local variables.

Created on Nov 14, 2012

@author: danny
'''

import socket, threading, traceback, sys, os
from lib.session_sock import SessionSocket, ConnectionClosed
from lib.util import pretty_dict





class StateProxyServer(threading.Thread):
    
    
    DEFAULT_LISTEN_PORT = 56565
    
    
    def __init__(self, local_obj, local_obj_lock, local_obj_reset_func, 
                       listen_port=DEFAULT_LISTEN_PORT):
                
        threading.Thread.__init__(self)
        self.daemon = True
        
        self._local_obj = local_obj
        self._lock = local_obj_lock
        self._listen_port = listen_port
        self._reset_func = local_obj_reset_func
        


    def run(self):

        server_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        server_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        server_sock.bind(('0.0.0.0', self._listen_port))
        server_sock.listen(5)
        
        while True:
            (raw_client_sock, _) = server_sock.accept()
            client_sock = SessionSocket(raw_client_sock)
            client_t = threading.Thread(target=self._handle_connection, args=(client_sock,))
            client_t.daemon = True
            client_t.start()
            
        
        
    def _handle_connection(self, client_sock):
        try:
            while self._handle_command(client_sock):
                pass
        
        except:
            print >> sys.stderr, '*' * 80
            print >> sys.stderr, traceback.format_exc()
        
        client_sock.close()
         
         
         
            
    def _handle_command(self, sock):
        
        try:
            cmd_list = sock.recv()
        except ConnectionClosed:
            return False
        
        if cmd_list[0] == 'GET':
            # ['GET', 'name_of_attr'] -> value_obj
            with self._lock:
                ret = getattr(self._local_obj, cmd_list[1])
            sock.send(ret)

        elif cmd_list[0] == 'GETALL':
            # ['GETALL'] -> obj's dict
            with self._lock:
                ret = pretty_dict(self._local_obj.__dict__)
            sock.send(ret)
        
        elif cmd_list[0] == 'SET':
            # ['SET', 'name_of_attr', value_obj] -> 'OK'
            with self._lock:
                setattr(self._local_obj, cmd_list[1], cmd_list[2])
            sock.send('OK')
            
        elif cmd_list[0] == 'RESET':
            # ['RESET'] -> 'OK'
            self._reset_func()
            sock.send('OK')
            
        elif cmd_list[0] == 'RUN':
            # ['RUN', 'func_name', 'param1', 'param2', ...] -> ret obj
            func = getattr(self._local_obj, cmd_list[1])
            ret = func(*cmd_list[2:])
            sock.send(ret)
            
        elif cmd_list[0] == 'EXIT':
            os._exit(0)
            
        elif cmd_list[0] == 'HELLO':
            sock.send('Hi there!')
            
        else:
            raise RuntimeError('Bad command: %s' % cmd_list)
        
        return True
        


class StateProxyClient:
    
    def __init__(self, proxy_host, port=StateProxyServer.DEFAULT_LISTEN_PORT):
        raw_sock = socket.create_connection((proxy_host, port))
        self._sock = SessionSocket(raw_sock)
        
    def hello(self):
        self._sock.send(['HELLO'])
        assert self._sock.recv() == 'Hi there!'
        
    def get(self, attr):
        self._sock.send(['GET', str(attr)])
        return self._sock.recv()
    
    def getall(self):
        self._sock.send(['GETALL'])
        return self._sock.recv()
    
    def set(self, attr, value):
        self._sock.send(['SET', str(attr), value])
        assert self._sock.recv() == 'OK'
        
    def reset(self):
        self._sock.send(['RESET']) 
        assert self._sock.recv() == 'OK'
        
    def run(self, func_name, *args):
        self._sock.send(['RUN', str(func_name)] + list(args))
        return self._sock.recv()
    
    def exit(self):
        self._sock.send(['EXIT'])
    