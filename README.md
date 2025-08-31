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

- [x] Add Neovim shortcuts
- [x] Add support for j, as in jump
- [x] Test or add support for return
- [x] Test or add support for until
- [ ] Test on slower hardware
  - [ ] It seems that dapuit is timing out
  - [ ] Try to start it with fewer windows
- [ ] Fix compatiblity with ipython 9.1.0 and higher, entering the debugger seems to break
- [ ] Create a pypi package
  - [ ] Update the documentation
  - [ ] Cleanup the repo
  - [ ] Write pipelines for publishing and such
- [ ] Create a Neovim plugin
- [ ] Write a blog post about debugging

# later

- [ ] Check how ipdab works with module reloads
- [ ] Consider post mortem support

# Nice

- [ ] Fix `RuntimeError: cannot schedule new futures after shutdown` when exiting ipdb with next (common issue)
