import os
import sys
import time
import socket
import redis
from redis.sentinel import Sentinel
import logging
import signal
import tornado.ioloop
import tornado.process
import subprocess

def noop(i):
    return i

def env(identifier, default, type=noop):
    return type(os.getenv('SINGLE_BEAT_%s' % identifier, default))

class Config(object):
    REDIS_SERVER = env('REDIS_SERVER', 'redis://localhost:6379')
    REDIS_SENTINEL = env('REDIS_SENTINEL', None)
    REDIS_SENTINEL_MASTER = env('REDIS_SENTINEL_MASTER', 'mymaster')
    REDIS_SENTINEL_DB = env('REDIS_SENTINEL_DB', 0)
    IDENTIFIER = env('IDENTIFIER', None)
    LOCK_TIME = env('LOCK_TIME', 5, int)
    INITIAL_LOCK_TIME = env('INITIAL_LOCK_TIME', LOCK_TIME * 2, int)
    HEARTBEAT_INTERVAL = env('HEARTBEAT_INTERVAL', 1, int)
    HOST_IDENTIFIER = env('HOST_IDENTIFIER', socket.gethostname())
    LOG_LEVEL = env('LOG_LEVEL', 'warn')
    # wait_mode can be, supervisored or heartbeat
    WAIT_MODE = env('WAIT_MODE', 'heartbeat')
    WAIT_BEFORE_DIE = env('WAIT_BEFORE_DIE', 60, int)

    def check(self, cond, message):
        if not cond:
            raise Exception(message)

    def checks(self):
        self.check(self.LOCK_TIME < self.INITIAL_LOCK_TIME, "inital lock time must be greater than lock time")
        self.check(self.HEARTBEAT_INTERVAL < (self.LOCK_TIME / 2.0), "SINGLE_BEAT_HEARTBEAT_INTERVAL must be smaller than SINGLE_BEAT_LOCK_TIME / 2")
        self.check(self.WAIT_MODE in ('supervised', 'heartbeat'), 'undefined wait mode')

config = Config()
config.checks()

numeric_log_level = getattr(logging, config.LOG_LEVEL.upper(), None)
logging.basicConfig(level=numeric_log_level)
logger = logging.getLogger(__name__)

if config.REDIS_SENTINEL:
    sentinels = [tuple(s.split(':')) for s in config.REDIS_SENTINEL.split(';')]
    sentinel = redis.sentinel.Sentinel(sentinels,
                                       db=config.REDIS_SENTINEL_DB,
                                       socket_timeout=0.1)
    master = sentinel.discover_master(config.REDIS_SENTINEL_MASTER)
    logger.debug('master: {}'.format(master))
else:
    rds = redis.Redis.from_url(config.REDIS_SERVER)
    rds.ping()


def get_process_identifier(args):
    """by looking at arguments we try to generate a proper identifier
        >>> get_process_identifier(['python', 'echo.py', '1'])
        'python_echo.py_1'
    """
    return '_'.join(args)


class Process(object):
    def __init__(self, args):
        self.args = args
        self.state = None
        self.t1 = time.time()

        self.identifier = config.IDENTIFIER or get_process_identifier(self.args[1:])

        signal.signal(signal.SIGTERM, self.sigterm_handler)
        signal.signal(signal.SIGINT, self.sigterm_handler)

        self.sprocess = None
        self.pc = None
        self.state = 'WAITING'
        self.ioloop = tornado.ioloop.IOLoop.instance()

    def proc_exit_cb(self, exit_status):
        """When child exits we use the same exit status code"""
        sys.exit(exit_status)

    def stdout_read_cb(self, data):
        sys.stdout.write(data)

    def stderr_read_cb(self, data):
        sys.stdout.write(data)

    def timer_cb_waiting(self):
        if self.acquire_lock():
            return self.spawn_process()
        # couldnt acquire lock
        if config.WAIT_MODE == 'supervised':
            logging.debug("already running, will exit after %s seconds"
                          % config.WAIT_BEFORE_DIE)
            time.sleep(config.WAIT_BEFORE_DIE)
            sys.exit()

    def timer_cb_running(self):
        rds = self.get_client()
        rds.set("SINGLE_BEAT_{identifier}".format(identifier=self.identifier),
                "{host_identifier}:{pid}".format(host_identifier=config.HOST_IDENTIFIER,
                                                 pid=self.sprocess.pid),
                ex=config.LOCK_TIME)

    def get_client(self):
        if config.REDIS_SENTINEL:
            return sentinel.master_for(config.REDIS_SENTINEL_MASTER,
                                       redis_class=redis.Redis)
        return rds

    def timer_cb(self):
        logger.debug("timer called %s state=%s",
                     time.time() - self.t1, self.state)
        self.t1 = time.time()
        fn = getattr(self, 'timer_cb_{}'.format(self.state.lower()))
        fn()

    def acquire_lock(self):
        rds = self.get_client()
        return rds.execute_command('SET', 'SINGLE_BEAT_%s' % self.identifier,
                                   "%s:%s" % (config.HOST_IDENTIFIER, '0'),
                                   'NX', 'EX', config.INITIAL_LOCK_TIME)

    def sigterm_handler(self, signum, frame):
        """ When we get term signal
        if we are waiting and got a sigterm, we just exit.
        if we have a child running, we pass the signal first to the child
        then we exit.

        :param signum:
        :param frame:
        :return:
        """
        assert(self.state in ('WAITING', 'RUNNING'))
        logging.debug("our state %s", self.state)
        if self.state == 'WAITING':
            return self.ioloop.stop()

        if self.state == 'RUNNING':
            logger.debug('already running sending signal to child - %s',
                         self.sprocess.pid)
            os.kill(self.sprocess.pid, signum)
        self.ioloop.stop()

    def run(self):
        self.pc = tornado.ioloop.PeriodicCallback(self.timer_cb, config.HEARTBEAT_INTERVAL * 1000)
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
