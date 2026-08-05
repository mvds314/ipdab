import fnmatch
import logging
import os
import pdb
import re
import site
import sys
import sysconfig
from abc import ABC, abstractmethod
from bdb import BdbQuit

from IPython.terminal.debugger import TerminalPdb

#: Modules that drive the debugger itself. Stepping into these is always an accident,
#: so they are skipped on top of whatever :class:`SkipMatcher` classifies as library code.
DEFAULT_SKIP = (
    "ipdab.*",
    "IPython.terminal.debugger",
    "concurrent.futures.*",
    "threading",
)

_WILDCARD = re.compile(r"[*?\[]")


def library_roots():
    """
    The directories that hold non-user code: the standard library and every
    site-packages directory known to this interpreter.

    Enumerating directories rather than module names matters. A virtual environment
    built on top of a base installation resolves imports from several site-packages
    directories at once, and an editable install lives outside all of them, so any
    name-based list is both incomplete and wrong about the user's own packages.
    """
    roots = set()
    paths = sysconfig.get_paths()
    for key in ("stdlib", "platstdlib", "purelib", "platlib"):
        path = paths.get(key)
        if path:
            roots.add(os.path.normcase(os.path.realpath(path)))
    for getter in ("getsitepackages", "getusersitepackages"):
        try:
            found = getattr(site, getter)()
        except (AttributeError, TypeError):
            continue
        if isinstance(found, str):
            found = [found]
        for path in found or []:
            roots.add(os.path.normcase(os.path.realpath(path)))
    return frozenset(roots)


class SkipMatcher:
    """
    Decide whether a module should be skipped by the debugger, quickly.

    `bdb.Bdb.is_skipped_module` walks the whole skip list with `fnmatch` on *every*
    call and line event. With a list of any size that dominates the run time of a
    traced program, and it is paid most heavily by modules that are *not* skipped,
    because a miss has to compare against every pattern. Two things fix that:

    - Patterns without wildcards go into a set, the rest into one compiled regex.
    - Every answer is memoised. Trace events repeat the same handful of module
      names endlessly, so the second lookup onwards is a dict hit.

    Parameters
    ----------
    patterns : iterable of str, optional
        `fnmatch` patterns of module names to skip, e.g. ``"mypkg.*"``.
    skip_libraries : bool, optional
        Skip any module whose file lives under :func:`library_roots`, plus builtin
        and frozen modules. This is the "only stop in my own code" behaviour and is
        what keeps the debugger out of heavy third party call stacks. Default True.
    unskip : iterable of str, optional
        `fnmatch` patterns that win over `skip_libraries`, to step into one library
        anyway. Explicit `patterns` still take precedence over these.
    """

    def __init__(self, patterns=(), skip_libraries=True, unskip=()):
        self._literals, self._regex = self._compile(patterns)
        self._unskip_literals, self._unskip_regex = self._compile(unskip)
        self.skip_libraries = skip_libraries
        self.roots = library_roots() if skip_libraries else frozenset()
        self._cache = {}

    @staticmethod
    def _compile(patterns):
        literals, wildcards = set(), []
        for pattern in patterns or ():
            if _WILDCARD.search(pattern):
                wildcards.append(pattern)
            else:
                literals.add(pattern)
        regex = None
        if wildcards:
            regex = re.compile("|".join(fnmatch.translate(p) for p in wildcards))
        return literals, regex

    @staticmethod
    def _matches(module_name, literals, regex):
        if module_name in literals:
            return True
        return regex is not None and regex.match(module_name) is not None

    def _is_library(self, module_name):
        """Whether `module_name` resolves to a file below one of :attr:`roots`."""
        module = sys.modules.get(module_name)
        if module is None:
            # Not imported (or synthetic globals from exec): assume user code and trace it.
            return False
        filename = getattr(module, "__file__", None)
        if filename is None:
            return True  # builtin or frozen, there is no source to step through
        filename = os.path.normcase(os.path.realpath(filename))
        return any(filename == root or filename.startswith(root + os.sep) for root in self.roots)

    def _classify(self, module_name):
        if self._matches(module_name, self._literals, self._regex):
            return True
        if not self.skip_libraries:
            return False
        if self._matches(module_name, self._unskip_literals, self._unskip_regex):
            return False
        return self._is_library(module_name)

    def __call__(self, module_name):
        if module_name is None:  # some modules do not have names
            return False
        try:
            return self._cache[module_name]
        except KeyError:
            pass
        result = self._classify(module_name)
        # Only remember a negative verdict once the module is importable, otherwise a
        # lookup made before the import completed would pin it to "user code" forever.
        if result or module_name in sys.modules:
            self._cache[module_name] = result
        return result


