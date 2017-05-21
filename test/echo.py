import time
import logging
logging.basicConfig(level=logging.DEBUG)

while True:
    logging.info(time.time())
    time.sleep(1)