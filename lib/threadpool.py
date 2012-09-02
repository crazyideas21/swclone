'''
Thread Pool duh. Adapted from: http://code.activestate.com/recipes/577187/ 

Created on Aug 31, 2012

@author: danny
'''

from Queue import Queue, Empty
from threading import Thread
import traceback

class _Worker(Thread):
    """Thread executing tasks from a given tasks queue"""
    def __init__(self, tasks):
        Thread.__init__(self)
        self.tasks = tasks
        self.daemon = True
        self.start()
    
    def run(self):
        
        while True:
            
            try:
                (func, args, kargs) = self.tasks.get(True, 20)
            except Empty:
                break
                            
            try: 
                func(*args, **kargs)
            except: 
                print traceback.format_exc()
                break
            finally:    
                self.tasks.task_done()


class ThreadPool:
    """Pool of threads consuming tasks from a queue"""
    def __init__(self, num_threads):
        self.tasks = Queue(num_threads)
        for _ in range(num_threads): 
            _Worker(self.tasks)

    def add_task(self, func, *args, **kargs):
        """Add a task to the queue"""
        self.tasks.put((func, args, kargs))

    def wait_completion(self):
        """Wait for completion of all the tasks in the queue"""
        self.tasks.join()
