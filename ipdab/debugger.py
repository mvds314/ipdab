import logging
import inspect
import pdb
import pkgutil
import sysconfig
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
        self._exited = False

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

    def set_trace(self, *args, frame=None, **kwargs):
        """
        Set a trace in the debugger, and notify the parent on stop.

        The idea is that `set_trace` sets up the debugger.
        Normally, notification happens in `user_line`, but we also want to notify
        on consecutive calls to `set_trace`, which would not call `user_line`.
        On consecutive calls to `set_trace`, `curframe` already set, so notification can happen.
        """
        if frame is not None:
            logging.debug(
                f"[DEBUGGER] set_trace called with frame {frame.f_code.co_filename}:{frame.f_lineno}"
            )
            self.curframe = frame
        elif self.curframe is not None:
            frame = self.curframe
        function_name = inspect.currentframe().f_code.co_name
        logging.debug(f"[DEBUGGER {function_name}] called")
        try:
            if frame is not None:
                self._parent._on_stop(frame)
                logging.debug(
                    f"[DEBUGGER {function_name}] Parent notified on stop for frame {frame.f_code.co_filename}:{frame.f_lineno}"
                )
            logging.debug(f"[DEBUGGER {function_name}] {function_name} done")
            retval = self._debug_base.set_trace(self, *args, **kwargs)
        except Exception as e:
            logging.error(f"[DEBUGGER {function_name}] Error: {e}")
            raise
        else:
            return retval

    def postcmd(self, stop, line):
        """
        Each time a prompt is about to be shown, the `interaction` method
        sets up `curframe` and then calls `cmdloop` to initialize a command loop.
        With in the command loop, each time a command is submitted, the following methods
        are called in order: the hook `precmd` before the execution of the command,
        the method `onecmd` to execute the command, and the method `postcmd` after the command is executed.
        """
        # TODO: why do we notify here, wouldn't it make more sense to overload do_next or do_step?
        try:
            cmd = line.strip().lower()
            if cmd in {"n", "s", "step", "next"}:
                logging.debug(f"[DEBUGGER] Post command '{cmd}' received; calling _on_stop")
                if self.curframe is None:
                    logging.error(
                        f"[DEBUGGER] Post command '{cmd}' received while curframe is None"
                    )
                self._parent._on_stop(self.curframe)
            else:
                logging.debug(f"[DEBUGGER] Post command '{cmd}' received; no action taken")
        except Exception as e:
            logging.error(f"[DEBUGGER] Error in postcmd: {e}")
        return self._debug_base.postcmd(self, stop, line)

    def do_quit(self, arg):
        logging.debug("[DEBUGGER] Quit command received, calling on exit once")
        try:
            self.call_on_exit_once()
        except Exception as e:
            logging.error(f"[DEBUGGER] Error in on_exit: {e}")
        return self._debug_base.do_quit(self, arg)

    do_q = do_quit  # Alias for do_quit
    do_exit = do_quit

    def do_continue(self, arg):
        """
        Not sure if we really need this.
        """
        logging.debug("[DEBUGGER] Continue command received")
        try:
            ret = self._debug_base.do_continue(self, arg)
            # If debugger finished (ret True), call _on_exit
            if getattr(self, "quitting", False):
                logging.debug("[DEBUGGER] Not quitting, calling on exit once, why?")
                self.call_on_exit_once()
            return ret
        except BdbQuit:
            logging.debug("[DEBUGGER] BdbQuit received, calling _on_exit")
            self.call_on_exit_once()
            raise
        except Exception as e:
            logging.error(f"[DEBUGGER] Error in do_continue: {e}")
            raise

    def do_EOF(self, arg):
        """
        Not sure if we really need this.
        """
        logging.debug("[DEBUGGER] EOF received, calling on exit once")
        try:
            self.call_on_exit_once()
        except Exception as e:
            logging.error(f"[DEBUGGER] Error in on_exit (EOF): {e}")
        return self._debug_base.do_EOF(self, arg)

    def set_quit(self):
        """
        Not sure if we really need this.
        """
        # Called by bdb when quitting the debugger (e.g., after continue at end of program)
        logging.debug("[DEBUGGER] set_quit called, calling _on_exit once")
        self.call_on_exit_once()
        return self._debug_base.set_quit(self)

    def interaction(self, frame, traceback=None):
        """
        Seems to be called when the interaction stops, but the finally part is not working yet.
        """
        try:
            self._debug_base.interaction(self, frame, traceback)
        finally:
            logging.debug("[DEBUGGER] Interaction finished, checking if running")
            if not getattr(self, "running", True):
                logging.debug("[DEBUGGER] Not running, calling _on_exit once")
                self.call_on_exit_once()
            elif getattr(self, "quitting", False):
                logging.debug("[DEBUGGER] Quitting, calling _on_exit")
                self.call_on_exit_once()
            else:
                logging.debug("[DEBUGGER] Still running, not calling _on_exit")

    def call_on_exit_once(self):
        """
        Called when the debugger is exiting.
        This method should be overridden by subclasses to handle exit logic.
        """
        if self._exited:
            logging.debug("[DEBUGGER] _exit called, but already exited")
            return
        else:
            logging.debug("[DEBUGGER] _exit called, calling _on_exit")
            self._parent._on_exit()
            self._exited = True

    # TODO: check this one and see if it fixes the continue issue
    def dispatch_return(self, frame, arg):
        if frame is self.botframe:
            logging.debug("[DEBUGGER] Dispatching return, calling _on_exit")
            self.call_on_exit_once()
        self._debug_base.dispatch_return(self, frame, arg)


