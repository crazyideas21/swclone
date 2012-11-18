import math, subprocess, traceback, datetime, sys, time, warnings, threading
import lib.config as config


class Logger:
    
    def __init__(self, log_file, reset=True):
        
        self._log_file = log_file
        self._base_time = time.time()
        self._lock = threading.Lock()
        
        if reset:
            with open(self._log_file, 'w') as f:
                print >> f, '*' * 80
                print >> f, datetime.datetime.today().strftime('%m-%d %H:%M:%S')
                print >> f, '*' * 80
                
        
        
    
    def write(self, *log_str_args):
    
        log_str_args = [str(e) for e in log_str_args]
        log_str = ' '.join(log_str_args)
    
        with self._lock:
            with open(self._log_file, 'a') as f:
                print >> f, '%.3f' % (time.time() - self._base_time),
                print >> f, datetime.datetime.today().strftime('%m-%d %H:%M:%S'), 
                print >> f, '>', log_str


    def __call__(self, *log_str_args):
        
        self.write(*log_str_args)
        
        

# Stores (func, args, kwargs) -> func output
_func_cache_dict = {}
_func_cache_lock = threading.Lock()

def func_cache(func, *args, **kwargs):
    """
    Returns the output of the func(*args, **kwargs). If the function is
    invoked again with the same obj and arguments, the cached result is
    returned. Thread-safe. All arguments must be hashable.
    
    """
    key = (func, tuple(args), tuple(kwargs.items()))
    with _func_cache_lock:
        try:
            return _func_cache_dict[key]
        except KeyError:
            pass
        except TypeError:
            raise TypeError('Unhasable arguments: ' + str(key))
        
    ret = func(*args, **kwargs)
    with _func_cache_lock:
        _func_cache_dict[key] = ret

    return ret



def deprecated(func):
    """This is a decorator which can be used to mark functions
    as deprecated. It will result in a warning being emmitted
    when the function is used."""
    ## {{{ http://code.activestate.com/recipes/391367/ (r1)    
    def newFunc(*args, **kwargs):
        warnings.warn("Call to deprecated function %s." % func.__name__,
                      category=DeprecationWarning)
        return func(*args, **kwargs)
    newFunc.__name__ = func.__name__
    newFunc.__doc__ = func.__doc__
    newFunc.__dict__.update(func.__dict__)
    return newFunc






def dictify(obj, max_level=5):
    """
    Recursively returns the object's string representation in the form of
    dictionaries.
    
    """
    if hasattr(obj, '__dict__') and max_level > 0:
        obj_dict = dict(obj.__dict__)
        for key in obj_dict:
            obj_dict[key] = dictify(obj_dict[key], max_level=max_level-1)
        return obj_dict
    
    else:
        return obj



def pretty_dict(dict_obj, indentation='  '):
    """ 
    Recursivly returns a formatted string representation of the dictionary.
    
    """
    result = ''
    
    if isinstance(dict_obj, dict):
        result += '\n'
        for key in dict_obj:
            result += indentation + ' * ' + str(key) + ' : '
            result += pretty_dict(dict_obj[key], indentation + '  ')
    else:
        result = repr(dict_obj) + ' [%d]' % len(str(dict_obj)) + '\n'
        
    return result



def verbose_sleep(t, prompt='Waiting...'):
    """
    Sleeps for t seconds, while printing out how many seconds left.
    
    """
    start_time = time.time()
    sys.stdout.write('\n')
    while True:
        t_elapsed = time.time() - start_time
        t_left = int(t - t_elapsed)
        if t_left > 0:
            sys.stdout.write('\r%s %s seconds       \r' % (prompt, t_left))
            sys.stdout.flush()
            time.sleep(1)
        else:
            break
    sys.stdout.write(prompt + 'Done.'  + ' ' * 20 + '\n')
    sys.stdout.flush()
    


def callback_sleep(t, callback, interval=2):
    """
    Sleeps for t seconds, while invoking the callback function at a given
    interval. The callback function should take one argument, t_left, which 
    denotes how many seconds left.
    
    """
    start_time = time.time()
    while True:
        t_elapsed = time.time() - start_time
        t_left = int(t - t_elapsed)
        if t_left > 0:        
            callback(t_left)
            time.sleep(interval)
        else:
            break
    




def ping_test(how_many_pings=5, dest_host=config.active_config.source_ip):
    """
    Pings from the source to destination hosts to refresh their ARP caches.
    
    """
    p = run_cmd('ping -c ', how_many_pings, ' ', dest_host, verbose=True)
    p.wait()
    



