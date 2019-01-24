from .beat import config
import json
import uuid
import time
import threading
import click

reply_channel = 'SINGLE_BEAT_REPLY_{}'.format(uuid.uuid4())


class Commander(object):

    def cmd_info(self):
        cmd = json.dumps({
            'cmd': 'who',
            'reply_channel': reply_channel
        })
        rds = config.get_redis()
        rds.publish('SB_{}'.format(config.IDENTIFIER), cmd)

    def cmd_quit(self):
        """\
        kills the child - if running - and then single-beat itself exits
        useful to terminate all single-beat instances in one go
        :return:
        """
        cmd = json.dumps({
            'cmd': 'quit',
            'reply_channel': reply_channel
        })
        rds = config.get_redis()
        rds.publish('SB_{}'.format(config.IDENTIFIER), cmd)

    def cmd_pause(self):
        """\
        it will kill the child and pause all nodes
        """
        cmd = json.dumps({
            'cmd': 'pause',
            'reply_channel': reply_channel
        })
        rds = config.get_redis()
        rds.publish('SB_{}'.format(config.IDENTIFIER), cmd)

    def cmd_resume(self):
        """\
        will resume all nodes - set them to waiting state
        """
        cmd = json.dumps({
            'cmd': 'resume',
            'reply_channel': reply_channel
        })
        rds = config.get_redis()
        rds.publish('SB_{}'.format(config.IDENTIFIER), cmd)


    def cmd_restart(self):
        """\
        it will restart the child process - in the same node
        useful for when deploying new code
        """
        cmd = json.dumps({
            'cmd': 'restart',
            'reply_channel': reply_channel
        })
        rds = config.get_redis()
        rds.publish('SB_{}'.format(config.IDENTIFIER), cmd)

    def cmd_stop(self):
        """\
        it will stop the child process, then any single-beat node will pick it up
        and restart
        """
        cmd = json.dumps({
            'cmd': 'stop',
            'reply_channel': reply_channel
        })
        rds = config.get_redis()
        rds.publish('SB_{}'.format(config.IDENTIFIER), cmd)

    def cmd_self_quit(self):
        rds = config.get_redis()
        print("quit now !", 'SB_{}'.format(config.IDENTIFIER))
        rds.publish(reply_channel, 'quit')


def submit_to_replies():
    rds = config.get_redis()
    cnt = rds.pubsub_numsub('SB_{}'.format(config.IDENTIFIER))
    cnt = cnt[0][1]
    p = rds.pubsub()
    p.subscribe(reply_channel)
    while cnt > 0:
        message = p.get_message(timeout=5)
        if not message:
            return
        if message['type'] == 'subscribe':
            continue

        data = json.loads(message['data'])
        print("{} | {} | {}".format(data['identifier'], data['state'], data.get('info', '') ))
        cnt = cnt - 1


@click.command()
@click.argument('cmd')
def main(cmd='info'):
    commander = Commander()
    fn = getattr(commander, 'cmd_{}'.format(cmd), None)
    if not fn:
        raise Exception('unknown command')
    thread = threading.Thread(target=submit_to_replies)
    thread.start()
    time.sleep(0.100)
    fn()


if __name__ == '__main__':
    main()

