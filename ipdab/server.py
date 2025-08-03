import asyncio
import atexit
import json
import logging
import threading
import time

from .debugger import Debugger

# TODO: shutdown logic has improved, but still needs to be tested


class IPDBAdapterServer:
    def __init__(self, host="127.0.0.1", port=9000, debugger="ipdb"):
        self.host = host
        self.port = port
        self.server = None
        self.thread = None
        self.loop = asyncio.new_event_loop()
        self.debugger = Debugger(
            backend=debugger,
            loop=self.loop,
            stopped_callback=self.stopped_callback,
            exited_callback=self.exited_callback,
        )
        self.client_writer = None
        self.client_reader = None
        self._shutdown_event = threading.Event()

    def __del__(self):
        """
        Ensure the server is properly shutdown when the adapter is deleted.
        """
        logging.debug("[IPDB Server] Deleting IPDBAdapterServer instance, shutting down server")
        self.shutdown()

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
        logging.debug(f"[IPDB Server] Sent event: {event_msg}")

    async def stopped_callback(self, reason="breakpoint"):
        if self.client_writer:
            logging.debug(f"[IPDB Server] Notifying stopped: {reason}")
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
            logging.debug(f"[IPDB Server] No client connected, cannot notify stopped: {reason}")

    async def exited_callback(self, reason="exited"):
        """
        Notify the client that the program has exited.
        And shutdown the debug adapter server.
        """
        if self.client_writer:
            logging.debug(f"[IPDB Server] Notifying exited: {reason}")
            await self.send_event(
                {
                    "event": "exited",
                    "body": {"reason": reason},
                }
            )
            await self.notify_terminated(reason)
        else:
            logging.debug(f"[IPDB Server] No client connected, cannot notify exited: {reason}")
        logging.debug("[IPDB Server] Exiting debug adapter server")
        await self.shutdown_server()

    async def notify_terminated(self, reason="terminated"):
        """
        Notify the client that the debug adapter server is terminating.
        """
        if self.client_writer:
            logging.debug("[IPDB Server] Notifying terminated")
            await self.send_event(
                {
                    "event": "terminated",
                    "body": {reason: reason},
                }
            )
        else:
            logging.debug("[IPDB Server] No client connected, cannot notify terminated")

    async def handle_client(self, reader, writer):
        logging.info("[IPDB Server] New client connection")
        self.client_writer = writer
        self.client_reader = reader
        while not self._shutdown_event.is_set():
            try:
                # TODO: fix this logic, this prevents server close
                msg = await self.read_dap_message(reader)
                if self._shutdown_event.is_set():
                    logging.debug("[IPDB Server] Shutdown event set, closing client connection")
                    break
            except Exception as e:
                logging.error(f"[IPDB Server] Error reading message: {e}")
                break
            if msg is None:
                logging.info("[IPDB Server] Client disconnected")
                break
            logging.debug(f"[IPDB Server] Received message: {msg}")
            response = {
                "type": "response",
                "seq": msg.get("seq", 0),
                "request_seq": msg.get("seq", 0),
                "success": True,
                "command": msg.get("command", ""),
            }
            cmd = msg.get("command")
            if cmd == "initialize":
                logging.debug("[IPDB Server] Initialize command received")
                response["body"] = {"supportsConfigurationDoneRequest": True}
            elif cmd == "launch":
                logging.debug("[IPDB Server] Launch command received, initializing debugger")
                response["body"] = {}
                await self.send_event({"event": "initialized", "body": {}})
            elif cmd == "continue":
                logging.error("[IPDB Server] Continue commands can only be send through terminal")
                response["success"] = False
                response["message"] = "Continue commands can only be sent through terminal"
            elif cmd == "pause":
                logging.error("[IPDB Server] Pause commands can only be send through terminal")
                response["success"] = False
                response["message"] = "Pause commands can only be sent through terminal"
            elif cmd == "stepIn":
                logging.error("[IPDB Server] StepIn commands can only be send through terminal")
                response["success"] = False
                response["message"] = "StepIn commands can only be sent through terminal"
            elif cmd == "stepOut":
                logging.error("[IPDB Server] StepOut commands can only be send through terminal")
                response["success"] = False
                response["message"] = "StepOut commands can only be sent through terminal"
            elif cmd == "next":
                logging.error("[IPDB Server] Next commands can only be send through terminal")
                response["success"] = False
                response["message"] = "Next commands can only be sent through terminal"
            elif cmd == "configurationDone":
                logging.debug("[IPDB Server] ConfigurationDone command received")
                response["body"] = {}
                await self.send_event(
                    {
                        "event": "stopped",
                        "body": {"reason": "entry", "threadId": 1, "allThreadsStopped": True},
                    }
                )
            elif cmd == "threads":
                logging.debug("[IPDB Server] Threads command received")
                response["body"] = {"threads": [{"id": 1, "name": "MainThread"}]}
            elif cmd == "stackTrace":
                logging.debug("[IPDB Server] StackTrace command received")
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
                logging.debug("[IPDB Server] Scopes command received")
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
                logging.debug("[IPDB Server] Variables command received")
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
                logging.debug("[IPDB Server] Evaluate command received")
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
                logging.debug("[IPDB Server] SetBreakpoints command received")
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
                logging.debug("[IPDB Server] SetExceptionBreakpoints command received")
                # You can store exception breakpoints info if needed or just acknowledge
                response["body"] = {}
                # For now, just acknowledge success; real implementation would configure exception breakpoints in debugger
            elif cmd == "source":
                logging.debug("[IPDB Server] Source command received")
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
                logging.debug("[IPDB Server] Disassemble command received")
                response["success"] = False
                response["message"] = "Disassemble not supported in this debugger"
            elif cmd == "disconnect":
                logging.info("[IPDB Server] Client disconnected")
                response["success"] = True
                response["message"] = "Disconnecting client"
            else:
                logging.warning(f"[IPDB Server] Unsupported command: {cmd}")
                response["success"] = False
                response["message"] = f"Unsupported command: {cmd}"
                logging.warning(f"[IPDB Server] Unsupported command: {cmd}")
            writer.write(self.encode_dap_message(response))
            await writer.drain()
            logging.debug(f"[IPDB Server] Sent response: {response}")
        writer.close()
        await writer.wait_closed()

    async def start_server(self):
        if self.server is not None:
            msg = "[IPDB Server] Server is already running, cannot start again"
            logging.error(msg)
            raise RuntimeError(msg)
        if self._shutdown_event.is_set():
            logging.debug(
                "[IPDB Server] Restarting server, clearing previously set shutdown event"
            )
            self._shutdown_event.clear()
        self.server = await asyncio.start_server(self.handle_client, self.host, self.port)
        logging.info(f"[IPDB Server] DAP server listening on {self.host}:{self.port}")
        async with self.server:
            await self.server.serve_forever()

    async def cleanup_running_loop(self):
        """
        Shutdown the event loop gracefully.
        This is a coroutine to be run in the event loop thread.
        """
        current_task = asyncio.current_task(loop=self.loop)
        tasks = [t for t in asyncio.all_tasks(self.loop) if t is not current_task and not t.done()]
        for task in tasks:
            task.cancel()
        if tasks:
            logging.debug("[IPDB Server] Cancelling all tasks in the event loop")
            await asyncio.gather(*tasks, return_exceptions=True)
        else:
            logging.debug("[IPDB Server] No tasks to cancel in the event loop")
        tasks = [t for t in asyncio.all_tasks(self.loop) if t is not current_task and not t.done()]
        if any(tasks):
            msg = (
                "[IPDB Server] There are still tasks running in the event loop after cancellation"
            )
            logging.error(msg)
            raise RuntimeError(msg)

        if hasattr(self.loop, "shutdown_asyncgens"):
            logging.debug("[IPDB Server] Shutting down async generators in the event loop")
            await self.loop.shutdown_asyncgens()
        else:
            logging.debug("[IPDB Server] No async generators to shutdown in the event loop")
        logging.debug("[IPDB Server] Stopping the event loop")
        self.loop.stop()

    def shutdown(self):
        """
        Cleanup logic for the event loop started in start_in_thread.
        Shutdown the DAP server and the loop gracefully.
        """
        if threading.current_thread() == self.thread:
            raise RuntimeError("Cannot shutdown server from within the event loop thread")
        logging.info("[IPDB Server] Shutting down DAP server")
        # Handle case where there is no loop or loop is already closed
        if self.loop is None:
            if self.server is not None:
                msg = "[IPDB Server] Event loop is None, but server is running, cannot shutdown"
                logging.error(msg)
                raise RuntimeError(msg)
            else:
                # We are already shut down
                logging.debug("[IPDB Server] Loop and server are already shut down, nothing to do")
                return
        elif self.loop.is_closed():
            logging.debug("[IPDB Server] Event loop is already closed, nothing to do")
            return
        # Handle non closed loop and running loop
        if self.loop.is_running():
            # Shut down server if it is running
            logging.debug(
                "[IPDB Server] Event loop is running not closed, proceeding to cleanup tasks"
            )
            if self.server is not None:
                logging.debug("[IPDB Server] Shutting down server in the event loop")
                asyncio.run_coroutine_threadsafe(self.shutdown_server(), self.loop).result()
                logging.debug("[IPDB Server] Server shutdown complete")
            # This needs to be called on a running loop
            asyncio.run_coroutine_threadsafe(self.cleanup_running_loop(), self.loop).result()
        else:
            if self.server is not None:
                msg = "[IPDB Server] Event loop is not running, but server is running, cannot shutdown"
                logging.error(msg)
                raise RuntimeError(msg)
        logging.debug("[IPDB Server] Closing event loop")
        self.loop.close()
        self.loop = None
        if self.thread.is_alive():
            msg = "[IPDB Server] Event loop thread is still alive after closing the loop"
            logging.error(msg)
            raise RuntimeError(msg)
        else:
            self.thread = None
        logging.info("[IPDB Server] DAP server shutdown complete")

    async def shutdown_server(self):
        """
        Shutdown the DAP server gracefully and notify the client if connected.
        To notify the client only once, we use a threading event `_shutdown_event`.
        """
        logging.info("[IPDB Server] Shutting down DAP server")
        if self.loop is None:
            if self.server is not None:
                logging.error("[IPDB Server] Event loop is None, cannot shutdown server")
                raise RuntimeError("Event loop is not running, cannot shutdown server")
            else:
                # We are already shut down
                logging.debug("[IPDB Server] Server is already shut down, nothing to do")
                return
        # Only notify the client once, we set the shutdown event afterwards
        if self.client_writer and self.loop.is_running() and not self._shutdown_event.is_set():
            logging.debug("[IPDB Server] Notifying client of shutdown")
            await self.notify_terminated("shutdown")
            logging.debug("[IPDB Server] Notifying client of shutdown complete")
            self._shutdown_event.set()
        else:
            logging.debug(
                "[IPDB Server] No client connected or already notified, skipping shutdown notification"
            )
        # Cancel all tasks in the event loop
        # tasks = [t for t in asyncio.all_tasks(self.loop) if not t.done()]
        # for task in tasks:
        #     task.cancel()
        # if tasks:
        #     logging.debug("[IPDB Server] Cancelling all tasks in the event loop")
        #     await asyncio.gather(*tasks, return_exceptions=True)
        # else:
        #     logging.debug("[IPDB Server] No tasks to cancel in the event loop")
        # Close the server
        if self.server.is_serving():
            logging.debug("[IPDB Server] Closing server and waiting for it to close")
            self.server.close()
            await self.server.wait_closed()
            logging.debug("[IPDB Server] Server closed")
            if self.server.is_serving():
                msg = "[IPDB Server] Server is still serving after close, this should not happen"
                logging.error(msg)
                raise RuntimeError(msg)
        else:
            logging.debug("[IPDB Server] Server is not serving, nothing to close")

    def _run_loop(self):
        asyncio.set_event_loop(self.loop)
        try:
            self.loop.create_task(self.start_server())
            self.loop.run_forever()
        except Exception as e:
            logging.error(f"[IPDB Server] Event loop exception: {e}")
        finally:
            logging.debug("[IPDB Server] Event loop stopping, shutting down")
            if not self.loop.is_closed() and self.loop.is_running():
                asyncio.run_coroutine_threadsafe(self.shutdown_server(), self.loop).result()

    def start_in_thread(self):
        self.thread = threading.Thread(target=self._run_loop, daemon=True)
        self.thread.start()

    def set_trace(self):
        if not self.server:
            logging.debug("[IPDB Server] Starting DAP server in a new thread")
            self.start_in_thread()
        else:
            logging.debug("[IPDB Server] DAP server already running, setting trace")
        # Enter ipdb prompt here
        try:
            return self.debugger.set_trace()
        except Exception as e:
            logging.error(
                f"[IPDB Server] Error of type {e.__class__.__name__} while setting trace: {e}"
            )
            raise


# Create singleton adapter
ipdab = IPDBAdapterServer()


def _cleanup():
    logging.debug("[IPDB Server] Cleaning up IPDB adapter")
    ipdab.shutdown()


atexit.register(_cleanup)


def set_trace():
    logging.debug("[IPDB Server] Setting trace in IPDB adapter")
    retval = ipdab.set_trace()
    logging.debug("[IPDB Server] Trace set, returning from set_trace")
    return retval


if __name__ == "__main__":
    # Simple example usage:
    import time

    logging.basicConfig(
        level=logging.DEBUG,
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
