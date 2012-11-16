'''
Loops the execution of a function at a given interval.

Usage: Say we want to execute func() every 10 ms for 2 minutes, so we write the
following:

looper = Looper(func, 0.010, 140)
looper.start()
# Print some status, or wait for two minutes.
looper.stop() 

Created on Nov 15, 2012

@author: Danny Y. Huang

'''
import threading, time
from lib.packet_sender_receiver import StateController

class Looper(StateController):
    
    def __init__(self, func, interval, max_run_time):
        
        StateController.__init__(self)

        self._func = func
        self._gap = interval
        self._max_run_time = max_run_time

        self._thread = threading.Thread(target=self._loop_thread)
        self._thread.daemon = True

        self._lock = threading.Lock()
        self._loop_active = True
        
        
        
    def start(self):
        
        StateController.start(self)
        self._thread.start()
        
        
        

    def stop(self):
        
        with self._lock:
            self._loop_active = False
        self._thread.join(timeout=20)
        StateController.stop(self)
    


    def _loop_thread(self):
        
        last_start_time = 0
        
        while True:
        
            # Check for stopping conditions.
            with self._lock:
                if not self._loop_active:
                    break

            # Have we timed out?
            current_time = time.time()
            if current_time - self._start_time > self._max_run_time:
                break 

            # Determine how long to sleep.
            time_elapsed = current_time - last_start_time
            if time_elapsed < self._gap:
                sleep_time = self._gap - time_elapsed
                time.sleep(sleep_time)
                
            # Fire!
            last_start_time = time.time()
            self._func()




def test():
    
    import random
    
    counter = [0]
    def func():
        time.sleep(random.uniform(0.0010 * 0.7, 0.0010 * 1.1))
        counter[0] += 1
        
    looper = Looper(func, 0.010, 20)
    looper.start()
    time.sleep(6)
    looper.stop()

    print 'Average rate:', counter[0] / looper.get_running_time()


if __name__ == '__main__':
    test()




