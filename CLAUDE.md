# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

`ipdab` implements the [Debug Adapter Protocol](https://microsoft.github.io/debug-adapter-protocol/) (DAP) on top of Python's `pdb`/`ipdb` terminal debuggers. Unlike `debugpy`, the debugger is still controlled from the terminal (you type `n`, `s`, `c`, etc. into the `ipdb`/`pdb` prompt); `ipdab` only pushes state (current line, stack, variables) to a connected DAP client (e.g. an IDE) over a socket so the IDE can *observe* and highlight progress. The DAP server cannot inject commands into the debugger — `continue`/`next`/`step`/`pause` requests from the client are rejected by design (see `handle_client` in `ipdab/server.py`).

## Commands

- Install (editable): `pip install -e .`
- Lint: `ruff check` (rules configured in `pyproject.toml`: `E`, `F`, `W`, line length 99)
- Format check: `ruff format --check` (this is what CI runs, in `.github/workflows/python-app.yml`)
- Format: `ruff format`
- There is currently no test suite (`pytest` is configured with a `tofix` marker in `pyproject.toml`, and CI has the `pytest` step commented out).
- Manually exercise the server/debugger by running one of the scripts in `examples/` (e.g. `python examples/example.py`) and connecting a DAP client to `localhost:9000`.

## Architecture

Two modules do all the work:

### `ipdab/debugger.py` — debugger integration layer

- `CustomDebugger` (ABC) is mixed in *before* `pdb.Pdb` / `TerminalPdb` in the MRO (`CustomTerminalPdb(CustomDebugger, TerminalPdb)`, `CustomPdb(CustomDebugger, pdb.Pdb)`) so it can override `preloop`, `postcmd`, `set_continue`, and `set_quit` and forward to the real base class via `self._debug_base.<method>(self, ...)`. This is how the debugger's internal state-machine callbacks get turned into `_on_stop` / `_on_exit` notifications without touching `pdb`/`ipdb` internals.
  - `preloop` fires `_on_stop` reliably any time a prompt is about to be shown (this is the primary "stopped" signal).
  - `postcmd` also fires `_on_stop`, but only for step/next/until/jump commands — this exists because after those commands the IDE's cursor needs to move, whereas `preloop` alone was apparently insufficient/duplicative in some cases (see the `TODO` at `debugger.py:57`).
  - `set_continue` decides whether the debug server exits based on the `on_continue` policy (see below) by asking `self._parent.on_continue_callback()`.
  - `set_quit`/`call_on_exit_once` guarantee the exit callback fires exactly once (`_exited` flag), because `BdbQuit` cannot be reliably caught elsewhere.
- `Debugger` wraps either backend (`backend="ipdb"` → `CustomTerminalPdb`, `backend="pdb"` → `CustomPdb`) behind one interface (`set_trace`, `set_break`, `clear_break`, `get_all_breaks`, `curframe`) so `server.py` doesn't need to know which backend is active. Standard library modules and `ipdab` itself are added to the debugger's `skip` list so stepping doesn't dive into stdlib or `ipdab` internals.

### `ipdab/server.py` — DAP server and thread/asyncio model

`IPDBAdapterServer` is a **singleton** (module-level instance `ipdab`, exposed to users as `ipdab.set_trace`). Threading model, documented in the module docstring, is the key thing to understand before touching this file:

- The DAP server runs an `asyncio` event loop in its own daemon thread (`start_in_thread` → `run_loop` → `server_main` → `background_server`), started lazily the first time `set_trace()` is called.
- The main thread (running the user's script, blocked inside the `ipdb`/`pdb` prompt) calls `stopped_callback`/`exited_callback` synchronously from `debugger.py`'s hooks; these use `asyncio.run_coroutine_threadsafe(...).result()` to hop onto the event-loop thread and block until the coroutine (`notify_stopped`/`notify_exited`) completes.
- Shutdown is coordinated with three `threading.Event`s (`_shutdown_event`, `_exited_event`, `_terminated_event`) to make each of `notify_exited`/`notify_terminated`/`shutdown_server` idempotent, since they can be reached from multiple paths (client disconnect, debugger exit, `atexit`, explicit `shutdown()`).
- `_at_exit_cleanup` is registered via `atexit` so the server thread is joined and the socket closed even if the user's script never calls anything explicitly.
- `handle_client`'s big `if/elif` chain over `msg.get("command")` is the actual (partial) DAP implementation: `initialize`, `launch`, `configurationDone`, `threads`, `stackTrace`, `scopes`, `variables`, `evaluate`, `setBreakpoints`, `setExceptionBreakpoints`, `source`, `disconnect` are supported; `continue`/`pause`/`stepIn`/`stepOut`/`next`/`disassemble` explicitly return `success: false` because they'd require controlling the debugger from the IDE, which isn't possible.
- `on_continue` (constructor/`set_trace` parameter, string enum `"exit_without_breakpoint"` | `"exit"` | `"keep_running"`) controls what happens to the *server* — not the debugger — when the user types `continue` at the prompt. This is read back by `Debugger.set_continue` via the `on_continue_callback` closure.

### Data flow for a typical session

1. User calls `ipdab.set_trace()` (re-exported from `ipdab/__init__.py`) → `IPDBAdapterServer.set_trace` → starts the server thread if needed → calls into `Debugger.set_trace` → enters the `ipdb`/`pdb` prompt in the main thread.
2. IDE connects over TCP to `host:port` (default `localhost:9000`), speaks DAP framing (`Content-Length` header + JSON body, see `read_dap_message`/`encode_dap_message`).
3. As the user steps through code at the terminal prompt, `CustomDebugger.preloop`/`postcmd` fire `_on_stop`, which reaches the event loop thread and pushes a `stopped` DAP event to the connected client.
4. On `continue` with no more breakpoints (default policy), the server notifies `exited`/`terminated` and shuts itself down; a later `set_trace()` call restarts it.

## Style notes from `pyproject.toml`

- Ruff line length 99; `E203`, `E501`, `E731`, `E402` are intentionally ignored (Black-compatibility and deliberate late imports).
