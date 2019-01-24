from .beat import config
import json
import uuid
import time
import threading
import click

reply_channel = 'SINGLE_BEAT_REPLY_{}'.format(uuid.uuid4())


class Commander(object):

    def cmd_info(self):
        return 'info', []

    def cmd_quit(self):
        """\
        kills the child - if running - and then single-beat itself exits
        useful to terminate all single-beat instances in one go
        :return:
        """
        return 'quit', []

    def cmd_pause(self):
        """\
        it will kill the child and pause all nodes
        """
        return 'pause', []

    def cmd_resume(self):
        """\
        will resume all nodes - set them to waiting state
        """
        return 'resume', []

    def cmd_restart(self):
        """\
        it will restart the child process - in the same node
        useful for when deploying new code
        """
        return 'restart', []

    def cmd_stop(self):
        """\
        it will stop the child process, then any single-beat node will pick it up
        and restart
        """
        return 'stop', []


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
    #
    cmd_name, args = fn()
    cmd = json.dumps({
        'cmd': cmd_name,
        'args': args,
        'reply_channel': reply_channel
    })
    rds = config.get_redis()
    rds.publish('SB_{}'.format(config.IDENTIFIER), cmd)


if __name__ == '__main__':
    main()

