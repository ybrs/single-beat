Single-beat
---------
Single-beat is a nice little application that ensures only one instance of your process runs across your servers.

Such as celerybeat (or some kind of daily mail sender, orphan file cleaner etc...) needs to be running only on one server,
but if that server gets down, well, you go and start it at another server etc. As we all hate manually doing things, single-beat automates this process.


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
- SINGLE_BEAT_HEARTBEAT_INTERVAL (default 1 second)

    when starting your process, we set a key with 5 second expiration (LOCK_TIME) in redis server, and other single-beat processes checks if that key exists. We continue to update that key every 1 second (HEARTBEAT_INTERVAL)

    this should work, but you might want to give more relaxed intervals, like:

    ```bash
    SINGLE_BEAT_LOCK_TIME=300 SINGLE_BEAT_HEARTBEAT_INTERVAL=60 single-beat celery beat
    ```

- SINGLE_BEAT_HOST_IDENTIFIER (default socket.gethostname)

    we set the name of the host and the process id as lock keys value, so you can check where does your process currently working.

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
    "aybarss-MacBook-Air.local:43213"
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
    "192.168.1.1:43597"
    ```

- SINGLE_BEAT_LOG_LEVEL (default warn)

    change log level to debug if you want to see the heartbeat messages.

- SINGLE_BEAT_WAIT_MODE (default heartbeat)
- SINGLE_BEAT_WAIT_BEFORE_DIE (default 60 seconds)

    instead of checking the process every second (heartbeat mode) you can put single beat into supervisor, and die after 60 seconds (SINGLE_BEAT_WAIT_BEFORE_DIE), so supervisor will respawn it again, single-beat will check if there is another process in the cluster, will wait for 60 seconds and die nicely, so supervisor will respawn it....

    easier to explain with code,

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
    environment=SINGLE_BEAT_IDENTIFIER="celery-beat",SINGLE_BEAT_REDIS_HOST="redis://localhost:6379/0",SINGLE_BEAT_WAIT_MODE="supervised", SINGLE_BEAT_WAIT_BEFORE_DIE=10
    command=single-beat celery beat -A example.tasks
    numprocs=1
    stdout_logfile=./logs/celerybeat.log
    stderr_logfile=./logs/celerybeat.err
    autostart=true
    autorestart=true
    startsecs=10
    ```

    it will try to spawn celerybeat every 60 seconds.

Usage Patterns
--------------

You can see an example usage with supervisor at example/celerybeat.conf

Why
--------

There are some other solutions but either they are either complicated, or you need to modify the process. And I couldn't find a simpler solution for this https://github.com/celery/celery/issues/251 without modifying or adding locks to my tasks.

You can also check uWsgi's [Legion Support](http://uwsgi-docs.readthedocs.org/en/latest/AttachingDaemons.html#legion-support) which can do the same thing.