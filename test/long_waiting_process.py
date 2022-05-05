# encoding: utf-8
import time
import sys
import signal


def sigusr1_handler(signum, frame):
    print("SIGUSR1 received")


signal.signal(signal.SIGUSR1, sigusr1_handler)


time.sleep(2)
while True:
    print("hello - ççöşııığğğ")
    sys.stdout.flush()
    time.sleep(1)
