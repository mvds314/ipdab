import asyncio
import logging
import pdb

from IPython.terminal.debugger import TerminalPdb


class CustomTerminalPdb(TerminalPdb):
    def __init__(self, parent, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._parent = parent

    def user_line(self, frame):
        logging.debug(f"[DEBUGGER] Stopped at: {frame.f_code.co_filename} line {frame.f_lineno}")
        try:
            self._parent._on_stop(frame)
            super().user_line(frame)
        except Exception as e:
            logging.error(f"[DEBUGGER] Error in user_line: {e}")

    def postcmd(self, stop, line):
        try:
            if line.strip() in {"n", "s", "step", "next"}:
                self._parent._on_stop(self.curframe)
        except Exception as e:
            logging.error(f"[DEBUGGER] Error in postcmd: {e}")
        return super().postcmd(stop, line)

    def do_quit(self, arg):
        logging.debug("[DEBUGGER] Quit command received")
        try:
            self._parent._on_exit()
        except Exception as e:
            logging.error(f"[DEBUGGER] Error in on_exit: {e}")
        return super().do_quit(arg)


class CustomPdb(pdb.Pdb):
    def __init__(self, parent, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._parent = parent

    def user_line(self, frame):
        logging.debug(f"[DEBUGGER] Stopped at: {frame.f_code.co_filename} line {frame.f_lineno}")
        try:
            self._parent._on_stop(frame)
            super().user_line(frame)
        except Exception as e:
            logging.error(f"[DEBUGGER] Error in user_line: {e}")

    def postcmd(self, stop, line):
        try:
            if line.strip() in {"n", "s", "step", "next"}:
                self._parent._on_stop(self.curframe)
        except Exception as e:
            logging.error(f"[DEBUGGER] Error in postcmd: {e}")
        return super().postcmd(stop, line)

    def do_quit(self, arg):
        logging.debug("[DEBUGGER] Quit command received")
        try:
            self._parent._on_exit()
        except Exception as e:
            logging.error(f"[DEBUGGER] Error in on_exit: {e}")
        return super().do_quit(arg)


class Debugger:
    def __init__(
        self,
        *args,
        backend="ipdb",
        stopped_callback=None,
        loop=None,
        exited_callback=None,
        **kwargs,
    ):
        backend = backend.lower()
        self.stopped_callback = stopped_callback
        self.exited_callback = exited_callback
        self.loop = loop

        if backend == "ipdb":
            self.debugger = CustomTerminalPdb(parent=self)
        elif backend == "pdb":
            self.debugger = CustomPdb(parent=self)
        else:
            raise ValueError(f"Unsupported debugger: {backend}. Use 'ipdb' or 'pdb'.")

        self.backend = backend

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

    def _on_exit(self):
        logging.debug("[DEBUGGER] Debugger is exiting")
        if self.exited_callback:
            loop = self.loop or asyncio.get_event_loop()
            if asyncio.iscoroutinefunction(self.exited_callback):
                asyncio.run_coroutine_threadsafe(self.exited_callback(reason="exited"), loop)
            else:
                self.exited_callback(reason="exited")
            logging.debug("[DEBUGGER] Exited callback executed.")
        else:
            logging.debug("[DEBUGGER] No exited callback set.")

    def set_trace(self):
        logging.debug("[DEBUGGER] Trace set, entering debugger.")
        self.debugger.set_trace()

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

