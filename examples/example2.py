from IPython.terminal.debugger import TerminalPdb


class SyncDebugger(TerminalPdb):
    def user_line(self, frame):
        # Called when the debugger stops at a line
        print(f"[DEBUGGER] Stopped at {frame.f_code.co_filename}:{frame.f_lineno}")
        # Normally, this would prompt user input, but we'll just continue


def example():
    dbg = SyncDebugger()
    print("Starting program")

    def test_func():
        x = 1
        y = 2
        dbg.set_trace()  # Breakpoint here
        z = x + y  # This line will be stepped over or into
        print("Result:", z)

    test_func()

    # Now, while stopped, send debugger commands synchronously:
    # Step over the next line (z = x + y)
    print("[DEBUGGER] Sending 'next'")
    dbg.onecmd("next")
    # Step into the print statement
    print("[DEBUGGER] Sending 'step'")
    dbg.onecmd("step")
    # Continue execution
    print("[DEBUGGER] Sending 'continue'")
    dbg.onecmd("continue")


if __name__ == "__main__":
    example()
