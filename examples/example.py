# script_to_debug.py
import logging

logging.basicConfig(
    # filename="example.log",
    level=logging.DEBUG,
    # level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)

import time

import ipdab


def myfun(x):
    return x


print("Starting script...")

time.sleep(1)

ipdab.set_trace()

x = 10
ipdab.set_trace()  # Debugger will stop here
y = 2 * myfun(x)
print("Result:", y)
