---
name: ipdab-internals
description: Deep internal reference for the ipdab codebase — the CustomDebugger MRO/mixin trick used to hook pdb/ipdb internals in ipdab/debugger.py, and the asyncio/threading model, singleton IPDBAdapterServer, DAP command table, and shutdown/event coordination in ipdab/server.py. Load this before making any non-trivial change to ipdab/debugger.py or ipdab/server.py, or when debugging issues with duplicate/missing "stopped" notifications, the on_continue behavior, server startup/shutdown races, client reconnection, or the DAP command handling in handle_client. This goes deeper than the repo's CLAUDE.md (which only has the high-level architecture) — consult it whenever the task touches debugger callbacks, the event-loop thread, or DAP message plumbing, even if the request doesn't mention "ipdab" by name.
---

# ipdab internals

`ipdab` bolts a Debug Adapter Protocol (DAP) server onto `pdb`/`ipdb`, but the debugger
is still driven from the terminal — the DAP client (IDE) can only *observe* state, never
inject `continue`/`step`/`pause` commands. Everything below explains the two files that
make that work: `ipdab/debugger.py` (hooking the debugger) and `ipdab/server.py`
(threading/asyncio plumbing + the DAP wire protocol). Read the relevant section before
editing either file — small changes here have non-obvious cross-thread consequences.

## `ipdab/debugger.py` — hooking pdb/ipdb without touching their internals

### The MRO trick

```python
class CustomTerminalPdb(CustomDebugger, TerminalPdb): ...
class CustomPdb(CustomDebugger, pdb.Pdb): ...
```

`CustomDebugger` (an ABC, not itself a `pdb.Pdb`/`TerminalPdb` subclass) is listed
**first** in the base list so Python's MRO resolves `preloop`, `postcmd`,
`set_continue`, and `set_quit` to `CustomDebugger`'s versions instead of the real
debugger base class's. Because `CustomDebugger` doesn't inherit from the base class
itself, `super()` doesn't reliably reach it — instead each override stores a direct
reference to the real base class at `__init__` time (`self._debug_base = TerminalPdb`
or `pdb.Pdb`) and calls it explicitly: `self._debug_base.<method>(self, ...)`. This is
why `CustomDebugger.__init__` takes `debug_base` as a parameter — it's not decoration,
it's the only way the overridden methods can still invoke the real pdb/ipdb behavior
after doing their own notification work.

If you add a new override to `CustomDebugger`, you must call `self._debug_base.<name>(self, ...)`
at the end (or wherever appropriate) or the real debugger behavior for that hook is lost.

### The two "stopped" signals — `preloop` vs `postcmd`

- **`preloop`** fires on *every* prompt display. It's the primary signal because
  `interaction()` (in the real pdb/ipdb base) guarantees `curframe` is set before
  `cmdloop` (and thus `preloop`) runs — unlike `user_line`, which fires before that
  setup completes.
- **`postcmd`** also fires `_on_stop`, but only when the just-executed command was a
  step/movement command — matched against the exact set
  `{"n", "s", "step", "next", "unt", "until"}` or a prefix match on
  `"j "`, `"jump "`, `"unt "`, `"until "` (i.e. `jump <line>` / `until <line>` forms).
  This exists so the IDE's cursor moves immediately after a step, but there's an open
  `TODO` at `debugger.py:57` questioning whether this duplicates `preloop` and sends
  `stopped` twice for the same pause — if you're chasing a bug about double "stopped"
  events reaching the client, start here.

### Exit handling

- **`set_continue`** asks `self._parent.on_continue_callback()` (wired from
  `Debugger` → `IPDBAdapterServer.on_continue`) for one of three policies:
  - `"exit_without_breakpoint"` — call `call_on_exit_once()` only if `self.breaks` is empty.
  - `"exit"` — always call `call_on_exit_once()`.
  - `"keep_running"` — no-op (there's a `# TODO: try to do something here` — currently
    nothing special happens; the debug *server* just stays up).
  Any other value raises `ValueError`.
- **`set_quit`** → `call_on_exit_once()` then delegates to the base class. This is the
  *only* reliable path for detecting a `BdbQuit`, since `BdbQuit` cannot be caught
  from outside — `ipdab` never controls the main loop that would need to catch it.
