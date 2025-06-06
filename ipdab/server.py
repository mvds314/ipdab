# ipdb_dap_adapter.py
import asyncio
import json

# Track external trigger from script
external_triggered = asyncio.Event()


# Minimal DAP message parser
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


async def handle_dap_client(reader, writer):
    print("[DAP] Client connected")
    while True:
        try:
            msg = await read_dap_message(reader)
        except Exception as e:
            print(f"[DAP] Error reading message: {e}")
            break
        else:
            if msg is None:
                print("[DAP] Client disconnected")
                break
            else:
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

        elif cmd == "continue":
            print("[DAP] Continue received (script must control ipdb)")

        elif cmd == "pause":
            print("[DAP] Pause received — signal script externally if needed")

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
        print(f"[DAP] Sent response: {response}")

    writer.close()
    await writer.wait_closed()


# Listen for external signal from script
async def listen_for_trace_signal():
    async def handle_trace(reader, writer):
        line = await reader.readline()
        if line.strip() == b"START":
            print("[Trigger] Script entered ipdb.set_trace()")
            external_triggered.set()
        writer.close()
        await writer.wait_closed()

    server = await asyncio.start_server(handle_trace, "127.0.0.1", 9001)
    print("[Trigger] Listening on port 9001")
    async with server:
        await server.serve_forever()


async def main():
    dap_server = await asyncio.start_server(handle_dap_client, "127.0.0.1", 9000)
    trigger_task = asyncio.create_task(listen_for_trace_signal())
    print("[Adapter] DAP on 9000, trigger on 9001")
    async with dap_server:
        await asyncio.gather(dap_server.serve_forever(), trigger_task)


if __name__ == "__main__":
    asyncio.run(main())
