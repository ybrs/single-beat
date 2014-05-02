import os
import sys
import pyuv
import time
import socket
import redis
import logging
import signal

logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)
logger.debug("hello....")

REDIS_SERVER  = os.environ.get('SINGLE_BEAT_REDIS_SERVER', 'redis://localhost:6379')
IDENTIFIER = os.environ.get('SINGLE_BEAT_IDENTIFIER', None)
LOCK_TIME = int(os.environ.get('SINGLE_BEAT_LOCK_TIME', 5))
HEARTBEAT_INTERVAL = int(os.environ.get('SINGLE_BEAT_LOCK_TIME', 1))

rds = redis.Redis.from_url(REDIS_SERVER)
rds.ping()

def proc_exit_cb(proc, exit_status, term_signal):
    sys.exit(exit_status)

def stdout_read_cb(handle, data, error):
    if data:
        sys.stdout.write(data)

def stderr_read_cb(handle, data, error):
    if data:
        sys.stdout.write(data)

t1 = time.time()
def timer_cb(timer):
    global t1, state
    logger.debug("timer called %s state=%s", time.time() - t1, state)
    t1 = time.time()
    if state == 'WAITING':
        if not already_running(identifier):
            spawn_process()
    elif state == "RUNNING":
        rds.set("SINGLE_BEAT_%s" % identifier, "%s:%s" % (socket.gethostname(), proc.pid), ex=LOCK_TIME)


def already_running(identifier):
    return rds.get('SINGLE_BEAT_%s' % identifier)

def sigterm_handler(signum, frame):
    logging.debug("our state %s", state)
    if state == 'WAITING':
        sys.exit(signum)
    elif state == 'RUNNING':
        logger.debug('already running sending signal to child - %s', proc.pid)
        os.kill(proc.pid, signum)

signal.signal(signal.SIGTERM, sigterm_handler)
signal.signal(signal.SIGINT, sigterm_handler)


state = None
identifier = None

def run_process():
    global identifier, state, loop
    args = sys.argv[1:]
    identifier = IDENTIFIER or args[0]
    #
    loop = pyuv.Loop.default_loop()
    timer = pyuv.Timer(loop)
    state = 'WAITING'
    # runs every 1 second
    timer.start(timer_cb, 0.1, HEARTBEAT_INTERVAL)
    loop.run()


def spawn_process():
    global state, proc
    args = sys.argv[1:]
    print args[1:]

    proc = pyuv.Process(loop)

    stdout_pipe = pyuv.Pipe(loop)
    stderr_pipe = pyuv.Pipe(loop)

    stdio = []
    stdio.append(pyuv.StdIO(flags=pyuv.UV_IGNORE))
    stdio.append(pyuv.StdIO(stream=stdout_pipe, flags=pyuv.UV_CREATE_PIPE|pyuv.UV_WRITABLE_PIPE))
    stdio.append(pyuv.StdIO(stream=stderr_pipe, flags=pyuv.UV_CREATE_PIPE|pyuv.UV_WRITABLE_PIPE))

    rds.set("SINGLE_BEAT_%s" % identifier, "%s:%s" % (socket.gethostname(), proc.pid), ex=LOCK_TIME)
    state = "RUNNING"

    proc.spawn(file=args[0],
               args=args[1:],
               cwd=os.getcwd(),
               exit_callback=proc_exit_cb,
               stdio=stdio)

    print ">>> pid >>>", proc.pid
    print "SB_%s" % identifier
    stdout_pipe.start_read(stdout_read_cb)
    stderr_pipe.start_read(stderr_read_cb)



if __name__ == "__main__":
    run_process()