import os
import sys
import time
import socket
import redis
import logging
import signal
import tornado.ioloop
import tornado.process
import subprocess


REDIS_SERVER = os.environ.get('SINGLE_BEAT_REDIS_SERVER',
                              'redis://localhost:6379')
IDENTIFIER = os.environ.get('SINGLE_BEAT_IDENTIFIER', None)
LOCK_TIME = int(os.environ.get('SINGLE_BEAT_LOCK_TIME', 5))
INITIAL_LOCK_TIME = int(os.environ.get('SINGLE_BEAT_INITIAL_LOCK_TIME',
                                       LOCK_TIME * 2))
assert LOCK_TIME < INITIAL_LOCK_TIME, "inital lock time must be greater than lock time "

HEARTBEAT_INTERVAL = int(os.environ.get('SINGLE_BEAT_HEARTBEAT_INTERVAL', 1))
assert HEARTBEAT_INTERVAL < (LOCK_TIME / 2.0), "SINGLE_BEAT_HEARTBEAT_INTERVAL must be smaller than SINGLE_BEAT_LOCK_TIME / 2"

HOST_IDENTIFIER = os.environ.get('SINGLE_BEAT_HOST_IDENTIFIER',
                                 socket.gethostname())
LOG_LEVEL = os.environ.get('SINGLE_BEAT_LOG_LEVEL', 'warn')

# wait_mode can be, supervisored or heartbeat
WAIT_MODE = os.environ.get('SINGLE_BEAT_WAIT_MODE', 'heartbeat')
assert WAIT_MODE in ('supervised', 'heartbeat')
WAIT_BEFORE_DIE = int(os.environ.get('SINGLE_BEAT_WAIT_BEFORE_DIE', 60))

numeric_log_level = getattr(logging, LOG_LEVEL.upper(), None)
logging.basicConfig(level=numeric_log_level)
logger = logging.getLogger(__name__)

rds = redis.Redis.from_url(REDIS_SERVER)
rds.ping()

class Process(object):
    def __init__(self, args):
        self.args = args
        self.state = None
        self.t1 = time.time()

        self.identifier = IDENTIFIER or self.args[0]

        signal.signal(signal.SIGTERM, self.sigterm_handler)
        signal.signal(signal.SIGINT, self.sigterm_handler)

        self.state = 'WAITING'
        self.ioloop = tornado.ioloop.IOLoop.instance()

    def proc_exit_cb(self, exit_status):
        sys.exit(exit_status)

    def stdout_read_cb(self, data):
        sys.stdout.write(data)

    def stderr_read_cb(self, data):
        sys.stdout.write(data)

    def timer_cb(self):
        logger.debug("timer called %s state=%s",
                     time.time() - self.t1, self.state)
        self.t1 = time.time()
        if self.state == 'WAITING':
            if self.acquire_lock(self.identifier):
                self.spawn_process()
            else:
                if WAIT_MODE == 'supervised':
                    logging.debug("already running, will exit after %s seconds"
                                  % WAIT_BEFORE_DIE)
                    time.sleep(WAIT_BEFORE_DIE)
                    sys.exit()
        elif self.state == "RUNNING":
            rds.set("SINGLE_BEAT_%s" % self.identifier,
                    "%s:%s" % (HOST_IDENTIFIER, self.sprocess.pid), ex=LOCK_TIME)

    def acquire_lock(self, identifier):
        return rds.execute_command('SET', 'SINGLE_BEAT_%s' % self.identifier,
                                   "%s:%s" % (HOST_IDENTIFIER, '0'),
                                   'NX', 'EX', INITIAL_LOCK_TIME)

    def sigterm_handler(self, signum, frame):
        logging.debug("our state %s", self.state)
        if self.state == 'WAITING':
            sys.exit(signum)
        elif self.state == 'RUNNING':
            logger.debug('already running sending signal to child - %s',
                         self.sprocess.pid)
            os.kill(self.sprocess.pid, signum)
        self.ioloop.stop()

    def run(self):
        self.pc = tornado.ioloop.PeriodicCallback(self.timer_cb, HEARTBEAT_INTERVAL * 1000)
        self.pc.start()
        self.ioloop.start()

    def spawn_process(self):
        STREAM = tornado.process.Subprocess.STREAM
        cmd = sys.argv[1:]
        env = os.environ

        self.state = "RUNNING"

        self.sprocess = tornado.process.Subprocess(cmd,
                    env=env,
                    stdin=subprocess.PIPE,
                    stdout=STREAM,
                    stderr=STREAM
                   )
        self.sprocess.set_exit_callback(self.proc_exit_cb)

        self.sprocess.stdout.read_until_close(streaming_callback=self.stdout_read_cb)
        self.sprocess.stderr.read_until_close(streaming_callback=self.stderr_read_cb)


def run_process():
    process = Process(sys.argv[1:])
    process.run()

if __name__ == "__main__":
    run_process()
