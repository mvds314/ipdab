# script_to_debug.py
import time
import ipdab

print("Starting script...")

time.sleep(1)

ipdab.set_trace()  # or use ipdb.Debugger().set_trace()

x = 10
ipdab.set_trace()  # Debugger will stop here
y = x * 2
print("Result:", y)
