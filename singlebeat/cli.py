#!/usr/bin/env python

from __future__ import unicode_literals

import logging

import redis
from prompt_toolkit.contrib.completers import WordCompleter
from prompt_toolkit import prompt
from prompt_toolkit.styles import style_from_dict
from prompt_toolkit.token import Token


from config import Config

config = Config()
config.checks()

numeric_log_level = getattr(logging, config.LOG_LEVEL.upper(), None)
logging.basicConfig(level=numeric_log_level)
logger = logging.getLogger(__name__)

rds = redis.Redis.from_url(config.REDIS_SERVER)
rds.ping()

cmds = {}
others = []

def command(fn):
    cmds[fn.__name__] = fn
    def wraps(*args, **kwargs):
        return fn(*args, **kwargs)
    return wraps

@command
def list():
    manages = rds.smembers('SINGLE_BEAT_IDENTIFIERS')
    return manages

@command
def kill():
    pass

@command
def tail():
    identifier = 'echo_running'
    rds.publish('SB_echo_running', 'start_tail')
    p = rds.pubsub()
    p.subscribe('SINGLE_BEAT_TAIL_{}'.format(identifier))
    for ln in p.listen():
        print(ln)

completer = WordCompleter(cmds.keys() + others, ignore_case=True)

test_style = style_from_dict({
    Token.Toolbar: '#ffffff bg:#333333',
})


def get_bottom_toolbar_tokens(cli):
    return [(Token.Toolbar, ' This is a toolbar. ')]

def main():
    while True:
        command = prompt('> ', 
                        completer=completer,
                         get_bottom_toolbar_tokens=get_bottom_toolbar_tokens,
                         style=test_style,
                        complete_while_typing=True)
        ret = cmds[command]()
        for l in ret:
            print(l)


if __name__ == '__main__':
    main()