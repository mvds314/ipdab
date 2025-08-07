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

- [x] Test `quit` and `exit` instead of `q`
- [x] Fix Neovim config keep showing arrow
- [x] Fix quit on continue
- [x] Fix quit on continue, but script is interactive
- [ ] Test ipdab with Neovim mappings
- [ ] Check how ipdab works with module reloads
- [x] Exclude ipdab modules from debugger
- [ ] Double check all the do_bla commands from pdb
- [ ] Test the setup in ToggleTerm
- [ ] Add Neovim shortcuts
- [ ] Create a pypi package
- [ ] Create a Neovim plugin
- [ ] Fix `RuntimeError: cannot schedule new futures after shutdown` when exiting ipdb with next (common issue)
