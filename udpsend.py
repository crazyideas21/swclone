'''
Sends a large number of UDP packets to the dest IP.

Arguments: [dest_ip]

If dest_ip is not specified, this acts as a server.

Created on Mar 24, 2013

@author: danny
'''

import sys, socket, time

MAX_SOCK_COUNT = 2000
GAP = 0.125
PORT = 48902


def client(dest_ip):
    
    print 'Client mode.'    
    sock_list = [socket.socket(socket.AF_INET, socket.SOCK_DGRAM) for _ in range(MAX_SOCK_COUNT)]

    print 'Sending...'     
    #while True:
    for sock in sock_list:
        sock.sendto('0', (dest_ip, PORT))
        time.sleep(GAP)
        





def main():
    
    try:
        dest_ip = sys.argv[1]
    except:
        server()
    else:
        client(dest_ip)
        


def server():

    print 'Server mode; doing nothing.'
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.bind(('', PORT))
    
    port_set = set()
    
    while True:
        (_, (_, port)) = sock.recvfrom(2048)
        port_set.add(port)
        print 'Connections:', len(port_set)



if __name__ == '__main__':
    main()