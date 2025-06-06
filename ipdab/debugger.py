import pdb
import asyncio
from IPython.terminal.debugger import TerminalPdb


class Debugger:
    def __init__(self, backend="ipdb", stopped_callback=None):
        backend = backend.lower()
        self.stopped_callback = stopped_callback
        if backend == "ipdb":
            parent = self

            class CustomTerminalPdb(TerminalPdb):
                def user_line(inner_self, frame):
                    super().user_line(frame)
                    parent._on_stop(frame)

            self.debugger = CustomTerminalPdb()
        elif backend == "pdb":
            parent = self

            class CustomPdb(pdb.Pdb):
                def user_line(inner_self, frame):
                    super().user_line(frame)
                    parent._on_stop(frame)

            self.debugger = CustomPdb()
        else:
            raise ValueError(f"Unsupported debugger: {backend}. Use 'ipdb' or 'pdb'.")
        self.backend = backend

    def _on_stop(self, frame):
        self.debugger.curframe = frame
        if self.stopped_callback:
            loop = asyncio.get_event_loop()
            asyncio.run_coroutine_threadsafe(self.stopped_callback(reason="breakpoint"), loop)

    def set_trace(self):
        self.debugger.set_trace()

    def set_continue(self):
        self.debugger.set_continue()

    def set_step(self):
        self.debugger.set_step()

    def set_next(self):
        if self.curframe:
            self.debugger.set_next(self.curframe)

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
