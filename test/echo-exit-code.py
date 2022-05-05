import sys
import time
import logging
logging.basicConfig(level=logging.DEBUG)

logging.info(time.time())
time.sleep(3)
print("exiting from echo !")
sys.exit(3)