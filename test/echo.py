import sys
import time
import logging

logging.basicConfig(level=logging.DEBUG)

while True:
    logging.info(time.time())
    try:
        time.sleep(1)
    except KeyboardInterrupt:
        break

print("exiting from echo !")
sys.exit(3)
