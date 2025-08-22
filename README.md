# ipdab

UNDER CONSTRUCTION

A Debug Adapter Protocol for the ipdb debugger.

# Installation

```bash
pip install git+https://github.com/mvds314/ipdab.git
```

Or, clone the repository and install with:

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

# TODO

# Critical

- [x] Test `quit` and `exit` instead of `q`
- [x] Fix Neovim config keep showing arrow
- [x] Fix quit on continue
- [x] Fix quit on continue, but script is interactive
- [x] Fix `on_stop` not called with `set_trace` -> test new setup
- [x] Exclude ipdab modules from debugger
- [ ] Test setup again
- [ ] Update postcmd logic
- [ ] Fix Neovim config to close debugger on quit and such, config seems broken
- [ ] Test ipdab with Neovim mappings
- [ ] Double check all the do_bla commands from pdb
- [ ] Test the setup in ToggleTerm

# Later

- [ ] Add Neovim shortcuts
- [ ] Check how ipdab works with module reloads
- [ ] Create a pypi package
- [ ] Create a Neovim plugin
- [ ] Consider post mortem support
- [ ] Add support for j, as in jump
- [ ] Add support for r, as in return
- [ ] Add support for u, as in up
- [ ] Add support for down as in moving down the stack

# Nice

- [ ] Fix `RuntimeError: cannot schedule new futures after shutdown` when exiting ipdb with next (common issue)
