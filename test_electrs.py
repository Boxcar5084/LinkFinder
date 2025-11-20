
import socket
import json

host = "192.168.7.218"   #"100.94.34.56"
port = 50001

sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
sock.settimeout(5)

try:
    sock.connect((host, port))
    print(f"✓ Connected to {host}:{port}")
    
    # Send a simple Electrum request
    request = {"jsonrpc": "2.0", "method": "blockchain.headers.subscribe", "params": [], "id": 1}
    sock.sendall((json.dumps(request) + "\n").encode())
    
    # Try to receive response
    response = sock.recv(4096)
    if response:
        print(f"✓ Received response: {response.decode()[:100]}")
    else:
        print("✗ No response received")
    
    sock.close()
except socket.timeout:
    print(f"✗ Timeout connecting to {host}:{port}")
except ConnectionRefusedError:
    print(f"✗ Connection refused by {host}:{port}")
except Exception as e:
    print(f"✗ Error: {e}")