- **`call_on_exit_once`** guards with the `self._exited` flag so `_on_exit` (and
  therefore `exited_callback` → `notify_exited`) fires exactly once no matter which
  path (quit vs. continue-with-no-breakpoints vs. `BdbQuit`/`SystemExit` caught in
  `Debugger.set_trace`) triggered it.
- The commented-out `dispatch_return`/`dispatch_exception`/`dispatch_line`/`dispatch_call`
  block at the bottom of `CustomDebugger` is dead exploratory code from trying
  lower-level bdb hooks instead of `preloop`/`postcmd` — useful context if `preloop`/`postcmd`
  ever prove insufficient, but not currently wired up.

### Skip lists

`CustomTerminalPdb.__init__` and `CustomPdb.__init__` both pass `DEFAULT_SKIP`
(`"ipdab.*"`, `"IPython.terminal.debugger"`, `"concurrent.futures.*"`, `"threading"`)
down to `bdb`, plus anything the caller supplies via `skip=`. Both backends now use the
same list — the old asymmetry, where only the `ipdb` variant skipped
`threading`/`concurrent.futures`, is gone.

Everything else is decided by `SkipMatcher`, which `CustomDebugger.is_skipped_module`
overrides `bdb.Bdb.is_skipped_module` with. Two things matter about it:

- **It classifies by path, not by name.** `library_roots()` collects the stdlib and
  *every* site-packages directory (`sysconfig` paths plus `site.getsitepackages()` and
  `site.getusersitepackages()`), and a module counts as library code when its
  `__file__` sits under one of them; builtin/frozen modules count too. This is what
  gives "only stop in my own code". Enumerating module *names* — what the code used to
  do with `pkgutil.iter_modules([sysconfig.get_paths()["stdlib"]])` — cannot work: a
  venv layered on a base install resolves imports from several site-packages
  directories, and an editable install lives outside all of them, so a name list both
  misses third-party packages and risks mislabelling the user's own.
- **It is cached, and that is a correctness-shaped performance fix.**
  `bdb.Bdb.stop_here` calls `is_skipped_module` on *every call and every line event*,
  and the stock implementation `fnmatch`es the entire skip list each time. The old
  190-entry stdlib list therefore cost ~130 µs per event, and the cost fell hardest on
  modules that were *not* skipped, since a miss compares against all 190 patterns.
  Measured on a trivial `pandas` call: 221 ms traced under the old list vs 4.2 ms with
  the matcher (745x vs 14x untraced). Wildcard patterns are compiled into one regex,
  literals go in a set, and every verdict is memoised — a negative verdict only once
  the module is in `sys.modules`, so a lookup made mid-import is not pinned forever.

Escape hatches: `skip_libraries=False` disables the path-based classification entirely,
and `unskip=[...]` re-enables stepping into named libraries (e.g. `["pandas.*"]`).
Both are accepted by `Debugger(...)`, which now forwards `*args`/`**kwargs` to the
backend instead of dropping them.

### `Debugger` façade

`Debugger` (constructor `backend="ipdb"|"pdb"`) is the only thing `server.py` talks to.
It exposes `set_trace`, `set_break`, `clear_break`, `get_all_breaks`, and the `curframe`
property, hiding which concrete class (`CustomTerminalPdb` vs `CustomPdb`) is active.
`set_trace` catches `BdbQuit`/`SystemExit` and calls `call_on_exit_once()` directly —
this is a second path to the same idempotent exit notification described above, needed
because `set_quit` isn't always reached before the exception propagates out.

## `ipdab/server.py` — threading/asyncio model and the DAP wire protocol

### Two threads, one blocking prompt

- The **main thread** runs the user's script and blocks inside the `pdb`/`ipdb` prompt
  once `set_trace()` is called.
- A **daemon thread** (`self.thread`, started by `start_in_thread`) runs an `asyncio`
  event loop via `asyncio.Runner` (`run_loop` → `runner.run(self.server_main())`). The
  `Runner` instance is stashed on `self.runner` so other code can reach its loop.
- `server_main` creates the actual listening server as a task
  (`self.server_task = asyncio.create_task(self.background_server())`); cancelling that
  task is how the server shuts down (see below).