def run_cmd(*cmd_args, **kwargs):
    """
    Runs a command in shell. Returns the Popen handle. Passes kwargs to the
    subprocess.Popen() call. One could, for example, specify the value of
    'stdout'.

    """
    cmd_args_str = map(str, cmd_args)
    cmd_str = ''.join(cmd_args_str)
    
    verbose = config.active_config.verbose
    if 'verbose' in kwargs:
        verbose = kwargs['verbose']
        del kwargs['verbose']
    if verbose:
        print ' * Running: ' + cmd_str
        
    return subprocess.Popen(cmd_str, shell=True, **kwargs)



def run_ssh(*cmd_args, **kwargs):
    """
    Runs SSH. Need to specify these keyword arguments:
    - user: SSH user. If none, defaults to root.
    - hostname: SSH username.
    - port: SSH port. If none, defaults to 22.
    
    Specifying the '-t' options allows the remote process to be killed when the
    local ssh session is terminated. See:
    
    http://stackoverflow.com/questions/331642/how-to-make-ssh-to-kill-remote-process-when-i-interrupt-ssh-itself
    
    The cmd_args are what's actually run in the SSH session. The rest of the
    kwargs are passed into run_cmd().
    
    """
    user = 'root'
    if 'user' in kwargs:
        user = kwargs['user']
        del kwargs['user']

    port = 22
    if 'port' in kwargs:
        port = kwargs['port']
        del kwargs['port']
        
    hostname = kwargs['hostname']        
    del kwargs['hostname']
    
    args = ['ssh -t -p ', int(port), ' -l ', user, ' ', hostname, ' "'] + list(cmd_args) + ['"']         
    return run_cmd(*args, **kwargs)
    


def sync_clocks(config_obj):
    """
    Coarsely synchrnoizes the clock of local and remote hosts. 

    """
    ntpdate_cmd = 'pkill ntpd; ntpdate -p 8 ntp.ucsd.edu'
    
    remote_proc = run_ssh(ntpdate_cmd, hostname=config_obj.pktgen_host)
    local_proc  = run_cmd(ntpdate_cmd)
    
    print 'Synchronizing clocks...'
    assert local_proc.wait() == 0 and remote_proc.wait() == 0




def get_mean_and_stdev(inlist):
    """ Returns the mean and stdev as a tuple. """

    length = len(inlist)
    if length < 2:
        return (0, 0)

    list_sum = sum(inlist)
    
    mean = float(list_sum) / length
    sum_sq = 0.0

    for v in inlist:
        sum_sq += (v - mean) * (v - mean)

    stdev = math.sqrt(sum_sq / (length - 1))
    return (mean, stdev)




def safe_run(func, *args, **kwargs):
    """
    Executes a function and returns its result safely. Aborts and logs traceback
    to err.log upon error.
    
    """

    try:
        return func(*args, **kwargs)

    except Exception, err:
        error_log('Function %s, %s, %s' % (repr(func), repr(args), repr(kwargs)))
        error_log('Exception: %s, %s' % (err, repr(err)))
        error_log(traceback.format_exc())
        return None



def error_log(log_str):
    """ Logs error to err.log. """
    
    try:
        f = open('err.log', 'w')
        log_str = '[%s] %s' % (datetime.datetime.now(), log_str)
        print >> f, log_str
        print log_str
        f.close()

    except Exception, err:
        print 'Logging failed:', repr(err), str(err)
        


def make_cdf_table(inlist):
    """
    Calculates the CDF of elements in input list. Returns a sorted list of (v,p)
    values, where p is the cumulative probability of the value v in the input
    list. The input list is not modified.
    
    """
    inlength = len(inlist)
    if inlength == 0:
        return []
        
    prob_increment = 1.0 / inlength    
    probabilities = [0.0 + prob_increment * index for index in xrange(inlength)]

    inlist_sorted = sorted(inlist)
    return zip(inlist_sorted, probabilities)

        




def make_scatter(xlist, ylist, xlabel, ylabel, title, filename):
    """
    Generates a single scatter plot.
    
    """
    import boomslang
    
    p = boomslang.Plot()
    s = boomslang.Scatter()
    
    (s.xValues, s.yValues) = (xlist, ylist)
    p.setXLabel(xlabel)
    p.setYLabel(ylabel)
    p.setTitle(title)
    
    p.add(s)  
    p.save(filename)
    

def hex_to_int(hex_str):
    """
    Converts a hex_str (which may have spaces) into int.

    """
    hex_str = hex_str.replace(' ', '')
    return int(hex_str, 16)







#===============================================================================
# DEPRECATED
#===============================================================================




@deprecated        
def make_cdf(inlist):
    """
    DEPRECATED. Sorts the input list in place. Returns its CDF as a list, whose
    length is equal to the input list.
    
    """
    inlength = len(inlist)
    if inlength == 0:
        return []
    
    inlist.sort()
    prob_increment = 1.0 / inlength
    
    return [0.0 + prob_increment * index for index in xrange(inlength)]

    
