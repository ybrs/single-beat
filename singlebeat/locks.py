import socket
import os
import logging
import sys
logger = logging.getLogger(__name__)

LOCK = None

ARGS = sys.argv[1:]
IDENTIFIER = os.environ.get('SINGLE_BEAT_IDENTIFIER') or ARGS[0]
HOST_IDENTIFIER = os.environ.get('SINGLE_BEAT_HOST_IDENTIFIER',
                                 socket.gethostname())

LOCK_TIME = os.environ.get('SINGLE_BEAT_LOCK_TIME')
INITIAL_LOCK_TIME = os.environ.get('SINGLE_BEAT_INITIAL_LOCK_TIME')
HEARTBEAT_INTERVAL = os.environ.get('SINGLE_BEAT_HEARTBEAT_INTERVAL')

RABBITMQ_SERVER = os.environ.get('SINGLE_BEAT_RABBITMQ_SERVER')
REDIS_SERVER = os.environ.get('SINGLE_BEAT_REDIS_SERVER')
POSTGRES_SERVER = os.environ.get('SINGLE_BEAT_POSTGRES_SERVER')
MONGO_SERVER = os.environ.get('SINGLE_BEAT_MONGO_SERVER')
MEMCACHED_SERVERS = os.environ.get('SINGLE_BEAT_MEMCACHED_SERVER')


class Lock(object):

    @property
    def lock_key(self):
        return 'SINGLE_BEAT_%s' % self.identifier or IDENTIFIER

    def acquire_lock(self, identifier):
        raise NotImplementedError

    def refresh_lock(self, identifier, pid):
        raise NotImplementedError


class RedisLock(Lock):
    def __init__(self, server_uri, *args):
        self.lock_time = int(LOCK_TIME or 1)
        self.initial_lock_time = int(INITIAL_LOCK_TIME or (self.lock_time * 2))
        self.heartbeat_interval = int(HEARTBEAT_INTERVAL or 1)
        self.server_uri = server_uri
        import redis
        self.rds = redis.Redis.from_url(REDIS_SERVER)
        self.rds.ping()

    def acquire_lock(self, identifier):
        value = "%s:%s" % (HOST_IDENTIFIER, '0')
        return self.rds.execute_command('SET', self.lock_key, value, 'NX', 'EX', self.initial_lock_time)

    def refresh_lock(self, identifier, pid):
        value = "%s:%s" % (HOST_IDENTIFIER, pid)
        return self.rds.set(self.lock_key, value, ex=self.lock_time)


class MemcacheLock(Lock):
    def __init__(self, server_uri, *args):
        self.lock_time = int(LOCK_TIME or 1)
        self.initial_lock_time = int(INITIAL_LOCK_TIME or (self.lock_time * 2))
        self.heartbeat_interval = int(HEARTBEAT_INTERVAL or 1)
        self.server_uri = server_uri.split(',')
        import memcache
        self.mc = memcache.Client(self.server_uri)

    def acquire_lock(self, identifier):
        value = "%s:%s" % (HOST_IDENTIFIER, '0')
        return self.rds.execute_command('SET', self.lock_key, value, 'NX', 'EX', self.initial_lock_time)

    def refresh_lock(self, identifier, pid):
        value = "%s:%s" % (HOST_IDENTIFIER, pid)
        mc.set(self.lock_key, value, time=LOCK_TIME)
        return True


