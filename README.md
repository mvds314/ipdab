# ipdab

A [Debug Adapter Protocol](https://microsoft.github.io/debug-adapter-protocol/) (DAP) for the Python [pdb](https://docs.python.org/3/library/pdb.html) and [ipdb](https://ipython.readthedocs.io/en/stable/api/generated/IPython.terminal.debugger.html#module-IPython.terminal.debugger) debuggers.
[Debugpy](https://github.com/microsoft/debugpy) is the reference implementation of a DAP for Python.
The DAP allow your IDE to communicate with the debugger in a standardised way.

The good, old Python debuggers `pdb` and `ipdb` debugger were considered incompatible with the DAP as you control the debugger from the terminal, and not from your IDE.
The aim of `ipdab` is to implement the DAP to these debuggers to the extent possible, and get create a debugging experience that some would consider to have the best of both world:

- You control the debugger from the terminal
- Your IDE is able to track the debugger, e.g., by indicating the current line with an arrow.

# How it works

In addition to starting the `pdb` or `ipdb` debugger, `ipdab` starts server whenever you use `set_trace`.
Any IDE that supports the DAP can connect to this server to track progress of the debugger, retrieve variable values,
retrieve the stack trace etc.

Note that it's not possible to control the debugger from your IDE. This is a technical limitation of the `pdb` and `ipdb` debugger.
They give control to the user every time you see a command prompt. At such a point, the DAP server cannot inject any commands
as it doesn't control the terminal in which the debugger runs. Controlling the debugger should be done from the terminal itself.

# Installation

```bash
pip install ipdab

```

Or, clone the [repository](https://github.com/mvds314/ipdab.git) and install with:

```bash
pip install -e .
```

# Usage

Just like `ipdb`, use `ipdab` in the code you want to debug:

```python
print("Hello, world!")
print("Starting ipdab...")

import ipdab

ipdab.set_trace()

print("This will be debugged.")
```

Now, connect your IDE to the DAP server started by `ipdab`.

TODO: an example for Neovim will follow

# TODO

- [x] Add Neovim shortcuts
- [x] Add support for j, as in jump
- [x] Test or add support for return
- [x] Test or add support for until
- [ ] Test on slower hardware
  - [ ] It seems that dapuit is timing out
  - [ ] Try to start it with fewer windows
- [ ] Create a pypi package
  - [ ] Cleanup the repo
- [ ] Create a Neovim plugin
- [ ] Write a blog post about debugging

- [ ] Fix compatiblity with ipython 9.1.0 and higher, entering the debugger seems to break
- [ ] Check how ipdab works with module reloads
- [ ] Consider post mortem support
