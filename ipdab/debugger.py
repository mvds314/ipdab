import pdb
import asyncio
from IPython.terminal.debugger import TerminalPdb


class Debugger:
    def __init__(self, backend="ipdb", stopped_callback=None, loop=None):
        backend = backend.lower()
        self.stopped_callback = stopped_callback
        self.loop = loop
        if backend == "ipdb":
            parent = self

            class CustomTerminalPdb(TerminalPdb):
                def user_line(inner_self, frame):
                    print(
                        "[DEBUGGER] Stopped at:", frame.f_code.co_filename, "line", frame.f_lineno
                    )
                    try:
                        super().user_line(frame)
                        parent._on_stop(frame)
                    except Exception as e:
                        print(f"[DEBUGGER] Error in user_line: {e}")

            self.debugger = CustomTerminalPdb()
        elif backend == "pdb":
            parent = self

            class CustomPdb(pdb.Pdb):
                def user_line(inner_self, frame):
                    print(
                        "[DEBUGGER] Stopped at:", frame.f_code.co_filename, "line", frame.f_lineno
                    )
                    try:
                        super().user_line(frame)
                        parent._on_stop(frame)
                    except Exception as e:
                        print(f"[DEBUGGER] Error in user_line: {e}")

            self.debugger = CustomPdb()
        else:
            raise ValueError(f"Unsupported debugger: {backend}. Use 'ipdb' or 'pdb'.")
        self.backend = backend

    def _on_stop(self, frame):
        self.debugger.curframe = frame
        print("[DEBUGGER] Stopped at:", frame.f_code.co_filename, "line", frame.f_lineno)
        if self.stopped_callback:
            loop = self.loop or asyncio.get_event_loop()
            if asyncio.iscoroutinefunction(self.stopped_callback):
                asyncio.run_coroutine_threadsafe(self.stopped_callback(reason="breakpoint"), loop)
            else:
                self.stopped_callback(reason="breakpoint")
            print("[DEBUGGER] Stopped callback executed.")
        else:
            print("[DEBUGGER] No stopped callback set, continuing without notification.")

    def set_trace(self):
        self.debugger.set_trace()
        print("[DEBUGGER] Stepping into the next line.")

    def set_continue(self):
        self.debugger.set_continue()
        print("[DEBUGGER] Continuing execution.")

    def set_step(self):
        self.debugger.set_step()
        print("[DEBUGGER] Stepping into the next line.")

    def set_next(self):
        if self.curframe:
            self.debugger.set_next(self.curframe)
            print("[DEBUGGER] Stepping over to the next line.")
        else:
            print("[DEBUGGER] No current frame to step over.")

    def set_return(self):
        if self.curframe:
            self.debugger.set_return(self.curframe)
            print("[DEBUGGER] Returning from the current frame.")
        else:
            print("[DEBUGGER] No current frame to return from.")

    def get_all_breaks(self):
        if hasattr(self.debugger, "get_all_breaks"):
            return self.debugger.get_all_breaks()
        else:
            return getattr(self.debugger, "breaks", {})

    def set_break(self, filename, lineno):
        self.debugger.set_break(filename, lineno)

    def clear_break(self, filename, lineno):
        self.debugger.clear_break(filename, lineno)

    @property
    def curframe(self):
        return getattr(self.debugger, "curframe", None)
