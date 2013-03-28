'''
Finds a flow-table's flow mod rate, based on the Sec 3.2.1 in the DevoFlow
paper: "...we attached two servers to the switch and opened the next con-
nection from one server to the other as soon as the previous connection was
established."

Argument: [redis_server_ip]

Created on Mar 24, 2013

@author: danny
'''

import socket, sys, time


REDIS_PORT = 6379
MAX_RUNNING_TIME = 60


def main():
    
    server_ip = sys.argv[1]
    conn_count = 0
    sock_list = []
    
    start_time = time.time()    
    while time.time() - start_time <= MAX_RUNNING_TIME:        
        
#        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
#        sock.setblocking(0)
#        sock.connect_ex((server_ip, REDIS_PORT))        
        sock_list += [socket.create_connection((server_ip, REDIS_PORT))]
        conn_count += 1
        
    print conn_count
    print conn_count / (time.time() - start_time)
    
    

if __name__ == '__main__':
    main()