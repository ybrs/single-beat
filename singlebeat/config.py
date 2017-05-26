import os
import socket

def noop(i):
    return i

def env(identifier, default, type=noop):
    return type(os.getenv('SINGLE_BEAT_%s' % identifier, default))


class Config(object):
    REDIS_SERVER = env('REDIS_SERVER', 'redis://localhost:6379')
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
