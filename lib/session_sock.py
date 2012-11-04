'''
A session wrapper for TCP non-blocking sockets. Includes a header that indicates
the subsequent length of the stream, which is pickled from the input object.

Usage:

sock = ... # Create a normal TCP socket
sess_sock = SessionSocket(sock)
sess_sock.send("hello") # This actually sends all of "5@hello".

# On the other side of connection.
print sess_sock.recv() # This returns all of "hello".
sess_sock.close()

Created on Oct 23, 2012

@author: Danny Y. Huang

'''
import cPickle as pickle


class InsufficientData(Exception):
    pass


class SessionSocket:
    
    
    def __init__(self, raw_sock):        
        self._sock = raw_sock
        self._rbuf = ''
        
                
    def send(self, raw_data):       
        """ 
        Blocks until raw data is completely sent. Raw data must be any picklable
        type. Returns the length of raw_data.
        
        """
        data = pickle.dumps(raw_data) 
        wbuf = str(len(data)) + '@' + data         
        while wbuf:
            sent = self._sock.send(wbuf)
            wbuf = wbuf[sent:]
        
        
    def recv(self):
        """ 
        May block if no data in rbuf. Returns the data in its original type. 
        
        """
        while True:                        
            try:
                # Check rbuf if there's enough data to return.
                try:
                    (header, data) = self._rbuf.split('@', 1)
                except ValueError:
                    raise InsufficientData
                
                length = int(header)
                if len(data) < length:
                    raise InsufficientData
                else:                    
                    self._rbuf = self._rbuf[len(header) + 1 + length : ]
                    data = data[0 : length]
                    return pickle.loads(data)            
                
            except InsufficientData:
                # Not enough data. Ask network.
                self._rbuf += self._sock.recv(32768)
        
    
    def close(self):
        return self._sock.close()
        
        