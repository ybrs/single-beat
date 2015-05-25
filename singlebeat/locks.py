import socket
import os
import logging
logger = logging.getLogger(__name__)

LOCK = None

HOST_IDENTIFIER = os.environ.get('SINGLE_BEAT_HOST_IDENTIFIER',
                                 socket.gethostname())

LOCK_TIME = os.environ.get('SINGLE_BEAT_LOCK_TIME')
INITIAL_LOCK_TIME = os.environ.get('SINGLE_BEAT_INITIAL_LOCK_TIME')
HEARTBEAT_INTERVAL = os.environ.get('SINGLE_BEAT_HEARTBEAT_INTERVAL')

REDIS_SERVER = os.environ.get('SINGLE_BEAT_REDIS_SERVER')
POSTGRES_SERVER = os.environ.get('SINGLE_BEAT_POSTGRES_SERVER')
MONGO_SERVER = os.environ.get('SINGLE_BEAT_MONGO_SERVER')
MEMCACHED_SERVERS = os.environ.get('SINGLE_BEAT_MEMCACHED_SERVER')


class Lock(object):

    @property
    def lock_key(self):
        return 'SINGLE_BEAT_%s' % self.identifier

    def acquire_lock(self, identifier):
        raise NotImplementedError
    def refresh_lock(self, identifier, pid):
        raise NotImplementedError


class RedisLock(Lock):
    def __init__(self, server_uri, *args):
        self.lock_time = int( LOCK_TIME or 1 )
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
        self.lock_time = int( LOCK_TIME or 1 )
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



class PostgresLock(Lock):
    def __init__(self, server_uri):
        self.lock_time = int( LOCK_TIME or 20 )
        self.heartbeat_interval = int(HEARTBEAT_INTERVAL or 10)
        self.server_uri = server_uri
        import psycopg2
        conn = psycopg2.connect(self.server_uri)
        cur = conn.cursor()
        cur.execute( ("CREATE TABLE IF NOT EXISTS single_beat_lock (key varchar PRIMARY KEY, "
                                                               "  value varchar, "
                                                               "  last_check_in timestamp);") )
        conn.commit()
        cur.close()
        self.conn = conn

    def acquire_lock(self):
        print "Trying to acquire lock..."
        value = "%s:%s" % (HOST_IDENTIFIER, '0')
        data ={'key': self.lock_key, 'value': value}
        query =  (" DELETE FROM single_beat_lock "
                        " WHERE (current_timestamp - last_check_in) > INTERVAL '{lock_time} seconds' ; "
                        " SELECT key, value,  (current_timestamp - last_check_in) as diff "
                        " FROM single_beat_lock WHERE key = %(key)s").format(lock_time=self.lock_time)
        cur = self.conn.cursor()
        cur.execute(query, data)
        lock_held = cur.fetchone()
        success = None
        if lock_held:
            print "Lock already held"
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
        print "REFRESHING"
        query = ("UPDATE single_beat_lock SET value = %(value)s , last_check_in = current_timestamp "
                       " WHERE key= %(key)s")
        cur = self.conn.cursor()
        cur.execute(query, {'key': self.lock_key, 'value': value})
        self.conn.commit()
        cur.close()
        return True


class RabbitMQLock(Lock):
    def __iniit__(self, server_uri):
        self.server_uri = server_uri
        import pika
        connection = pika.BlockingConnection(pika.ConnectionParameters('localhost'))
        channel = connection.channel()
        channel.exchange_declare(exchange='single-beat', type='fanout')

    def acquire_lock(self, identifier):
        return False

    def refresh_lock(self, identifier, pid):
        return False


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
elif POSTGRES_SERVER:
    LOCK = PostgresLock(POSTGRES_SERVER)
elif MONGO_SERVER:
    LOCK = MongoLock(MONGO_SERVER)
else:
    LOCK = RedisLock('redis://localhost:6379')
    #TODO: try catch redis lock....then try catch memcache lock as defaults
    #LOCK = MemcacheLock('127.0.0.1:11211')