class RabbitMQLock(Lock):

    def __init__(self, server_uri):
        self.identifier = IDENTIFIER
        self.lock_time = int(LOCK_TIME or 12)
        self.initial_lock_time = int(INITIAL_LOCK_TIME or (self.lock_time * 2))
        self.heartbeat_interval = int(HEARTBEAT_INTERVAL or 4)
        self.server_uri = server_uri
        self.args = {'x-message-ttl': self.lock_time * 100}
        import pika
        parameters = pika.URLParameters(self.server_uri)
        self.exchange = 'single-beat'
        self.connection = pika.BlockingConnection(parameters)
        self.channel = self.connection.channel()
        self.channel.exchange_declare(exchange=self.exchange, type='fanout')
        self.q = self.channel.queue_declare(exclusive=True, arguments=self.args)
        self.queue_name = self.q.method.queue
        result = self.channel.queue_bind(exchange=self.exchange,
                                         queue=self.queue_name,
                                         routing_key=self.lock_key)

    def acquire_lock(self):
        from time import sleep
        sleep(self.heartbeat_interval)
        method_frame, header_frame, body = self.channel.basic_get(self.queue_name)
        if not body:
            value = "%s:%s" % (HOST_IDENTIFIER, '0')
            self.channel.basic_publish(exchange=self.exchange,
                                       routing_key=self.lock_key,
                                       body=value)
            return True
        self.channel.queue_purge(self.queue_name)
        return False

    def refresh_lock(self, pid):
        value = "%s:%s" % (HOST_IDENTIFIER, pid)
        self.channel.basic_publish(exchange=self.exchange,
                                   routing_key=self.lock_key,
                                   body=value)
        return True


class PostgresLock(Lock):
    def __init__(self, server_uri):
        self.lock_time = int(LOCK_TIME or 20)
        self.heartbeat_interval = int(HEARTBEAT_INTERVAL or 10)
        self.server_uri = server_uri
        import psycopg2
        import urlparse  # import urllib.parse for python 3+
        result = urlparse.urlparse(server_uri)
        conn = psycopg2.connect(
            database=result.path[1:],
            user=result.username,
            password=result.password,
            host=result.hostname
        )
        # conn = psycopg2.connect(self.server_uri)
        cur = conn.cursor()
        cur.execute(("CREATE TABLE IF NOT EXISTS single_beat_lock (key varchar PRIMARY KEY, "
                     "  value varchar, "
                     "  last_check_in timestamp);"))
        conn.commit()
        cur.close()
        self.conn = conn

    def acquire_lock(self):
        value = "%s:%s" % (HOST_IDENTIFIER, '0')
        data = {'key': self.lock_key, 'value': value}
        query = (" DELETE FROM single_beat_lock "
                 " WHERE (current_timestamp - last_check_in) > INTERVAL '{lock_time} seconds' ; "
                 " SELECT key, value,  (current_timestamp - last_check_in) as diff "
                 " FROM single_beat_lock WHERE key = %(key)s").format(lock_time=self.lock_time)
        cur = self.conn.cursor()
        cur.execute(query, data)
        lock_held = cur.fetchone()
        success = None
        if lock_held:
            success = False
        else:
            query = ("INSERT INTO single_beat_lock (key, value, last_check_in) "
                     " VALUES (%(key)s, %(value)s, current_timestamp)")
            try:
                cur.execute(query, data)
                success = True
            except Exception as e:
                logger.error("ERROR: %s" % e)
                success = False
        self.conn.commit()
        cur.close()
        return success

    def refresh_lock(self, pid=None):
        pid = pid or 0
        value = "%s:%s" % (HOST_IDENTIFIER, pid)
        query = ("UPDATE single_beat_lock SET value = %(value)s , last_check_in = current_timestamp "
                 " WHERE key= %(key)s")
        cur = self.conn.cursor()
        cur.execute(query, {'key': self.lock_key, 'value': value})
        self.conn.commit()
        cur.close()
        return True


class MongoLock(Lock):
    def __init__(self, server_uri):
        self.server_uri = server_uri

    def acquire_lock(self, identifier):
        return False

    def refresh_lock(self, identifier, pid):
        return False


if REDIS_SERVER:
    LOCK = RedisLock(REDIS_SERVER)
elif MEMCACHED_SERVERS:
    LOCK = MemcacheLock(REDIS_SERVER)
elif RABBITMQ_SERVER:
    LOCK = RabbitMQLock(RABBITMQ_SERVER)
elif POSTGRES_SERVER:
    LOCK = PostgresLock(POSTGRES_SERVER)
elif MONGO_SERVER:
    LOCK = MongoLock(MONGO_SERVER)
else:
    LOCK = RedisLock('redis://localhost:6379')
    # TODO: try catch redis lock....then try catch memcache lock as defaults
    # LOCK = MemcacheLock('127.0.0.1:11211')
