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
