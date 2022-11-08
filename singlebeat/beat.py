import codecs
import functools
import json
import os
import sys
import time
import socket
import redis
import logging
import signal
import asyncio
from redis import asyncio as aioredis


def noop(i):
    return i


def env(identifier, default, type=noop):
    return type(os.getenv("SINGLE_BEAT_%s" % identifier, default))


class Config(object):
    REDIS_SERVER = env('REDIS_SERVER', 'redis://localhost:6379')
    REDIS_PASSWORD = env('REDIS_PASSWORD', None)
    REDIS_SENTINEL = env('REDIS_SENTINEL', None)
    REDIS_SENTINEL_MASTER = env('REDIS_SENTINEL_MASTER', 'mymaster')
    REDIS_SENTINEL_DB = env('REDIS_SENTINEL_DB', 0)
    REDIS_SENTINEL_PASSWORD = env('REDIS_SENTINEL_PASSWORD', None)
    IDENTIFIER = env('IDENTIFIER', None)
    LOCK_TIME = env('LOCK_TIME', 5, int)
    INITIAL_LOCK_TIME = env('INITIAL_LOCK_TIME', LOCK_TIME * 2, int)
    HEARTBEAT_INTERVAL = env('HEARTBEAT_INTERVAL', 1, int)
    HOST_IDENTIFIER = env('HOST_IDENTIFIER', socket.gethostname())
    LOG_LEVEL = env('LOG_LEVEL', 'warn')
    # wait_mode can be, supervisord or heartbeat
    WAIT_MODE = env("WAIT_MODE", "heartbeat")
    WAIT_BEFORE_DIE = env("WAIT_BEFORE_DIE", 60, int)
    _host_identifier = None

    def check(self, cond, message):
        if not cond:
            raise Exception(message)

    def checks(self):
        self.check(
            self.LOCK_TIME < self.INITIAL_LOCK_TIME,
            "initial lock time must be greater than lock time",
        )
        self.check(
            self.HEARTBEAT_INTERVAL < (self.LOCK_TIME / 2.0),
            "SINGLE_BEAT_HEARTBEAT_INTERVAL must be smaller than SINGLE_BEAT_LOCK_TIME / 2",
        )
        self.check(self.WAIT_MODE in ("supervised", "heartbeat"), "undefined wait mode")
        if self.REDIS_SENTINEL:
            master = self._sentinel.discover_master(self.REDIS_SENTINEL_MASTER)
        else:
            self._redis.ping()

    def get_redis(self):
        if self.REDIS_SENTINEL:
            return self._sentinel.master_for(self.REDIS_SENTINEL_MASTER,
                                             password=self.REDIS_PASSWORD,
                                             redis_class=redis.Redis)
        return self._redis

    def rewrite_redis_url(self):
        """\
        if REDIS_SERVER is just an ip address, then we try to translate it to
        redis_url, redis://REDIS_SERVER so that it doesn't try to connect to
        localhost while you try to connect to another server
        :return:
        """
        if (
            self.REDIS_SERVER.startswith("unix://")
            or self.REDIS_SERVER.startswith("redis://")
            or self.REDIS_SERVER.startswith("rediss://")
        ):
            return self.REDIS_SERVER
        return "redis://{}/".format(self.REDIS_SERVER)

    def __init__(self):
        if self.REDIS_SENTINEL:
            sentinels = [tuple(s.split(':')) for s in self.REDIS_SENTINEL.split(';')]
            self._sentinel = redis.sentinel.Sentinel(sentinels,
                                                     db=self.REDIS_SENTINEL_DB,
                                                     socket_timeout=0.1,
                                                     sentinel_kwargs={"password": self.REDIS_SENTINEL_PASSWORD}
                                                     )
        else:
            self._redis = redis.Redis.from_url(self.rewrite_redis_url())

    def get_async_redis_client(self):
        conn = self.get_redis().connection_pool.get_connection("ping")
        host, port, password = conn.host, conn.port, conn.password
        r = aioredis.Redis(host=host, port=port, password=password)
        return r.pubsub()

    def get_host_identifier(self):
        """\
        we try to return IPADDR:PID form to identify where any singlebeat instance is
        running.

        :return:
        """
        if self._host_identifier:
            return self._host_identifier
        local_ip_addr = (
            self.get_redis()
            .connection_pool.get_connection("ping")
            ._sock.getsockname()[0]
        )
        self._host_identifier = "{}:{}".format(local_ip_addr, os.getpid())
        return self._host_identifier


