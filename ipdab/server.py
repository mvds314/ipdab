import asyncio
import ipdb
import json
import sys

# Global debugger instance (we'll step into this one from outside)
debugger = ipdb.Debugger()


# Simple DAP message parsing helpers
async def read_dap_message(reader):
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


def encode_dap_message(payload):
    body = json.dumps(payload)
    return f"Content-Length: {len(body)}\r\n\r\n{body}".encode()


async def handle_client(reader, writer):
    while True:
        try:
            msg = await read_dap_message(reader)
        except Exception as e:
            print(f"Error reading message: {e}")
            break

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
            # Dummy accept, we don't launch the program here
            response["body"] = {}

        elif cmd == "continue":
            debugger.set_continue()

        elif cmd == "next":
            debugger.set_next(sys._getframe().f_back)

        elif cmd == "stepIn":
            debugger.set_step()

        elif cmd == "pause":
            debugger.set_trace(sys._getframe().f_back)

        elif cmd == "evaluate":
            expr = msg.get("arguments", {}).get("expression", "")
            try:
                result = eval(expr, globals(), locals())
                response["body"] = {"result": str(result), "variablesReference": 0}
            except Exception as e:
                response["body"] = {"result": f"Error: {e}", "variablesReference": 0}

        else:
            response["success"] = False
            response["message"] = f"Unsupported command: {cmd}"

        writer.write(encode_dap_message(response))
        await writer.drain()

    writer.close()
    await writer.wait_closed()


async def main():
    server = await asyncio.start_server(handle_client, "127.0.0.1", 9000)
    print("[ipdb-dap] listening on port 9000")
    async with server:
        await server.serve_forever()


if __name__ == "__main__":
    asyncio.run(main())

