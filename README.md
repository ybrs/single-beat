Single-beat
---------
Single-beat is a nice little application that ensures only one instance of your process runs across your servers.

Such as celerybeat (or some kind of daily mail sender, orphan file cleaner etc...) needs to be running only on one server,
but if that server gets down, well, you go and start it at another server etc. 

As we all hate manually doing things, single-beat automates this process.


How
---------

We use redis as a lock server, and wrap your process with single-beat, in two servers,

```bash
single-beat celery beat
```

on the second server

```bash
single-beat celery beat
```

on the third server

```bash
single-beat celery beat
```

The second process will just wait until the first one dies etc.

Installation
------------

```bash
sudo pip install single-beat
```

Configuration
-------------

You can configure single-beat with environment variables, like

```bash
SINGLE_BEAT_REDIS_SERVER='redis://redis-host:6379/1' single-beat celery beat
```

- SINGLE_BEAT_REDIS_SERVER

    you can give redis host url, we pass it to from_url of [redis-py](http://redis-py.readthedocs.org/en/latest/#redis.StrictRedis.from_url)

- SINGLE_BEAT_REDIS_SENTINEL

    use redis sentinel to select the redis host to use, sentinels are defined as colon-separated list of hostname and port pairs, e.g. `192.168.1.10:26379;192.168.1.11:26379;192.168.1.12:26379`

- SINGLE_BEAT_REDIS_SENTINEL_MASTER (default `mymaster`)
- SINGLE_BEAT_REDIS_SENTINEL_DB (default 0)
- SINGLE_BEAT_IDENTIFIER

    the default is we use your process name as the identifier, like

    ```bash
    single-beat celery beat
    ```

    all processes checks a key named, SINGLE_BEAT_celery but in some cases you might need to give another identifier, eg. your project name etc.

    ```bash
    SINGLE_BEAT_IDENTIFIER='celery-beat' single-beat celery beat
    ```

- SINGLE_BEAT_LOCK_TIME (default 5 seconds)
- SINGLE_BEAT_INITIAL_LOCK_TIME (default 2 * SINGLE_BEAT_LOCK_TIME seconds)
- SINGLE_BEAT_HEARTBEAT_INTERVAL (default 1 second)

    when starting your process, we set a key with 10 second expiration (INITIAL_LOCK_TIME) in redis server, 
    other single-beat processes checks if that key exists - if it exists they won't spawn children. 
    
    We continue to update that key every 1 second (HEARTBEAT_INTERVAL) setting it with a ttl of 5 seconds (LOCK_TIME)

    This should work, but you might want to give more relaxed intervals, like:

    ```bash
    SINGLE_BEAT_LOCK_TIME=300 SINGLE_BEAT_HEARTBEAT_INTERVAL=60 single-beat celery beat
    ```

- SINGLE_BEAT_HOST_IDENTIFIER (default socket.gethostname)

    we set the name of the host and the process id as lock keys value, so you can check where your process lives.

    ```bash
    SINGLE_BEAT_IDENTIFIER='celery-beat' single-beat celery beat
    ```

    ```bash
    (env)$ redis-cli
    redis 127.0.0.1:6379> keys *
    1) "_kombu.binding.celeryev"
    2) "celery"
    3) "_kombu.binding.celery"
    4) "SINGLE_BEAT_celery-beat"
    redis 127.0.0.1:6379> get SINGLE_BEAT_celery-beat
    "0:aybarss-MacBook-Air.local:43213"
    redis 127.0.0.1:6379>
    ```

    ```bash
    SINGLE_BEAT_HOST_IDENTIFIER='192.168.1.1' SINGLE_BEAT_IDENTIFIER='celery-beat' single-beat celery beat
    ```

    ```bash
    (env)$ redis-cli
    redis 127.0.0.1:6379> keys *
    1) "SINGLE_BEAT_celery-beat"
    redis 127.0.0.1:6379> get SINGLE_BEAT_celery-beat
    "0:192.168.1.1:43597"
    ```

- SINGLE_BEAT_LOG_LEVEL (default warn)

    change log level to debug if you want to see the heartbeat messages.

- SINGLE_BEAT_WAIT_MODE (default heartbeat)
- SINGLE_BEAT_WAIT_BEFORE_DIE (default 60 seconds)
    
    singlebeat has two different modes:
        - heartbeat (default)
        - supervised
    
    In heartbeat mode, single-beat is responsible for everything, spawning a process checking its status, publishing etc.
    In supervised mode, single-beat starts, checks if the child is running somewhere and waits for a while and then exits. So supervisord - or another scheduler picks up and restarts single-beat.

    on first server

    ```bash
    SINGLE_BEAT_LOG_LEVEL=debug SINGLE_BEAT_WAIT_MODE=supervised SINGLE_BEAT_WAIT_BEFORE_DIE=10 SINGLE_BEAT_IDENTIFIER='celery-beat' single-beat celery beat -A example.tasks
    DEBUG:singlebeat.beat:timer called 0.100841999054 state=WAITING
    [2014-05-05 16:28:24,099: INFO/MainProcess] beat: Starting...
    DEBUG:singlebeat.beat:timer called 0.999553918839 state=RUNNING
    DEBUG:singlebeat.beat:timer called 1.00173187256 state=RUNNING
    DEBUG:singlebeat.beat:timer called 1.00134801865 state=RUNNING
    ```

    this will heartbeat every second, on your second server

    ```bash
    SINGLE_BEAT_LOG_LEVEL=debug SINGLE_BEAT_WAIT_MODE=supervised SINGLE_BEAT_WAIT_BEFORE_DIE=10 SINGLE_BEAT_IDENTIFIER='celery-beat' single-beat celery beat -A example.tasks
    DEBUG:singlebeat.beat:timer called 0.101243019104 state=WAITING
    DEBUG:root:already running, will exit after 60 seconds
    ```

    so if you do this in your supervisor.conf

    ```bash
    [program:celerybeat]
    environment=SINGLE_BEAT_IDENTIFIER="celery-beat",SINGLE_BEAT_REDIS_SERVER="redis://localhost:6379/0",SINGLE_BEAT_WAIT_MODE="supervised", SINGLE_BEAT_WAIT_BEFORE_DIE=10
    command=single-beat celery beat -A example.tasks
    numprocs=1
    stdout_logfile=./logs/celerybeat.log
    stderr_logfile=./logs/celerybeat.err
    autostart=true
    autorestart=true
    startsecs=10
    ```

    it will try to spawn celerybeat every 60 seconds.

Cli
-------------
Single-beat also has a simple cli, that gives info about where your process is living - also can pause single-beat, restart your process etc.

"info" will show where the process is running, the first node identifier is the ip address connecting to redis - by default.

```
(venv3) $ SINGLE_BEAT_IDENTIFIER=echo SINGLE_BEAT_LOG_LEVEL=critical SINGLE_BEAT_REDIS_SERVER=127.0.0.1 single-beat-cli info
127.0.0.1:95779 | WAITING |
127.0.0.1:95776 | RUNNING | pid: 95778
127.0.0.1:95784 | WAITING |
```


"stop", will stop your child process, so any node will pick it up again

```
(venv3) $ SINGLE_BEAT_IDENTIFIER=echo SINGLE_BEAT_LOG_LEVEL=critical SINGLE_BEAT_REDIS_SERVER=127.0.0.1 single-beat-cli stop
127.0.0.1:95776 | PAUSED | killed
127.0.0.1:95779 | WAITING |
127.0.0.1:95784 | WAITING |

(venv3) $ SINGLE_BEAT_IDENTIFIER=echo SINGLE_BEAT_LOG_LEVEL=critical SINGLE_BEAT_REDIS_SERVER=127.0.0.1 single-beat-cli info
127.0.0.1:95776 | WAITING |
127.0.0.1:95779 | WAITING |
127.0.0.1:95784 | RUNNING | pid: 95877
```

"restart" will restart the child process in the active node.

```
(venv3) $ SINGLE_BEAT_IDENTIFIER=echo SINGLE_BEAT_LOG_LEVEL=critical SINGLE_BEAT_REDIS_SERVER=127.0.0.1 single-beat-cli info
127.0.0.1:95776 | WAITING |
127.0.0.1:95779 | WAITING |
127.0.0.1:95784 | RUNNING | pid: 95877

(venv3) $ SINGLE_BEAT_IDENTIFIER=echo SINGLE_BEAT_LOG_LEVEL=critical SINGLE_BEAT_REDIS_SERVER=127.0.0.1 single-beat-cli restart
127.0.0.1:95776 | WAITING |
127.0.0.1:95779 | WAITING |
127.0.0.1:95784 | RESTARTING | killed

(venv3) $ SINGLE_BEAT_IDENTIFIER=echo SINGLE_BEAT_LOG_LEVEL=critical SINGLE_BEAT_REDIS_SERVER=127.0.0.1 single-beat-cli info
127.0.0.1:95776 | WAITING |
127.0.0.1:95779 | WAITING |
127.0.0.1:95784 | RUNNING | pid: 95905
```


"pause" will kill the child, and put all single-beat nodes in pause state. This is useful for when deploying, to ensure that no "old version of the code"
is running while the deploy process is in place. after the deploy you can "resume" so any node will pick the child.

```
(venv3) $ SINGLE_BEAT_IDENTIFIER=echo SINGLE_BEAT_LOG_LEVEL=critical SINGLE_BEAT_REDIS_SERVER=127.0.0.1 single-beat-cli info
127.0.0.1:95776 | WAITING |
127.0.0.1:95779 | WAITING |
127.0.0.1:95784 | RUNNING | pid: 95905

(venv3) $ SINGLE_BEAT_IDENTIFIER=echo SINGLE_BEAT_LOG_LEVEL=critical SINGLE_BEAT_REDIS_SERVER=127.0.0.1 single-beat-cli pause
127.0.0.1:95776 | PAUSED |
127.0.0.1:95779 | PAUSED |
127.0.0.1:95784 | PAUSED | killed

(venv3) $ SINGLE_BEAT_IDENTIFIER=echo SINGLE_BEAT_LOG_LEVEL=critical SINGLE_BEAT_REDIS_SERVER=127.0.0.1 single-beat-cli info
127.0.0.1:95776 | PAUSED |
127.0.0.1:95779 | PAUSED |
127.0.0.1:95784 | PAUSED |
```

"resume" will put single-beat nodes in waiting state - so any node will pick up the child

```
(venv3) $ SINGLE_BEAT_IDENTIFIER=echo SINGLE_BEAT_LOG_LEVEL=critical SINGLE_BEAT_REDIS_SERVER=127.0.0.1 single-beat-cli info
127.0.0.1:95776 | PAUSED |
127.0.0.1:95779 | PAUSED |
127.0.0.1:95784 | PAUSED |

(venv3) $ SINGLE_BEAT_IDENTIFIER=echo SINGLE_BEAT_LOG_LEVEL=critical SINGLE_BEAT_REDIS_SERVER=127.0.0.1 single-beat-cli resume
127.0.0.1:95776 | WAITING |
127.0.0.1:95784 | WAITING |
127.0.0.1:95779 | WAITING |

(venv3) $ SINGLE_BEAT_IDENTIFIER=echo SINGLE_BEAT_LOG_LEVEL=critical SINGLE_BEAT_REDIS_SERVER=127.0.0.1 single-beat-cli info
127.0.0.1:95776 | WAITING |
127.0.0.1:95784 | WAITING |
127.0.0.1:95779 | RUNNING | pid: 96025
```


"quit" will terminate all child processes and then the parent process itself. So there will be no live single-beat nodes. Its useful to
have some sort of hand-brake - also might be useful when you have blue/green, or canary style deployments.

```
(venv3) $ SINGLE_BEAT_IDENTIFIER=echo SINGLE_BEAT_LOG_LEVEL=critical SINGLE_BEAT_REDIS_SERVER=127.0.0.1 single-beat-cli quit
127.0.0.1:95784 | RUNNING |

(venv3) $
(venv3) $ SINGLE_BEAT_IDENTIFIER=echo SINGLE_BEAT_LOG_LEVEL=critical SINGLE_BEAT_REDIS_SERVER=127.0.0.1 single-beat-cli info
```


Usage Patterns
--------------

You can see an example usage with supervisor at example/celerybeat.conf

Why
--------

There are some other solutions but either they are either complicated, or you need to modify the process. And I couldn't find a simpler solution for this https://github.com/celery/celery/issues/251 without modifying or adding locks to my tasks.

You can also check uWsgi's [Legion Support](http://uwsgi-docs.readthedocs.org/en/latest/AttachingDaemons.html#legion-support) which can do the same thing.

Credits
----------
 * [ybrs](https://github.com/ybrs)
 * [edmund-wagner](https://github.com/edmund-wagner)
 * [lowks](https://github.com/lowks)
 * [rangermeier](https://github.com/rangermeier)
 * [joekohlsdorf](https://github.com/joekohlsdorf)

 