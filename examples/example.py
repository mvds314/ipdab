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
    print("In myfun with x =", x)
    print("Still in the func")
    return x


print("Starting script...")

time.sleep(1)

ipdab.set_trace(on_continue="keep_running")  # Debugger will stop here

x = 10
ipdab.set_trace(on_continue="exit_without_breakpoint")
y = 2 * myfun(x)
print("Result:", y)
