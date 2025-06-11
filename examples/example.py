# script_to_debug.py
import logging

logging.basicConfig(
    # filename="example.log",
    level=logging.DEBUG,
    format="%(asctime)s [%(levelname)s] %(message)s",
)

import time

import ipdab

print("Starting script...")

time.sleep(1)

ipdab.set_trace()  # or use ipdb.Debugger().set_trace()

x = 10
ipdab.set_trace()  # Debugger will stop here
y = x * 2
print("Result:", y)
