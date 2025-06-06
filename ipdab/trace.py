import ipdb
import asyncio
import threading


class IPDBAdapterServer:
    def __init__(self):
        self.server = None
        self.loop = None
        self.debugger = ipdb.Debugger()

    async def start_server(self):
        self.server = await asyncio.start_server(self.handle_client, "127.0.0.1", 9000)
        await self.server.serve_forever()

    def start_in_thread(self):
        def run_loop():
            self.loop = asyncio.new_event_loop()
            asyncio.set_event_loop(self.loop)
            self.loop.run_until_complete(self.start_server())

        threading.Thread(target=run_loop, daemon=True).start()

    async def handle_client(self, reader, writer):
        # Handle incoming DAP messages here
        pass

    def set_trace(self):
        if not self.server:
            self.start_in_thread()
        self.debugger.set_trace()


ipdab = IPDBAdapterServer()


def set_trace():
    ipdab.set_trace()

