import asyncio
import json
import logging
import threading
import time

from .debugger import Debugger


class IPDBAdapterServer:
    def __init__(self, host="127.0.0.1", port=9000, debugger="ipdb"):
        self.host = host
        self.port = port
        self.server = None
        self.loop = asyncio.new_event_loop()
        self.debugger = Debugger(
            backend=debugger, stopped_callback=self.notify_stopped, loop=self.loop
        )
        self.client_writer = None
        self.client_reader = None
        self._shutdown_event = threading.Event()

    async def read_dap_message(self, reader):
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
        logging.debug(f"[DAP] Sent event: {event_msg}")

    async def notify_stopped(self, reason="breakpoint"):
        if self.client_writer:
            logging.debug(f"[DAP] Notifying stopped: {reason}")
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
        else:
            logging.debug(f"[DAP] No client connected, cannot notify stopped: {reason}")

    async def handle_client(self, reader, writer):
        logging.info("[DAP] New client connection")
        self.client_writer = writer
        self.client_reader = reader
        while True:
            try:
                msg = await self.read_dap_message(reader)
            except Exception as e:
                logging.error(f"[DAP] Error reading message: {e}")
                break
            if msg is None:
                logging.info("[DAP] Client disconnected")
                break
            logging.debug(f"[DAP] Received message: {msg}")
            response = {
                "type": "response",
                "seq": msg.get("seq", 0),
                "request_seq": msg.get("seq", 0),
                "success": True,
                "command": msg.get("command", ""),
            }
            cmd = msg.get("command")
            if cmd == "initialize":
                logging.info("[DAP] Initialize command received")
                response["body"] = {"supportsConfigurationDoneRequest": True}
            elif cmd == "launch":
                logging.info("[DAP] Launch command received, initializing debugger")
                response["body"] = {}
                await self.send_event({"event": "initialized", "body": {}})
            elif cmd == "continue":
                logging.error("[DAP] Continue commands can only be send through terminal")
                response["success"] = False
                response["message"] = "Continue commands can only be sent through terminal"
            elif cmd == "pause":
                logging.info("[DAP] Pause command received, pausing debugger")
                self.debugger.set_trace()
                await self.send_event(
                    {
                        "event": "stopped",
                        "body": {"reason": "pause", "threadId": 1, "allThreadsStopped": True},
                    }
                )
            elif cmd == "stepIn":
                logging.error("[DAP] StepIn commands can only be send through terminal")
                response["success"] = False
                response["message"] = "StepIn commands can only be sent through terminal"
            elif cmd == "stepOut":
                logging.error("[DAP] StepOut commands can only be send through terminal")
                response["success"] = False
                response["message"] = "StepOut commands can only be sent through terminal"
            elif cmd == "next":
                logging.error("[DAP] Next commands can only be send through terminal")
                response["success"] = False
                response["message"] = "Next commands can only be sent through terminal"
            elif cmd == "configurationDone":
                logging.info("[DAP] ConfigurationDone command received")
                response["body"] = {}
                await self.send_event(
                    {
                        "event": "stopped",
                        "body": {"reason": "entry", "threadId": 1, "allThreadsStopped": True},
                    }
                )
            elif cmd == "threads":
                logging.info("[DAP] Threads command received")
                response["body"] = {"threads": [{"id": 1, "name": "MainThread"}]}
            elif cmd == "stackTrace":
                logging.info("[DAP] StackTrace command received")
                frames = []
                if self.debugger.curframe:
                    f = self.debugger.curframe
                    i = 0
                    while f and i < 20:
                        code = f.f_code
                        frames.append(
                            {
                                "id": i,
                                "name": code.co_name,
                                "line": f.f_lineno,
                                "column": 1,
                                "source": {"path": code.co_filename},
                            }
                        )
                        f = f.f_back
                        i += 1
                response["body"] = {"stackFrames": frames, "totalFrames": len(frames)}
            elif cmd == "scopes":
                logging.info("[DAP] Scopes command received")
                frame_id = msg.get("arguments", {}).get("frameId", 0)
                response["body"] = {
                    "scopes": [
                        {
                            "name": "Locals",
                            "variablesReference": 1000 + frame_id,
                            "expensive": False,
                        },
                        {
                            "name": "Globals",
                            "variablesReference": 2000 + frame_id,
                            "expensive": True,
                        },
                    ]
                }
            elif cmd == "variables":
                logging.info("[DAP] Variables command received")
                var_ref = msg.get("arguments", {}).get("variablesReference", 0)
                frame = self.debugger.curframe
                variables = []
                if 1000 <= var_ref < 2000 and frame:
                    for k, v in frame.f_locals.items():
                        variables.append({"name": k, "value": repr(v), "variablesReference": 0})
                elif var_ref >= 2000 and frame:
                    for k, v in frame.f_globals.items():
                        variables.append({"name": k, "value": repr(v), "variablesReference": 0})
                response["body"] = {"variables": variables}
            elif cmd == "evaluate":
                logging.info("[DAP] Evaluate command received")
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
                logging.info("[DAP] SetBreakpoints command received")
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
            elif cmd == "setExceptionBreakpoints":
                logging.info("[DAP] SetExceptionBreakpoints command received")
                # You can store exception breakpoints info if needed or just acknowledge
                response["body"] = {}
                # For now, just acknowledge success; real implementation would configure exception breakpoints in debugger
            elif cmd == "source":
                logging.info("[DAP] Source command received")
                args = msg.get("arguments", {})
                # For simplicity, handle only file path sources (no binary or compiled sources)
                if "path" in args.get("source", {}):
                    path = args["source"]["path"]
                    try:
                        with open(path, "r", encoding="utf-8") as f:
                            content = f.read()
                        response["body"] = {"content": content}
                    except Exception as e:
                        response["success"] = False
                        response["message"] = f"Failed to read source: {e}"
                else:
                    response["success"] = False
                    response["message"] = "Unsupported source reference"
            elif cmd == "disassemble":
                logging.info("[DAP] Disassemble command received")
                response["success"] = False
                response["message"] = "Disassemble not supported in this debugger"
            else:
                logging.warning(f"[DAP] Unsupported command: {cmd}")
                response["success"] = False
                response["message"] = f"Unsupported command: {cmd}"
                logging.warning(f"[DAP] Unsupported command: {cmd}")
            writer.write(self.encode_dap_message(response))
            await writer.drain()
            logging.debug(f"[DAP] Sent response: {response}")
        writer.close()
        await writer.wait_closed()

    async def start_server(self):
        self.server = await asyncio.start_server(self.handle_client, self.host, self.port)
        logging.debug(f"[Adapter] DAP server listening on {self.host}:{self.port}")
        async with self.server:
            await self.server.serve_forever()

    def shutdown(self):
        logging.info("[Adapter] Shutting down DAP server")
        self._shutdown_event.set()
        if self.loop:
            self.loop.call_soon_threadsafe(self.loop.stop)

    def _run_loop(self):
        asyncio.set_event_loop(self.loop)
        try:
            self.loop.run_until_complete(self.start_server())
        except asyncio.CancelledError:
            pass
        except Exception as e:
            logging.error(f"[Adapter] Event loop exception: {e}")
        finally:
            logging.debug("[Adapter] Event loop stopping")
            try:
                self.loop.run_until_complete(self.loop.shutdown_asyncgens())
            finally:
                self.loop.close()

    def start_in_thread(self):
        threading.Thread(target=self._run_loop, daemon=True).start()

    def set_trace(self):
        if not self.server:
            logging.debug("[Adapter] Starting DAP server in a new thread")
            self.start_in_thread()
        else:
            logging.debug("[Adapter] DAP server already running, setting trace")
        # Enter ipdb prompt here
        self.debugger.set_trace()


# Create singleton adapter
ipdab = IPDBAdapterServer()


def set_trace():
    logging.info("[Adapter] Setting trace in IPDB adapter")
    ipdab.set_trace()


if __name__ == "__main__":
    # Simple example usage:
    import time

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
    )

    print("Starting debug adapter server...")
    ipdab.start_in_thread()

    print("Run your script and call set_trace() to debug.")
    # Keep main thread alive
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("Exiting adapter server")
