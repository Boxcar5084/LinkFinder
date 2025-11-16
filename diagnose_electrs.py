#!/usr/bin/env python3
import socket
import json
import time

host = "100.94.34.56"
port = 50001

print("=" * 60)
print("TEST 1: Sending JSON-RPC request")
print("=" * 60)

sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
sock.settimeout(10)

try:
    sock.connect((host, port))
    print(f"âœ“ Connected to {host}:{port}")
    
    request = {"jsonrpc": "2.0", "method": "blockchain.headers.subscribe", "params": [], "id": 1}
    message = json.dumps(request) + "\n"
    
    print(f"Sending: {message.strip()}")
    sock.sendall(message.encode())
    
    time.sleep(2)
    sock.setblocking(False)
    
    try:
        response = sock.recv(4096)
        if response:
            print(f"âœ“ Received {len(response)} bytes")
            print(f"Data: {response[:200]}")
        else:
            print("âœ— Received empty response")
    except BlockingIOError:
        print("âœ— No response (timeout)")
    
    sock.close()
except Exception as e:
    print(f"âœ— Error: {e}")

print()
print("=" * 60)
print("TEST 2: Send address query")
print("=" * 60)

sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
sock.settimeout(5)

try:
    sock.connect((host, port))
    
    request = {
        "jsonrpc": "2.0",
        "method": "blockchain.address.get_history",
        "params": ["1A1z7agoat4FqCnf4Xy7jJn1eJd7azHXzA"],
        "id": 1
    }
    message = json.dumps(request) + "\n"
    
    print("Sending address query...")
    sock.sendall(message.encode())
    
    response_data = b""
    while True:
        try:
            chunk = sock.recv(4096)
            if not chunk:
                break
            response_data += chunk
        except socket.timeout:
            break
    
    if response_data:
        try:
            response = json.loads(response_data.decode())
            print(f"âœ“ Got JSON response: {response}")
        except Exception as parse_err:
            print(f"âœ“ Got {len(response_data)} bytes (not JSON)")
            print(f"Raw: {response_data[:100]}")
    else:
        print("âœ— No response data")
    
    sock.close()
except Exception as e:
    print(f"âœ— Error: {e}")

print()
print("Done!")