class CustomTerminalPdb(CustomDebugger, TerminalPdb):
    """
    Custom TerminalPdb that integrates with the parent Debugger class.
    This class overrides methods to handle stopping and exiting events.
    """

    def __init__(self, parent, *args, **kwargs):
        skip = kwargs.pop("skip", [])
        # Add all standard library modules to skip
        stdlib_path = sysconfig.get_paths()["stdlib"]
        stdlib_modules = set()
        for module_info in pkgutil.iter_modules([stdlib_path]):
            stdlib_modules.add(module_info.name)
        # Add patterns for all stdlib modules
        for mod in stdlib_modules:
            skip.append(mod)
        # Additional modules to skip
        skip.append("ipdab.*")
        skip.append("IPython.terminal.debugger")
        skip.append("concurrent.futures.*")
        skip.append("threading")
        CustomDebugger.__init__(self, TerminalPdb, parent)
        TerminalPdb.__init__(self, *args, skip=skip, **kwargs)
        logging.debug("[CustomTerminalPdb] Initialized")


class CustomPdb(CustomDebugger, pdb.Pdb):
    """
    Custom Pdb that integrates with the parent Debugger class.
    This class overrides methods to handle stopping and exiting events.
    """

    def __init__(self, parent, *args, **kwargs):
        skip = kwargs.pop("skip", [])
        # Add all standard library modules to skip
        stdlib_path = sysconfig.get_paths()["stdlib"]
        stdlib_modules = set()
        for module_info in pkgutil.iter_modules([stdlib_path]):
            stdlib_modules.add(module_info.name)
        # Add patterns for all stdlib modules
        for mod in stdlib_modules:
            skip.append(mod)
        # Additional modules to skip
        skip.append("ipdab.*")
        CustomDebugger.__init__(self, pdb.Pdb, parent)
        pdb.Pdb.__init__(self, *args, skip=skip, **kwargs)
        logging.debug("[CustomPdb] Initialized")


class Debugger:
    def __init__(
        self,
        *args,
        backend="ipdb",
        stopped_callback=None,
        exited_callback=None,
        **kwargs,
    ):
        backend = backend.lower()
        self.stopped_callback = stopped_callback
        self.exited_callback = exited_callback

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
            self.stopped_callback(reason="breakpoint")
            logging.debug("[DEBUGGER] Stopped callback executed.")
        else:
            logging.debug("[DEBUGGER] No stopped callback set.")

    def _on_exit(self):
        logging.debug("[DEBUGGER] Debugger is exiting")
        if self.exited_callback:
            self.exited_callback(reason="exited")
            logging.debug("[DEBUGGER] Exited callback executed.")
        else:
            logging.debug("[DEBUGGER] No exited callback set.")

    def set_trace(self, frame=None):
        logging.debug("[DEBUGGER] Trace set, entering debugger.")
        try:
            return self.debugger.set_trace(frame=frame)
        except (BdbQuit, SystemExit):
            logging.debug("[DEBUGGER] BdbQuit or SystemExit caught, calling _on_exit")
            self.debugger.call_on_exit_once()
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
