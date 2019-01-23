from .beat import config
import json
import uuid
import time
import threading

reply_channel = 'SINGLE_BEAT_REPLY_{}'.format(uuid.uuid4())


def cmd_who():
    cmd = json.dumps({
        'cmd': 'who',
        'reply_channel': reply_channel
    })
    rds = config.get_redis()
    # print("sending command now !", 'SB_{}'.format(config.IDENTIFIER))
    rds.publish('SB_{}'.format(config.IDENTIFIER), cmd)
    # print("sent command")


def cmd_self_quit():
    rds = config.get_redis()
    print("quit now !", 'SB_{}'.format(config.IDENTIFIER))
    rds.publish(reply_channel, 'quit')


def submit_to_replies():
    # print("reply thread started")
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
        print("{} | {}".format(data['identifier'], data['state']))
        cnt = cnt - 1


def main():
    thread = threading.Thread(target=submit_to_replies)
    thread.start()
    time.sleep(0.100)
    cmd_who()
    thread.join(timeout=3)


if __name__ == '__main__':
    main()

# import tornado
# import tornadis
#
# reply_channel = 'SINGLE_BEAT_REPLY_{}'.format(uuid.uuid4())
#
#
# @tornado.gen.coroutine
# def pubsub_coroutine():
#     conn = config.get_redis().connection_pool.get_connection('ping')
#     client = tornadis.PubSubClient(host=conn.host, port=conn.port,
#                                    password=conn.password, autoconnect=False)
#     yield client.connect()
#     yield client.pubsub_subscribe(reply_channel)
#
#     # Looping over received messages
#     while True:
#         msg = yield client.pubsub_pop_message()
#         print(msg)
#         if isinstance(msg, tornadis.TornadisException):
#             # closed connection by the server
#             break
#         elif len(msg) >= 4 and msg[3] == "STOP":
#             # it's a STOP message, let's unsubscribe and quit the loop
#             yield client.pubsub_punsubscribe("foo*")
#             yield client.pubsub_unsubscribe("bar")
#             break
#
#     # Let's disconnect
#     client.disconnect()
#
#
# loop = tornado.ioloop.IOLoop.instance()
# loop.run_sync(pubsub_coroutine)