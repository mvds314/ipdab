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

- [ ] Test on slower hardware
- [x] Add Neovim shortcuts
- [ ] Create a pypi package
- [ ] Create a Neovim plugin
- [x] Add support for j, as in jump
- [ ] Test or add support for return
- [ ] Test or add support for until
- [ ] Add support for down as in moving down the stack

# later

- [ ] Check how ipdab works with module reloads
- [ ] Consider post mortem support

# Nice

- [ ] Fix `RuntimeError: cannot schedule new futures after shutdown` when exiting ipdb with next (common issue)
