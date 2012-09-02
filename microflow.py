'''
Sends and receives short, bursty TCP flows by implementing an echo service.
Specify either 'server' or 'client' to start the application in either mode.

Created on Aug 31, 2012

@author: danny
'''
import asyncore, sys, socket, time
import lib.util as util
from lib.threadpool import ThreadPool

class EchoHandler(asyncore.dispatcher_with_send):

    def handle_read(self):
        data = self.recv(4096)
        if data:
            self.send(data)



class EchoServer(asyncore.dispatcher):

    def __init__(self, host, port):
        asyncore.dispatcher.__init__(self)
        self.create_socket(socket.AF_INET, socket.SOCK_STREAM)
        self.set_reuse_addr()
        self.bind((host, port))
        self.listen(5)

    def handle_accept(self):
        sock, _ = self.accept()
        _ = EchoHandler(sock)



class EchoClient:
    
    def __init__(self, host, port, length):
        self.host = host
        self.port = port
        self.length = length
        self.running_time = None
        
    def start(self):
        w_data = '0' * self.length
        r_data = ''
        start_time = time.time()
        try:
            sock = socket.create_connection((self.host, self.port))
            sock.sendall(w_data)
            while len(r_data) < self.length:
                r_data += sock.recv(4096)
            sock.close()
            self.running_time = time.time() - start_time
        except Exception, err:
            print err, repr(err)
        
        
            
    

            
def server():
    
    server = EchoServer('0.0.0.0', 12345)
    try:
        asyncore.loop()
    except KeyboardInterrupt:
        pass
    
    
    
def client():
    
    util.ping_test()

    client_list = []
    pool = ThreadPool(150) 
    
    for i in range(700):
        print 'Starting client', i
        client = EchoClient('10.66.10.1', 12345, 64*1000)        
        pool.add_task(client.start)
        client_list.append(client)
    
    pool.wait_completion()

    delay_list = []
    for client in client_list:
        if client.running_time is None:
            delay_ms = 0
        else:
            delay_ms = client.running_time * 1000.0
        delay_list.append(delay_ms)
    
    cdf_list = util.make_cdf(delay_list)
    
    with open('data/microflow_delay.txt', 'w') as f:
        for (x, y) in zip(delay_list, cdf_list):
            print >> f, x, y
        





def main():
    
    if 'server' in sys.argv:
        server()
    elif 'client' in sys.argv:
        client()
    else:
        print >> sys.stderr, 'Bad command line arguments. Specify either "server" or "client" mode.'


if __name__ == '__main__':
    main()