config = Config()
config.checks()

numeric_log_level = getattr(logging, config.LOG_LEVEL.upper(), None)
logging.basicConfig(level=numeric_log_level)
logger = logging.getLogger(__name__)


def get_process_identifier(args):
    """by looking at arguments we try to generate a proper identifier
    >>> get_process_identifier(['python', 'echo.py', '1'])
    'python_echo.py_1'
    """
    return "_".join(args)


class State:
    PAUSED = "PAUSED"
    RUNNING = "RUNNING"
    WAITING = "WAITING"
    RESTARTING = "RESTARTING"


def is_process_alive(pid):
    try:
        os.kill(pid, 0)
        return True
    except:
        return False


class Process(object):
    def __init__(self, args):
        self.args = args
        self.state = None
        self.t1 = time.time()

        self.identifier = config.IDENTIFIER or get_process_identifier(self.args[1:])
        self.ioloop = asyncio.get_running_loop()

        for signame in {"SIGINT", "SIGTERM"}:
            sig = getattr(signal, signame)
            self.ioloop.add_signal_handler(
                sig, functools.partial(self.sigterm_handler, sig, self.ioloop)
            )

        self.async_redis = config.get_async_redis_client()
        self.fence_token = 0
        self.sprocess = None
        self.pc = None
        self.state = State.WAITING
        self._periodic_callback_running = True
        self.child_exit_cb = self.proc_exit_cb

    def proc_exit_cb(self, exit_status):
        """When child exits we use the same exit status code"""
        self._periodic_callback_running = False
        sys.exit(exit_status)

    def proc_exit_cb_noop(self, exit_status):
        """\
        when we deliberately restart/stop the child process,
        we don't want to exit ourselves, so we replace proc_exit_cb
        with a noop one when restarting
        :param exit_status:
        :return:
        """

    def proc_exit_cb_restart(self, exit_status):
        """\
        this is used when we restart the process,
        it re-triggers the start
        """
        self.ioloop.run_until_complete(self.spawn_process())

    def proc_exit_cb_state_set(self, exit_status):
        if self.state == State.PAUSED:
            self.state = State.WAITING

    def stdout_read_cb(self, data):
        sys.stdout.write(data)

    def stderr_read_cb(self, data):
        sys.stderr.write(data)

    async def timer_cb_paused(self):
        pass

    async def timer_cb_waiting(self):
        if self.acquire_lock():
            logger.info(f"acquired lock, {self.identifier} spawning child process")
            return self.ioloop.create_task(self.spawn_process())
        # couldn't acquire lock
        if config.WAIT_MODE == "supervised":
            logger.debug(
                "already running, will exit after %s seconds" % config.WAIT_BEFORE_DIE
            )
            time.sleep(config.WAIT_BEFORE_DIE)
            sys.exit()

    def process_pid(self):
        """\
        when we are restarting, we want to keep sending heart beat, so any other single-beat
        node will not pick it up.
        hence we need a process-id as an identifier - even for a short period of time.
        :return:
        """
        if self.sprocess:
            return self.sprocess.pid
        return -1

    async def timer_cb_running(self):
        rds = config.get_redis()
        # read current fence token
        redis_fence_token = rds.get(
            "SINGLE_BEAT_{identifier}".format(identifier=self.identifier)
        )

        if redis_fence_token:
            redis_fence_token = int(redis_fence_token.split(b":")[0])
        else:
            logger.error(
                "fence token could not be read from Redis - assuming lock expired, trying to reacquire lock"
            )
            if self.acquire_lock():
                logger.info("reacquired lock")
                redis_fence_token = self.fence_token
            else:
                logger.error("unable to reacquire lock, terminating")
                os.kill(os.getpid(), signal.SIGTERM)

        logger.debug(
            "expected fence token: {} fence token read from Redis: {}".format(
                self.fence_token, redis_fence_token
            )
        )

        if self.fence_token == redis_fence_token:
            self.fence_token += 1
            rds.set(
                "SINGLE_BEAT_{identifier}".format(identifier=self.identifier),
                "{}:{}:{}".format(
                    self.fence_token, config.HOST_IDENTIFIER, self.process_pid()
                ),
                ex=config.LOCK_TIME,
            )
        else:
            logger.error(
                "fence token did not match - lock is held by another process, terminating"
            )
            # send sigterm to ourself and let the sigterm_handler do the rest
            os.kill(os.getpid(), signal.SIGTERM)

    async def timer_cb_restarting(self):
        """\
        when restarting we are doing exactly the same as running - we don't want any other
        single-beat node to pick up
        :return:
        """
        await self.timer_cb_running()

    async def timer_cb(self):
        logger.debug("timer called %s state=%s", time.time() - self.t1, self.state)
        self.t1 = time.time()
        fn = getattr(self, "timer_cb_{}".format(self.state.lower()))
        await fn()

    def acquire_lock(self):
        rds = config.get_redis()
        return rds.execute_command(
            "SET",
            "SINGLE_BEAT_{}".format(self.identifier),
            "{}:{}:{}".format(self.fence_token, config.HOST_IDENTIFIER, 0),
            "NX",
            "EX",
            config.INITIAL_LOCK_TIME,
        )

    def sigterm_handler(self, signum, loop):
        """When we get term signal
        if we are waiting and got a sigterm, we just exit.
        if we have a child running, we pass the signal first to the child
        then we exit.

        To exit we signal our main sleep/trigger loop on `self.run()`

        :param signum:
        :param ioloop:
        :return:
        """
        assert self.state in ("WAITING", "RUNNING", "PAUSED")
        logger.debug("our state %s", self.state)
        if self.state == "WAITING":
            self._periodic_callback_running = False

        if self.state == "RUNNING":
            logger.debug(
                "already running sending signal to child - %s", self.sprocess.pid
            )
            self.sprocess.send_signal(signum)
            logger.debug("waiting for subprocess to finish")
            self.ioloop.create_task(self.sprocess.wait())
        self._periodic_callback_running = False

    async def run(self):
        while self._periodic_callback_running:
            await self.timer_cb()
            await asyncio.sleep(config.HEARTBEAT_INTERVAL)

    async def _read_stream(self, stream, cb):
        decoder = codecs.getincrementaldecoder('utf-8')(errors='strict')

        while True:
            line = await stream.read(100)
            if line:
                cb(decoder.decode(line))
            else:
                break

    async def spawn_process(self):
        cmd = self.args
        env = os.environ

        self.state = State.RUNNING
        try:
            self.sprocess = await asyncio.create_subprocess_exec(
                *cmd,
                env=env,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
        except FileNotFoundError:
            """
            if the file that we need to run doesn't exists
            we immediately exit.
            """
            logger.exception("file not found")
            return self.child_exit_cb(1)
        try:
            await asyncio.wait(
                [
                    asyncio.create_task(self._read_stream(self.sprocess.stdout, self.forward_stdout)),
                    asyncio.create_task(self._read_stream(self.sprocess.stderr, self.forward_stderr)),
                ]
            )
            self.child_exit_cb(self.sprocess.returncode)
        except SystemExit as e:
            os._exit(e.code)

    def cli_command_info(self, msg):
        info = ""
        if self.sprocess:
            if is_process_alive(self.sprocess.pid):
                info = "pid: {}".format(self.sprocess.pid)
        return info

    def child_process_alive(self):
        return not self.sprocess.protocol._process_exited

    def cli_command_quit(self, msg):
        """\
        kills the child and exits
        """
        if self.state == State.RUNNING and self.sprocess and self.child_process_alive():
            self.sprocess.kill()
        else:
            sys.exit(0)

    def cli_command_pause(self, msg):
        """\
        if we have a running child we kill it and set our state to paused
        if we don't have a running child, we set our state to paused
        this will pause all the nodes in single-beat cluster

        its useful when you deploy some code and don't want your child to spawn
        randomly

        :param msg:
        :return:
        """
        info = ""
        if self.state == State.RUNNING and self.sprocess and self.child_process_alive():
            self.child_exit_cb = self.proc_exit_cb_noop
            self.sprocess.kill()
            info = "killed"
            # TODO: check if process is really dead etc.
        self.state = State.PAUSED
        return info

    def cli_command_resume(self, msg):
        """\
        sets state to waiting - so we resume spawning children
        """
        if self.state == State.PAUSED:
            self.state = State.WAITING

    def cli_command_stop(self, msg):
        """\
        stops the running child process - if its running
        it will re-spawn in any single-beat node after sometime

        :param msg:
        :return:
        """
        info = ""
        if self.state == State.RUNNING and self.sprocess and self.sprocess.proc:
            self.state = State.PAUSED
            # TODO:
            # self.sprocess.set_exit_callback(self.proc_exit_cb_state_set)
            self.sprocess.kill()
            info = "killed"
            # TODO: check if process is really dead etc.
        return info

    def cli_command_restart(self, msg):
        """\
        restart the subprocess
        i. we set our state to RESTARTING - on restarting we still send heartbeat
        ii. we kill the subprocess
        iii. we start again
        iv. if its started we set our state to RUNNING, else we set it to WAITING

        :param msg:
        :return:
        """
        info = ""
        if self.state == State.RUNNING and self.sprocess and self.sprocess.proc:
            self.state = State.RESTARTING
            self.child_exit_cb = self.proc_exit_cb_restart
            self.sprocess.kill()
            info = "killed"
            # TODO: check if process is really dead etc.
        return info

    def pubsub_callback(self, msg):
        logger.info("got command - %s", msg)

        if msg["type"] != b"message":
            return

        try:
            cmd = json.loads(msg["data"])
        except:
            logger.exception("exception on parsing command %s", msg)
            return

        fn = getattr(self, "cli_command_{}".format(cmd["cmd"]), None)
        if not fn:
            logger.info("cli_command_{} not found".format(cmd["cmd"]))
            return

        logger.info("got command - %s running %s", msg["data"], fn)
        info = fn(cmd)
        rds = config.get_redis()
        logger.info("reply to %s", cmd["reply_channel"])
        rds.publish(
            cmd["reply_channel"],
            json.dumps(
                {
                    "identifier": config.get_host_identifier(),
                    "state": self.state,
                    "info": info or "",
                }
            ),
        )

    async def wait_for_commands(self):
        logger.info("subscribed to %s", "SB_{}".format(self.identifier))
        await self.async_redis.subscribe("SB_{}".format(self.identifier))
        logger.debug("subscribed to redis channel %s", "SB_{}".format(self.identifier))
        async for msg in self.async_redis.listen():
            self.pubsub_callback(msg)

    def forward_stdout(self, buf):
        self.stdout_read_cb(buf)

    def forward_stderr(self, buf):
        self.stderr_read_cb(buf)


async def run_process():
    process = Process(sys.argv[1:])
    await process.run()


def main():
    asyncio.run(run_process())


if __name__ == "__main__":
    main()

