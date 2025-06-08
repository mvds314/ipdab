# script_to_debug.py
import logging
import time

import ipdab

logging.basicConfig(
    filename="example.log",
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)

print("Starting script...")

time.sleep(1)

ipdab.set_trace()  # or use ipdb.Debugger().set_trace()

x = 10
ipdab.set_trace()  # Debugger will stop here
y = x * 2
print("Result:", y)
