import pdb
from IPython.terminal.debugger import TerminalPdb


class Debugger:
    def __init__(self, backend="ipdb"):
        backend = backend.lower()
        if backend == "ipdb":
            self.debugger = TerminalPdb()
        elif backend == "pdb":
            self.debugger = pdb.Pdb()
        else:
            raise ValueError(f"Unsupported debugger: {backend}. Use 'ipdb' or 'pdb'.")
        self.backend = backend

    def set_trace(self):
        self.debugger.set_trace()

    def set_continue(self):
        self.debugger.set_continue()

    def set_step(self):
        self.debugger.set_step()

    def set_next(self):
        self.debugger.set_next()

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
