# script_to_debug.py
import time
import ipdb

print("Starting script...")

time.sleep(1)

ipdb.set_trace()  # or use ipdb.Debugger().set_trace()

x = 10
y = x * 2
print("Result:", y)
