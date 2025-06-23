import asyncio
import logging
import pdb
from abc import ABC, abstractmethod
from bdb import BdbQuit

from IPython.terminal.debugger import TerminalPdb


class CustomDebugger(ABC):
    """
    Base class for custom debuggers.
    This class is abstract and should not be instantiated directly.
    """

    @abstractmethod
    def __init__(self, debug_base, parent):
        """
        Initialize the custom debugger with a parent reference.

        Implementation should handle setting up the debugger

        :param parent: Reference to the parent object that will handle callbacks.
        """
        self._debug_base = debug_base
        self._parent = parent

    def user_line(self, frame):
        """
        Called when the debugger stops at a line of code.
        :param frame: The current stack frame.
        """
        logging.debug(
            f"[DEBUGGER] user_line called, frame {frame.f_code.co_filename}:{frame.f_lineno}"
        )
        try:
            # Call base debugger method first so internal state updates correctly
            self._debug_base.user_line(self, frame)
            logging.debug(
                f"[DEBUGGER] Base user_line done, curframe is {getattr(self, 'curframe', None)}"
            )

            # Then notify parent
            self._parent._on_stop(frame)
        except Exception as e:
            logging.error(f"[DEBUGGER] Error in user_line: {e}")

    def postcmd(self, stop, line):
        try:
            cmd = line.strip().lower()
            if cmd in {"n", "s", "step", "next"}:
                logging.debug(f"[DEBUGGER] Post command '{cmd}' received; calling _on_stop")
                self._parent._on_stop(self.curframe)
            else:
                logging.debug(f"[DEBUGGER] Post command '{cmd}' received; no action taken")
        except Exception as e:
            logging.error(f"[DEBUGGER] Error in postcmd: {e}")
        return self._debug_base.postcmd(self, stop, line)

    def do_quit(self, arg):
        logging.debug("[DEBUGGER] Quit command received")
        try:
            self._parent._on_exit()
        except Exception as e:
            logging.error(f"[DEBUGGER] Error in on_exit: {e}")
        return self._debug_base.do_quit(self, arg)

    def do_continue(self, arg):
        logging.debug("[DEBUGGER] Continue command received")
        try:
            ret = self._debug_base.do_continue(self, arg)
            # If debugger finished (ret True), call _on_exit
            if ret:
                self._parent._on_exit()
            return ret
        except BdbQuit:
            logging.debug("[DEBUGGER] BdbQuit received, calling _on_exit")
            self._parent._on_exit()
            raise
        except Exception as e:
            logging.error(f"[DEBUGGER] Error in do_continue: {e}")
            raise

    def do_EOF(self, arg):
        logging.debug("[DEBUGGER] EOF received")
        try:
            self._parent._on_exit()
        except Exception as e:
            logging.error(f"[DEBUGGER] Error in on_exit (EOF): {e}")
        return self._debug_base.do_EOF(self, arg)


class CustomTerminalPdb(CustomDebugger, TerminalPdb):
    """
    Custom TerminalPdb that integrates with the parent Debugger class.
    This class overrides methods to handle stopping and exiting events.
    """

    def __init__(self, parent, *args, **kwargs):
        CustomDebugger.__init__(self, TerminalPdb, parent)
        TerminalPdb.__init__(self, *args, **kwargs)
        logging.debug("[DEBUGGER] CustomTerminalPdb initialized")


class CustomPdb(CustomDebugger, pdb.Pdb):
    """
    Custom Pdb that integrates with the parent Debugger class.
    This class overrides methods to handle stopping and exiting events.
    """

    def __init__(self, parent, *args, **kwargs):
        CustomDebugger.__init__(self, pdb.Pdb, parent)
        pdb.Pdb.__init__(self, *args, **kwargs)
        logging.debug("[DEBUGGER] CustomPdb initialized")


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
        logging.debug(
            f"[DEBUGGER] _on_stop called for {frame.f_code.co_filename}:{frame.f_lineno}"
        )
        if self.stopped_callback:
            loop = self.loop or asyncio.get_event_loop()
            if asyncio.iscoroutinefunction(self.stopped_callback):
                asyncio.run_coroutine_threadsafe(self.stopped_callback(reason="breakpoint"), loop)
            else:
                self.stopped_callback(reason="breakpoint")
            logging.debug("[DEBUGGER] Stopped callback executed.")
        else:
            logging.debug("[DEBUGGER] No stopped callback set.")

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
        try:
            return self.debugger.set_trace()
        except (BdbQuit, SystemExit):
            logging.debug("[DEBUGGER] BdbQuit or SystemExit caught, calling _on_exit")
            self._on_exit()
        except Exception as e:
            logging.error(f"[DEBUGGER] Error in set_trace: {e}")
            raise

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
