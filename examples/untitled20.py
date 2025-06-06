# -*- coding: utf-8 -*-
"""
Created on Fri Jun  6 16:21:44 2025

@author: ROB6027
"""

import socket

def send_dap_message(sock, message_json: str):
    message_bytes = message_json.encode("utf-8")
    header = f"Content-Length: {len(message_bytes)}\r\n\r\n".encode("utf-8")
    sock.sendall(header + message_bytes)

def recv_dap_message(sock):
    # Read headers
    header_data = b""
    while b"\r\n\r\n" not in header_data:
        header_data += sock.recv(1)
    headers, _ = header_data.split(b"\r\n\r\n", 1)
    # Parse Content-Length
    content_length = 0
    for line in headers.decode().split("\r\n"):
        if line.lower().startswith("content-length:"):
            content_length = int(line.split(":")[1].strip())
    # Read content_length bytes of body
    body = b""
    while len(body) < content_length:
        body += sock.recv(content_length - len(body))
    return body.decode()

def main():
    host = "127.0.0.1"
    port = 9000  # Change if your adapter uses another port

    initialize_request = """{
        "seq": 1,
        "type": "request",
        "command": "initialize",
        "arguments": {
            "clientID": "test-client",
            "adapterID": "ipdb",
            "pathFormat": "path",
            "linesStartAt1": true,
            "columnsStartAt1": true,
            "supportsVariableType": true,
            "supportsVariablePaging": true,
            "supportsRunInTerminalRequest": false
        }
    }"""

    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.connect((host, port))
        print("Connected to DAP adapter")

        send_dap_message(sock, initialize_request)
        print("Sent initialize request")

        response = recv_dap_message(sock)
        print("Received response:")
        print(response)

if __name__ == "__main__":
    main()