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

from tornado import gen
from config import Config

config = Config()
config.checks()

numeric_log_level = getattr(logging, config.LOG_LEVEL.upper(), None)
logging.basicConfig(level=numeric_log_level)
logger = logging.getLogger(__name__)

rds = redis.Redis.from_url(config.REDIS_SERVER)
rds.ping()

from toredis import Client
host, port = config.REDIS_SERVER.replace('redis://', '').split(':')
tredis_client = Client()
tredis_client.connect(host=host, port=int(port))


def get_process_identifier(args):
    """by looking at arguments we try to generate a proper identifier
        >>> get_process_identifier(['python', 'echo.py', '1'])
        'python_echo.py_1'
    """
    return '_'.join(args)

class State(object):
    PAUSED = 'paused'
    WAITING = 'waiting'
    RUNNING = 'running'

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
        self.state = State.WAITING
        self.ioloop = tornado.ioloop.IOLoop.instance()
        self.ioloop.spawn_callback(self.wait_for_commands)
        self.log_tail = None
        #
        self.tail_channel_name = 'SINGLE_BEAT_TAIL_{}'.format(config.IDENTIFIER)
        logger.debug("tail channel name - %s", self.tail_channel_name)

    def command_start_tail(self):
        self.log_tail = True

    def command_stop_tail(self):
        self.log_tail = False

    def command_start(self):
        if self.sprocess and self.sprocess.pid:
            self.state = State.RUNNING
        else:
            self.state = State.WAITING

    def command_pause(self):
        """pause, pauses respawning the command in all the single-beat instances,
        so if you pause a command, well it will be paused until its started
        :return:
        """
        self.state = State.PAUSED

    def command_stop(self):
        """ stops the running command, it will respawn in another instance of single-beat
        we dont want to exit when we kill the child, we want single-beat to live but child to exit.
        so we remove exit_callback here.

        :return:
        """
        if not (self.sprocess and self.sprocess.pid):
            return

        def exit_cb(*args, **kwargs):
            self.sprocess = None
            if self.state == State.PAUSED:
                # if we are paused we dont want to restart it
                self.state = State.PAUSED
                return
            self.state = State.WAITING

        self.sprocess.set_exit_callback(exit_cb)
        os.kill(self.sprocess.pid, signal.SIGTERM)

    def command_pid(self):
        print("pid", self.sprocess.pid)

    def pubsub_callback(self, msg):
        if msg[0] != 'message':
            return

        fn = getattr(self, 'command_{}'.format(msg[2]), None)
        if fn:
            logger.debug("got command - %s running %s", msg[2], fn)
            fn()


    @gen.coroutine
    def wait_for_commands(self):
        # while True:
            # command = yield gen.Task(tredis_client.blpop, 'single_beat_client_1', 5)
            # print("command", command)
            # print("hello")
            # response = yield gen.Task(tredis_client.subscribe, "foobar")
        # response = tredis_client.subscribe "foobar")
        # print(response)
        tredis_client.subscribe('SB_{}'.format(config.IDENTIFIER), self.pubsub_callback)
        logger.debug('subcribed to redis channel %s', 'SB_{}'.format(config.IDENTIFIER))
            # print("response")

    def proc_exit_cb(self, exit_status):
        """When child exits we use the same exit status code"""
        sys.exit(exit_status)

    def stdout_read_cb(self, data):
        sys.stdout.write(data)
        if self.log_tail:
           rds.publish(self.tail_channel_name, data)

    def stderr_read_cb(self, data):
        sys.stderr.write(data)
        if self.log_tail:
            rds.publish(self.tail_channel_name, data)

    def publish_process(self):
        rds.set("SINGLE_BEAT_{identifier}".format(identifier=self.identifier),
                "{host_identifier}:{pid}".format(host_identifier=config.HOST_IDENTIFIER,
                                                 pid=self.sprocess.pid),
                ex=config.LOCK_TIME)

    def timer_cb_paused(self):
        if self.sprocess and self.sprocess.pid:
            self.publish_process()

    def timer_cb_waiting(self):
        if self.state == State.PAUSED:
            # if we are paused, don't try to do anything.
            return

        if self.acquire_lock():
            return self.spawn_process()

        # couldnt acquire lock
        if config.WAIT_MODE == 'supervised':
            logging.debug("already running, will exit after %s seconds"
                          % config.WAIT_BEFORE_DIE)
            time.sleep(config.WAIT_BEFORE_DIE)
            sys.exit()

    def timer_cb_running(self):
        if self.sprocess.pid:
            self.publish_process()

    def timer_cb(self):
        logger.debug("timer called %s state=%s",
                     time.time() - self.t1, self.state)
        self.t1 = time.time()
        fn = getattr(self, 'timer_cb_{}'.format(self.state.lower()))
        fn()

    def acquire_lock(self):
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
        assert(self.state in (State.WAITING, State.RUNNING, State.PAUSED))
        logging.debug("our state %s", self.state)
        if self.state == State.WAITING:
            return self.ioloop.stop()

        if self.state == State.RUNNING:
            logger.debug('already running sending signal to child - %s',
                         self.sprocess.pid)
            os.kill(self.sprocess.pid, signum)

        if self.state == State.PAUSED:
            # TODO:
            pass

        self.ioloop.stop()

    def run(self):
        rds.sadd('SINGLE_BEAT_IDENTIFIERS', self.identifier)
        self.pc = tornado.ioloop.PeriodicCallback(self.timer_cb, config.HEARTBEAT_INTERVAL * 1000)
        self.pc.start()
        self.ioloop.start()

    def spawn_process(self):
        STREAM = tornado.process.Subprocess.STREAM
        cmd = sys.argv[1:]
        env = os.environ

        self.state = State.RUNNING

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
