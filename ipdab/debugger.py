import asyncio
import logging
import pdb

from IPython import get_ipython
from IPython.terminal.debugger import TerminalPdb


class Debugger:
    def __init__(self, backend="ipdb", stopped_callback=None, loop=None):
        backend = backend.lower()
        self.stopped_callback = stopped_callback
        self.loop = loop
        self.shell = get_ipython()
        if backend == "ipdb":
            parent = self

            class CustomTerminalPdb(TerminalPdb):
                def user_line(inner_self, frame):
                    logging.debug(
                        f"[DEBUGGER] Stopped at: {frame.f_code.co_filename} line {frame.f_lineno}"
                    )
                    try:
                        parent._on_stop(frame)
                        super().user_line(frame)
                    except Exception as e:
                        logging.error(f"[DEBUGGER] Error in user_line: {e}")

            self.debugger = CustomTerminalPdb()
        elif backend == "pdb":
            raise NotImplementedError()
            parent = self

            class CustomPdb(pdb.Pdb):
                def user_line(inner_self, frame):
                    logging.debug(
                        f"[DEBUGGER] Stopped at: {frame.f_code.co_filename} line {frame.f_lineno}"
                    )
                    try:
                        parent._on_stop(frame)
                        super().user_line(frame)
                    except Exception as e:
                        logging.error(f"[DEBUGGER] Error in user_line: {e}")

            self.debugger = CustomPdb()
        else:
            raise ValueError(f"Unsupported debugger: {backend}. Use 'ipdb' or 'pdb'.")
        self.backend = backend

    def send_to_terminal(self, command):
        if not self.shell:
            raise RuntimeError("No active IPython shell found")
        logging.debug(f"[DEBUGGER] Sending command to terminal: {command}")
        self.shell.run_cell(f"!{command}", store_history=False)

    def _on_stop(self, frame):
        self.debugger.curframe = frame
        logging.debug(f"[DEBUGGER] Stopped at: {frame.f_code.co_filename} line {frame.f_lineno}")
        if self.stopped_callback:
            loop = self.loop or asyncio.get_event_loop()
            if asyncio.iscoroutinefunction(self.stopped_callback):
                asyncio.run_coroutine_threadsafe(self.stopped_callback(reason="breakpoint"), loop)
            else:
                self.stopped_callback(reason="breakpoint")
            logging.debug("[DEBUGGER] Stopped callback executed.")
        else:
            logging.debug("[DEBUGGER] No stopped callback set, continuing without notification.")

    def set_trace(self):
        logging.debug("[DEBUGGER] Trace set, entering debugger.")
        self.debugger.set_trace()

    def set_continue(self):
        logging.debug("[DEBUGGER] Continue command issued.")
        self.debugger.onecmd("continue")

    def set_step(self):
        logging.debug("[DEBUGGER] Step command issued.")
        self.debugger.onecmd("step")

    def set_next(self):
        logging.debug("[DEBUGGER] Next command issued.")
        self.debugger.onecmd("next")

    def set_return(self):
        logging.debug("[DEBUGGER] Return command issued.")
        self.debugger.onecmd("return")

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