class CustomDebugger(ABC):
    """
    Base class for custom debuggers.
    This class is abstract and should not be instantiated directly.
    """

    @abstractmethod
    def __init__(self, debug_base, parent, skip=(), skip_libraries=True, unskip=()):
        """
        Initialize the custom debugger with a parent reference.

        Implementation should handle setting up the debugger

        :param parent: Reference to the parent object that will handle callbacks.
        :param skip: Extra `fnmatch` patterns of module names to skip.
        :param skip_libraries: Skip the standard library and site-packages, so the
            debugger only stops in your own code. See :class:`SkipMatcher`.
        :param unskip: Patterns that override `skip_libraries` for selected modules.
        """
        self._debug_base = debug_base
        self._parent = parent
        self._exited = False
        self._skip_matcher = SkipMatcher(
            patterns=skip, skip_libraries=skip_libraries, unskip=unskip
        )

    def is_skipped_module(self, module_name):
        """
        Override of `bdb.Bdb.is_skipped_module` using the cached :class:`SkipMatcher`.

        Note `bdb.Bdb.stop_here` only consults this when `self.skip` is non-empty, which
        is why the backends always pass :data:`DEFAULT_SKIP` through to `bdb`.
        """
        return self._skip_matcher(module_name)

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
            if (
                cmd in {"n", "s", "step", "next", "unt", "until"}
                or cmd.startswith("j ")
                or cmd.startswith("jump ")
                or cmd.startswith("unt ")
                or cmd.startswith("until ")
            ):
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
                    self.call_on_exit_once()
            elif on_continue == "exit":
                self.call_on_exit_once()
            elif on_continue == "keep_running":
                # TODO: try to do something here
                pass
            else:
                raise ValueError(f"Invalid on_continue return value: {on_continue}")
        self._debug_base.set_continue(self)

    def set_quit(self):
        """
        Called when the debugger is quitting, it's the only way a BdbQuit is raised.

        Note that catching BdbQuit is not possible, as we don't not control the main loop.
        the `set_trace` method merely injects callbacks into the interpreter that cause the
        debugger to stop at breakpoints and such.
        """
        self.call_on_exit_once()
        return self._debug_base.set_quit(self)

    def call_on_exit_once(self):
        """
        Called when the debugger is exiting.
        This method should be overridden by subclasses to handle exit logic.
        """
        if self._exited:
            return
        else:
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
        skip = list(kwargs.pop("skip", []) or []) + list(DEFAULT_SKIP)
        skip_libraries = kwargs.pop("skip_libraries", True)
        unskip = kwargs.pop("unskip", ())
        CustomDebugger.__init__(
            self, TerminalPdb, parent, skip=skip, skip_libraries=skip_libraries, unskip=unskip
        )
        TerminalPdb.__init__(self, *args, skip=skip, **kwargs)


class CustomPdb(CustomDebugger, pdb.Pdb):
    """
    Custom Pdb that integrates with the parent Debugger class.
    This class overrides methods to handle stopping and exiting events.
    """

    def __init__(self, parent, *args, **kwargs):
        skip = list(kwargs.pop("skip", []) or []) + list(DEFAULT_SKIP)
        skip_libraries = kwargs.pop("skip_libraries", True)
        unskip = kwargs.pop("unskip", ())
        CustomDebugger.__init__(
            self, pdb.Pdb, parent, skip=skip, skip_libraries=skip_libraries, unskip=unskip
        )
        pdb.Pdb.__init__(self, *args, skip=skip, **kwargs)


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
            self.debugger = CustomTerminalPdb(self, *args, **kwargs)
        elif backend == "pdb":
            self.debugger = CustomPdb(self, *args, **kwargs)
        else:
            raise ValueError(f"Unsupported debugger: {backend}. Use 'ipdb' or 'pdb'.")

        self.backend = backend

    def clear_exited(self):
        self.debugger._exited = False

    def _on_stop(self, frame):
        if self.stopped_callback:
            self.stopped_callback(reason="breakpoint")

    def _on_exit(self):
        if self.exited_callback:
            self.exited_callback(reason="exited")

    def set_trace(self, frame=None):
        try:
            return self.debugger.set_trace(frame=frame)
        except (BdbQuit, SystemExit):
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
