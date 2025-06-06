import asyncio
import json
import threading
import time

# import pdb
from IPython.terminal.debugger import TerminalPdb
from .debugger import Debugger


class IPDBAdapterServer:
    def __init__(self, host="127.0.0.1", port=9000, debugger="ipdb"):
        self.host = host
        self.port = port
        self.server = None
        self.loop = None
        self.debugger = Debugger(backend=debugger)
        self.client_writer = None
        self.client_reader = None
        self._shutdown_event = threading.Event()

    async def read_dap_message(self, reader):
        # Read headers until blank line
        header = b""
        while not header.endswith(b"\r\n\r\n"):
            header += await reader.read(1)
        header_text = header.decode()
        content_length = 0
        for line in header_text.strip().split("\r\n"):
            if line.lower().startswith("content-length:"):
                content_length = int(line.split(":")[1].strip())
        body = await reader.read(content_length)
        return json.loads(body.decode())

    def encode_dap_message(self, payload):
        body = json.dumps(payload)
        return f"Content-Length: {len(body)}\r\n\r\n{body}".encode()

    async def send_event(self, event_body):
        event_msg = {"type": "event", "seq": 0, **event_body}
        self.client_writer.write(self.encode_dap_message(event_msg))
        await self.client_writer.drain()
        print(f"[DAP] Sent event: {event_msg}")

    async def notify_stopped(self, reason="breakpoint"):
        if self.client_writer:
            await self.send_event(
                {
                    "event": "stopped",
                    "body": {
                        "reason": reason,
                        "threadId": 1,
                        "allThreadsStopped": True,
                    },
                }
            )

    async def handle_client(self, reader, writer):
        print("[DAP] Client connected")
        self.client_writer = writer
        self.client_reader = reader

        while True:
            try:
                msg = await self.read_dap_message(reader)
            except Exception as e:
                print(f"[DAP] Error reading message: {e}")
                break

            if msg is None:
                print("[DAP] Client disconnected")
                break

            print(f"[DAP] Received: {msg}")
            response = {
                "type": "response",
                "seq": msg.get("seq", 0),
                "request_seq": msg.get("seq", 0),
                "success": True,
                "command": msg.get("command", ""),
            }

            cmd = msg.get("command")

            if cmd == "initialize":
                response["body"] = {"supportsConfigurationDoneRequest": True}

            elif cmd == "launch":
                response["body"] = {}

                await self.send_event({"event": "initialized", "body": {}})

            elif cmd == "continue":
                print("[DAP] Continue received")
                # Resume ipdb execution
                self.debugger.set_continue()
                # Notify client that execution has resumed
                await self.send_event("continued", {"threadId": 1, "allThreadsContinued": True})

            elif cmd == "pause":
                print("[DAP] Pause received")
                # Pause ipdb — simulate with set_trace() to drop in prompt
                self.debugger.set_trace()
                await self.send_event(
                    "stopped",
                    {
                        "reason": "pause",
                        "threadId": 1,
                        "allThreadsStopped": True,
                    },
                )

            elif cmd == "stepIn":
                print("[DAP] StepIn received")
                self.debugger.set_step()
                await self.send_event(
                    "stopped",
                    {
                        "reason": "step",
                        "threadId": 1,
                        "allThreadsStopped": True,
                    },
                )

            elif cmd == "stepOut":
                print("[DAP] StepOut received")
                self.debugger.set_return()  # if your debugger supports it, or implement accordingly
                await self.send_event(
                    "stopped",
                    {
                        "reason": "step",
                        "threadId": 1,
                        "allThreadsStopped": True,
                    },
                )

            elif cmd == "next":
                print("[DAP] Next received")
                self.debugger.set_next()
                await self.send_event(
                    "stopped",
                    {
                        "reason": "step",
                        "threadId": 1,
                        "allThreadsStopped": True,
                    },
                )
            elif cmd == "configurationDone":
                print("[DAP] Configuration done received")
                response["body"] = {}

                # Optional: Send a 'stopped' event to indicate the debugger is ready
                await self.send_event(
                    {
                        "event": "stopped",
                        "body": {
                            "reason": "entry",
                            "threadId": 1,
                            "allThreadsStopped": True,
                        },
                    }
                )
            elif cmd == "evaluate":
                expr = msg.get("arguments", {}).get("expression", "")
                try:
                    # Evaluate expression in ipdb debugger context
                    result = eval(
                        expr, self.debugger.curframe.f_globals, self.debugger.curframe.f_locals
                    )
                    response["body"] = {"result": str(result), "variablesReference": 0}
                except Exception as e:
                    response["body"] = {"result": f"Error: {e}", "variablesReference": 0}

            elif cmd == "setBreakpoints":
                args = msg.get("arguments", {})
                source = args.get("source", {})
                path = source.get("path", "")
                breakpoints = args.get("breakpoints", [])

                # Clear old breakpoints in the file
                if path in self.debugger.get_all_breaks():
                    for bp_line in self.debugger.get_all_breaks()[path]:
                        self.debugger.clear_break(path, bp_line)

                actual_bps = []
                for bp in breakpoints:
                    line = bp.get("line")
                    if line:
                        self.debugger.set_break(path, line)
                        actual_bps.append({"verified": True, "line": line})

                response["body"] = {"breakpoints": actual_bps}

            else:
                response["success"] = False
                response["message"] = f"Unsupported command: {cmd}"

            writer.write(self.encode_dap_message(response))
            await writer.drain()
            print(f"[DAP] Sent response: {response}")

        writer.close()
        await writer.wait_closed()

    async def start_server(self):
        self.server = await asyncio.start_server(self.handle_client, self.host, self.port)
        print(f"[Adapter] DAP server listening on {self.host}:{self.port}")
        async with self.server:
            await self.server.serve_forever()

    def shutdown(self):
        print("[Adapter] Shutdown initiated")
        self._shutdown_event.set()
        if self.loop:
            self.loop.call_soon_threadsafe(self.loop.stop)

    def _run_loop(self):
        self.loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self.loop)
        try:
            self.loop.run_until_complete(self.start_server())
        except asyncio.CancelledError:
            pass
        except Exception as e:
            print(f"[Adapter] Event loop exception: {e}")
        finally:
            print("[Adapter] Event loop stopping")
            try:
                self.loop.run_until_complete(self.loop.shutdown_asyncgens())
            finally:
                self.loop.close()

    def start_in_thread(self):
        threading.Thread(target=self._run_loop, daemon=True).start()

    def set_trace(self):
        if not self.server:
            self.start_in_thread()
        # Enter ipdb prompt here
        self.debugger.set_trace()


# Create singleton adapter
ipdab = IPDBAdapterServer()


def set_trace():
    ipdab.set_trace()


if __name__ == "__main__":
    # Simple example usage:
    import time

    print("Starting debug adapter server...")
    ipdab.start_in_thread()

    print("Run your script and call set_trace() to debug.")
    # Keep main thread alive
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("Exiting adapter server")
