import logging
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

    def preloop(self):
        """
        Whenever the debug stops somewhere, it will open a prompt in the `cmdloop`.
        This is done by the `interaction` method in the base class.
        The interaction method also initializes `curframe` and clears it as well afterwards.

        The most reliable way to notify the debugger of a stop is with the `precmd` hook.
        At this point, we are sure `curframe` is set, contrary to `user_line`, it
        is always called before the cmd
        """
        try:
            logging.debug(
                f"[DEBUGGER] Debugger command loop started at frame {self.curframe}; Notifing parent _on_stop"
            )
            if self.curframe is None:
                logging.error("[DEBUGGER] curframe is None in preloop")
            else:
                self._parent._on_stop(self.curframe)
        except Exception as e:
            logging.error(f"[DEBUGGER] Error in preloop: {e}")
        return self._debug_base.preloop(self)

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

    def set_continue(self):
        """
        Afterwards, stops only at breakpoints, when finished, or on calling
        `set_trace` which simply reinitializes the debugger from the start.

        If there are no breakpoints, set the system trace function to None.

        The return value of `on_continue_callback` determines what happens to
        the ipdab server:
        - "exit_without_breakpoint": Exit the debugger on continue if no further breakpoints are set. Note `set_trace` calls do not count as breakpoints, in such cases the debug server will be reinitialized, and the clients needs to reconnect.
        - "exit": Exit the debug server even if there are break points set.
        - "keep_running": Keep the debug server running after continue, allowing future `set_trace` calls to re-enter the debugger.
        """
        if self._parent.on_continue_callback is not None:
            on_continue = self._parent.on_continue_callback()
            if on_continue == "exit_without_breakpoint":
                if not self.breaks:
                    logging.debug("[DEBUGGER] set_quit called, calling _on_exit once")
                    self.call_on_exit_once()
                    logging.debug("[DEBUGGER] Calling _on_exit completed")
            elif on_continue == "exit":
                logging.debug("[DEBUGGER] set_quit called, calling _on_exit once")
                self.call_on_exit_once()
                logging.debug("[DEBUGGER] Calling _on_exit completed")
            elif on_continue == "keep_running":
                # TODO: try to do something here
                pass
            else:
                raise ValueError(f"Invalid on_continue return value: {on_continue}")
        self._debug_base.set_continue(self)
        self._set_stopinfo(self.botframe, None, -1)

    def set_quit(self):
        """
        Called when the debugger is quitting, it's the only way a BdbQuit is raised.

        Note that catching BdbQuit is not possible, as we don't not control the main loop.
        the `set_trace` method merely injects callbacks into the interpreter that cause the
        debugger to stop at breakpoints and such.
        """
        logging.debug("[DEBUGGER] set_quit called, calling _on_exit once")
        self.call_on_exit_once()
        logging.debug("[DEBUGGER] Calling _on_exit completed")
        return self._debug_base.set_quit(self)

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

    # These methods are called by the base debugger to handle events.
    # They function as callbacks inserted into the interpreter.
    # def dispatch_return(self, frame, arg):
    #     logging.debug(f"[DEBUGGER] dispatch_return called at frame {frame}")
    #     if frame is self.botframe:
    #         logging.debug("[DEBUGGER] dispatch_return at botframe, calling _on_exit once")
    #         self.call_on_exit_once()
    #     self._debug_base.dispatch_return(self, frame, arg)

    # def dispatch_exception(self, frame, arg):
    #     logging.debug(f"[DEBUGGER] dispatch_exception called at frame {frame} with arg {arg}")
    #     self._debug_base.dispatch_exception(self, frame, arg)
    #
    # def dispatch_line(self, frame):
    #     logging.debug(f"[DEBUGGER] dispatch_line called at frame {frame}")
    #     self._debug_base.dispatch_line(self, frame)
    #
    # def dispatch_call(self, frame, arg):
    #     logging.debug(f"[DEBUGGER] dispatch_call called at frame {frame} with arg {arg}")
    #     self._debug_base.dispatch_call(self, frame, arg)


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
        on_continue_callback=None,
        **kwargs,
    ):
        backend = backend.lower()
        self.stopped_callback = stopped_callback
        self.exited_callback = exited_callback
        self.on_continue_callback = on_continue_callback
        if backend == "ipdb":
            self.debugger = CustomTerminalPdb(parent=self)
        elif backend == "pdb":
            self.debugger = CustomPdb(parent=self)
        else:
            raise ValueError(f"Unsupported debugger: {backend}. Use 'ipdb' or 'pdb'.")

        self.backend = backend

    def _on_stop(self, frame):
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