- Cross-thread calls **always** go through
  `asyncio.run_coroutine_threadsafe(coro, self.runner._loop).result()` — note this reaches
  into `Runner`'s private `_loop` attribute; there's no public accessor. Both
  `stopped_callback` and `exited_callback` (called synchronously from the main thread by
  `debugger.py`'s hooks) use this pattern to hop onto the event-loop thread and block
  until the corresponding coroutine (`notify_stopped`/`notify_exited`) finishes, so the
  main thread doesn't resume until the DAP event has actually been sent.

### The three `threading.Event`s

Because `notify_exited`, `notify_terminated`, and `shutdown_server` can each be reached
from multiple independent paths (client disconnect, debugger exit, `atexit`, explicit
`.shutdown()` call), each has its own event so re-entry is a safe no-op instead of
double-sending a DAP event or double-cancelling a task:

| Event | Set by | Guards |
|---|---|---|
| `_exited_event` | `notify_exited` (first line) | prevents sending `exited`/re-running `notify_exited` twice |
| `_terminated_event` | `notify_terminated` (first line) | prevents sending `terminated` twice; `notify_terminated` is called both from `notify_exited` and from `shutdown_server` |
| `_shutdown_event` | `shutdown_server` (once, guarding the rest of the method) | stops `handle_client`'s read loop, blocks new `stopped`/`exited` notifications (`stopped_callback`/`exited_callback` both check `_shutdown_event.is_set()` and bail early) |

All three are cleared again in `background_server` (server startup) and in `set_trace`,
so a fresh `set_trace()` call after a full exit can restart cleanly.

### Startup / shutdown sequencing

- `set_trace(frame, on_continue)` — if `self.server` is falsy, calls `start_in_thread()`
  (which spawns the daemon thread and polls `self.server_running` up to `max_wait_time`
  seconds, tolerating a transient `"Inconsistent server state"` `RuntimeError` while the
  server/task pair is mid-assignment), clears all three events, then calls into
  `Debugger.set_trace` — this is what actually blocks the main thread at the prompt.
- `server_running` is a tri-state check: `False` if `_shutdown_event` is set or both
  `server`/`server_task` are `None`; raises `RuntimeError("Inconsistent server state...")`
  if exactly one of `server`/`server_task` is set (a transient state during startup —
  callers like `start_in_thread` retry on this specific message rather than treating it
  as fatal).
- `shutdown()` is the public, cross-thread teardown entry point (also called from
  `__del__` and from `atexit`-registered `_at_exit_cleanup`). It raises if called from
  *inside* the event-loop thread (that would deadlock), schedules `shutdown_server()`
  via `run_coroutine_threadsafe`, then joins the daemon thread.
- `shutdown_server()` (runs inside the loop) sets `_shutdown_event`, notifies
  `terminated` once if a client is connected, cancels `_read_dap_message_task` and
  `server_task` if not already done, and awaits the cancellation. `background_server`'s
  `finally` block resets `self.server = None` once `serve_forever()` unwinds (there's a
  `# TODO: is this the correct fix?` next to that reset — worth a second look if you see
  stale-server-reference bugs across repeated `set_trace()`/shutdown cycles).

### `on_continue` — server policy, not debugger control

`IPDBAdapterServer.on_continue` (property with validation, one of
`"exit_without_breakpoint" | "exit" | "keep_running"`) is threaded through as
`on_continue_callback` to `Debugger` → `CustomDebugger.set_continue` (see above). It
controls whether the **DAP server** tears itself down when the user types `continue` at
the prompt — it has no effect on the debugger itself, which always genuinely continues
execution. Note the module-level `set_trace()` convenience function defaults to
`on_continue="keep_running"`, while `IPDBAdapterServer.set_trace`'s own default is
`"exit_without_breakpoint"` — callers going through the re-exported `ipdab.set_trace()`
get the "keep running" behavior unless they override it.

### `handle_client` — the DAP command table

One client at a time: a new connection calls `disconnect_client()` on any existing one
first. On connect, `self.debugger.clear_exited()` resets the debugger's `_exited` flag
so a client that connects *after* a prior exit can still get fresh notifications.

Messages are framed as `Content-Length: N\r\n\r\n<N bytes of JSON>`
(`read_dap_message` reads byte-by-byte until it sees the header terminator, then reads
exactly `Content-Length` body bytes; `encode_dap_message` does the inverse for
responses/events).

| Command | Behavior |
|---|---|
| `initialize` | `{"supportsConfigurationDoneRequest": true}` |
| `launch` | empty body response, then sends an `initialized` event |
| `configurationDone` | empty body, then sends a synthetic `stopped` event with `reason: "entry"` |
| `threads` | hardcoded single thread `{"id": 1, "name": "MainThread"}` |
| `stackTrace` | walks `curframe.f_back` up to 20 frames |
| `scopes` | two synthetic scopes per frame: `Locals` (`variablesReference = 1000 + frameId`), `Globals` (`2000 + frameId`, `expensive: true`) |
| `variables` | branches on the `1000 ≤ ref < 2000` (locals) vs `ref ≥ 2000` (globals) ranges above; values are `repr()`'d, no nested/lazy expansion (`variablesReference: 0` always) |
| `evaluate` | `eval(expr, curframe.f_globals, curframe.f_locals)`, stringified; exceptions become `"Error: {e}"` in the result body rather than a failed response |
| `setBreakpoints` | clears all existing breakpoints for the given path via `get_all_breaks()`/`clear_break`, then sets the new set; always reports `verified: true` without checking the line is actually breakable |
| `setExceptionBreakpoints` | acknowledged, not actually implemented |
| `source` | reads the file at `source.path` off disk directly (no support for `sourceReference`-only sources) |
| `disconnect` | responds success, then the read loop breaks (see below) |
| `continue`, `pause`, `stepIn`, `stepOut`, `next`, `disassemble` | **always `success: false`** — this is the deliberate design boundary: control must come from the terminal, never from the IDE |
| anything else | `success: false`, `"Unsupported command: {cmd}"` |

After building `response`, the loop checks the three shutdown-related events again
before writing — and specifically for `disconnect`, it `break`s the read loop *without*
writing the response (the response is built but never sent), then `disconnect_client()`
runs in the `finally` block.

### Reference implementation used in `handle_client`

The `background_server`/`handle_client` split follows the pattern described in
https://superfastpython.com/asyncio-server-background-task/ — if a future change to the
server lifecycle looks structurally odd, check that article's "Closing Asyncio Server
Safely With Context Manager" example for the intended shape.

## Session data flow (concrete walkthrough)

1. Script calls `ipdab.set_trace()` → `IPDBAdapterServer.set_trace` → `start_in_thread()`
   spins up the daemon thread running the asyncio server (default `localhost:9000`) →
   `Debugger.set_trace` enters the real `pdb`/`ipdb` prompt, blocking the main thread.
2. IDE connects; sends `initialize` → `launch` (server fires `initialized` event) →
   `setBreakpoints` (one call per source file) → `configurationDone` (server fires a
   synthetic `stopped`/`entry` event since the debugger is already sitting at the
   `set_trace()` call site).
3. IDE issues read-only queries (`threads`, `stackTrace`, `scopes`, `variables`,
   `evaluate`) against `self.debugger.curframe` to render the current state.
4. User types `n`/`s`/`c`/etc. **at the terminal**. `postcmd` (for step-like commands)
   and/or `preloop` (for the next prompt) call `_on_stop` → `stopped_callback` →
   cross-thread hop → `notify_stopped` → `stopped` DAP event pushed to the IDE, which
   re-queries frames/variables.
5. On `continue` with no breakpoints left (default `on_continue_callback` policy is
   whatever was passed to `set_trace`), `set_continue` calls `call_on_exit_once` →
   `_on_exit` → `exited_callback` → cross-thread hop → `notify_exited` (sends `exited`
   then `terminated`) → `shutdown_server()` cancels the server task; the daemon thread's
   `run_loop` exits.
6. A later `ipdab.set_trace()` call sees `self.server` is falsy again and restarts the
   whole thing from step 1 — the client must reconnect.

## Known rough edges (from code TODOs / README TODO — check before assuming a bug is new)

- `preloop`/`postcmd` may both fire `_on_stop` for the same logical pause
  (`debugger.py:57` TODO) — a duplicate `stopped` event is a known open question, not
  necessarily a regression you introduced.
- `pdb` backend's skip list omits `IPython.terminal.debugger`/`concurrent.futures.*`/`threading`
  that the `ipdb` backend includes — likely an oversight, not a deliberate asymmetry.
- `background_server`'s `self.server = None` reset on shutdown is marked
  `# TODO: is this the correct fix?` — treat as unverified if debugging repeated
  start/stop cycles.
- No test suite exists yet (see repo `CLAUDE.md`); changes to this threading/callback
  machinery should be manually exercised via `examples/example.py` plus a real DAP
  client connection, since races here won't show up from reading the code alone.
