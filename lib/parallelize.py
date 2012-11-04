'''
Execute a job with multiple worker threads/processes.

Usage: Given some function func(), we want to execute it over 10 threads.

> pool = ThreadPool = (max_threads=10)
> pool.run(func, arg1, arg2, k=v)

User functions must provide their own error-handling.

Created on Oct 25, 2012

@author: danny
'''
import threading
from Queue import Queue, Empty, Full



class ThreadPool:
    
    
    def __init__(self, max_threads=10, block_on_busy_workers=False):
        """
        Max_threads specifies the number of worker threads, while
        block_on_busy_workers indicates whether run() should block if all the
        worker threads are busy.
        
        """
        if block_on_busy_workers:
            self._queue = Queue(maxsize=1)    
        else:
            self._queue = Queue(maxsize=0)    
                    
        self._lock = threading.Lock()
        self._active = True                        
        self._threads = []
            
        for _ in range(max_threads):
            t = threading.Thread(target=self._worker_thread)
            t.start()
            self._threads.append(t)
        
        
        
    def run(self, func, *args, **kwargs):
        """ May block if block_on_busy_workers is set. """
        while True:                
            try:
                self._queue.put((func, args, kwargs), block=True, timeout=2)
                break
            except Full:
                with self._lock:
                    if not self._active:
                        break

        
        
        
        
    def close(self):
        with self._lock:
            self._active = False
        for t in self._threads:
            t.join()
                
                
        
    def _worker_thread(self):        
        while True:            
            try:
                (func, args, kwargs) = self._queue.get(block=True, timeout=2)
            except Empty:
                pass
            else:
                func(*args, **kwargs)
            finally:  
                with self._lock:
                    if not self._active:
                        break

            