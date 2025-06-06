import asyncio
import ipdb

debugger = ipdb.Debugger()


async def handle_request(reader, writer):
    while True:
        data = await reader.read(100)
        command = data.decode().rstrip()

        if command == "step":
            debugger.set_step()
        elif command == "continue":
            debugger.set_continue()
        elif command == "pause":
            debugger.set_trace()
        elif command.startswith("eval "):
            expression = command[5:]
            result = eval(expression)
            writer.write(f"Result: {result}\n".encode())

        writer.write(b"Command executed\n")
        await writer.drain()


async def main():
    server = await asyncio.start_server(handle_request, "127.0.0.1", 9999)
    async with server:
        await server.serve_forever()


asyncio.run(main())
