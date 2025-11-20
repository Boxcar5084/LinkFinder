import socket
import json
import time
import sys

def test_electrs_with_protection():
    """
    Test electrs with proper error handling and protection against hanging
    """
    host = "192.168.7.218"
    port = 50001
    
    print("\n" + "="*60)
    print("ELECTRS DIAGNOSTIC TEST (WITH PROTECTION)")
    print("="*60)
    
    # TEST 1: Basic connectivity
    print("\nTEST 1: Basic Connectivity")
    print("-" * 60)
    
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(5)
        sock.connect((host, port))
        print(f"✓ Connected to {host}:{port}")
        
        # Test headers.subscribe (lightweight, fast)
        request = {
            "jsonrpc": "2.0",
            "method": "blockchain.headers.subscribe",
            "params": [],
            "id": 1
        }
        
        sock.sendall((json.dumps(request) + '\n').encode('utf-8'))
        
        # Improved response reading
        response_data = b""
        buffer = b""
        start_time = time.time()
        
        while time.time() - start_time < 5:
            try:
                sock.settimeout(2)
                chunk = sock.recv(4096)
                if not chunk:
                    break
                
                buffer += chunk
                if b'\n' in buffer:
                    parts = buffer.split(b'\n', 1)
                    response_data = parts[0]
                    break
            except socket.timeout:
                if buffer:
                    response_data = buffer
                    break
                continue
        
        sock.close()
        
        if response_data:
            try:
                result = json.loads(response_data.decode('utf-8'))
                if 'result' in result:
                    height = result['result'].get('height', 0)
                    print(f"✓ Headers subscribe works")
                    print(f"  Current block height: {height}")
                else:
                    print(f"✗ Headers subscribe failed: {result}")
            except json.JSONDecodeError as e:
                print(f"✗ Failed to parse response: {e}")
                print(f"  Response: {response_data[:200]}")
        else:
            print(f"✗ No response received")
        
    except Exception as e:
        print(f"✗ Basic connectivity failed: {e}")
        return
    
    # TEST 2: Test server.ping (verify responsiveness)
    print("\nTEST 2: Server Ping (Responsiveness)")
    print("-" * 60)
    
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(5)
        sock.connect((host, port))
        
        request = {
            "jsonrpc": "2.0",
            "method": "server.ping",
            "params": [],
            "id": 2
        }
        
        sock.sendall((json.dumps(request) + '\n').encode('utf-8'))
        
        # Improved response reading
        response_data = b""
        buffer = b""
        start_time = time.time()
        
        while time.time() - start_time < 5:
            try:
                sock.settimeout(2)
                chunk = sock.recv(4096)
                if not chunk:
                    break
                
                buffer += chunk
                if b'\n' in buffer:
                    parts = buffer.split(b'\n', 1)
                    response_data = parts[0]
                    break
            except socket.timeout:
                if buffer:
                    response_data = buffer
                    break
                continue
        
        sock.close()
        
        if response_data:
            try:
                result = json.loads(response_data.decode('utf-8'))
                if 'result' in result or result.get('result') is None:
                    print(f"✓ Server responds to ping - electrs is responsive")
                else:
                    print(f"✗ Unexpected ping response: {result}")
            except json.JSONDecodeError as e:
                print(f"✗ Failed to parse ping response: {e}")
        else:
            print(f"✗ No response to ping")
    except Exception as e:
        print(f"✗ Server ping failed: {e}")
    
    # TEST 3: Test with SIMPLE empty scripthash first (no transactions)
    print("\nTEST 3: Query Empty Scripthash (No Transactions)")
    print("-" * 60)
    
    # Use an obviously unused scripthash (all zeros)
    empty_scripthash = "aa" * 32  # 64 character hex string, all 'aa'
    
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(10)
        sock.connect((host, port))
        
        # Try balance query directly WITHOUT subscribe
        request = {
            "jsonrpc": "2.0",
            "method": "blockchain.scripthash.get_balance",
            "params": [empty_scripthash],
            "id": 3
        }
        
        print(f"Querying unused scripthash (should have 0 balance)...")
        sock.sendall((json.dumps(request) + '\n').encode('utf-8'))
        
        response = sock.recv(4096)
        result = json.loads(response.decode('utf-8'))
        
        if 'result' in result:
            balance = result['result']
            print(f"✓ Query succeeded!")
            print(f"  Confirmed: {balance.get('confirmed', 0)} satoshis")
            print(f"  Unconfirmed: {balance.get('unconfirmed', 0)} satoshis")
        elif 'error' in result:
            print(f"✗ Query returned error: {result['error']['message']}")
        
        sock.close()
    except socket.timeout:
        print(f"✗ Empty scripthash query timed out (possible indexing issue)")
    except Exception as e:
        print(f"✗ Query failed: {e}")
    
    # TEST 4: Test the problematic scripthash with short timeout
    print("\nTEST 4: Query Known-Active Scripthash (Short Timeout)")
    print("-" * 60)
    
    active_scripthash = "8b01df4e368ea28f8dc0423bcf7a4923e3a12d307c875e47a0cfbf90b5c39161"
    
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(5)  # SHORT timeout to avoid hanging
        sock.connect((host, port))
        
        request = {
            "jsonrpc": "2.0",
            "method": "blockchain.scripthash.get_balance",
            "params": [active_scripthash],
            "id": 4
        }
        
        print(f"Querying known-active scripthash (with 5s timeout)...")
        sock.sendall((json.dumps(request) + '\n').encode('utf-8'))
        
        # Improved response reading - read until newline
        response_data = b""
        buffer = b""
        start_time = time.time()
        
        while time.time() - start_time < 5:  # 5 second timeout
            try:
                sock.settimeout(1)  # Short timeout for each recv
                chunk = sock.recv(4096)
                if not chunk:
                    break
                
                buffer += chunk
                if b'\n' in buffer:
                    parts = buffer.split(b'\n', 1)
                    response_data = parts[0]
                    break
            except socket.timeout:
                if buffer:
                    # Try to parse what we have
                    response_data = buffer
                    break
                continue
        
        sock.close()
        
        if not response_data:
            print(f"✗ No response received within timeout")
            print(f"  This suggests electrs is hung/indexing on this address")
            print(f"  SOLUTION: Restart electrs or check its logs")
        else:
            try:
                result = json.loads(response_data.decode('utf-8'))
                if 'result' in result:
                    balance = result['result']
                    print(f"✓ Query succeeded!")
                    print(f"  Confirmed: {balance.get('confirmed', 0):,} satoshis")
                    print(f"  Unconfirmed: {balance.get('unconfirmed', 0):,} satoshis")
                elif 'error' in result:
                    print(f"✗ Query returned error: {result['error']}")
                else:
                    print(f"✗ Unexpected response: {result}")
            except json.JSONDecodeError as e:
                print(f"✗ Failed to parse response: {e}")
                print(f"  Response: {response_data[:200]}")
        
    except socket.timeout:
        print(f"✗ Query timed out on known-active scripthash")
        print(f"  This suggests electrs is hung/indexing on this address")
        print(f"  SOLUTION: Restart electrs or check its logs")
    except Exception as e:
        print(f"✗ Query failed: {e}")
    
    # TEST 5: Check electrs version/info
    print("\nTEST 5: Get Server Version Info")
    print("-" * 60)
    
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(5)
        sock.connect((host, port))
        
        request = {
            "jsonrpc": "2.0",
            "method": "server.version",
            "params": ["LinkFinder", "1.4"],
            "id": 5
        }
        
        sock.sendall((json.dumps(request) + '\n').encode('utf-8'))
        
        # Improved response reading
        response_data = b""
        buffer = b""
        start_time = time.time()
        
        while time.time() - start_time < 5:
            try:
                sock.settimeout(1)
                chunk = sock.recv(4096)
                if not chunk:
                    break
                
                buffer += chunk
                if b'\n' in buffer:
                    parts = buffer.split(b'\n', 1)
                    response_data = parts[0]
                    break
            except socket.timeout:
                if buffer:
                    response_data = buffer
                    break
                continue
        
        sock.close()
        
        if response_data:
            try:
                result = json.loads(response_data.decode('utf-8'))
                if 'result' in result:
                    version_info = result['result']
                    print(f"✓ Server info: {version_info}")
                elif 'error' in result:
                    print(f"✗ Server returned error: {result['error']}")
                else:
                    print(f"✗ Unexpected response: {result}")
            except json.JSONDecodeError as e:
                print(f"✗ Failed to parse response: {e}")
        else:
            print(f"✗ No response received")
    except socket.timeout:
        print(f"✗ Version check timed out")
    except Exception as e:
        print(f"✗ Version check failed: {e}")
    
    # TEST 6: Test address.get_history (what the provider actually uses)
    print("\nTEST 6: Query Address History (Provider Method)")
    print("-" * 60)
    
    # Use a known address (Genesis block address)
    test_address = "1A1zP1eP5QGefi2DMPTfTL5SLmv7DivfNa"
    
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(10)  # Longer timeout for history queries
        sock.connect((host, port))
        
        request = {
            "jsonrpc": "2.0",
            "method": "blockchain.address.get_history",
            "params": [test_address],
            "id": 6
        }
        
        print(f"Querying address history for {test_address}...")
        sock.sendall((json.dumps(request) + '\n').encode('utf-8'))
        
        # Improved response reading
        response_data = b""
        buffer = b""
        start_time = time.time()
        
        while time.time() - start_time < 10:
            try:
                sock.settimeout(2)
                chunk = sock.recv(4096)
                if not chunk:
                    break
                
                buffer += chunk
                if b'\n' in buffer:
                    parts = buffer.split(b'\n', 1)
                    response_data = parts[0]
                    break
            except socket.timeout:
                if buffer:
                    response_data = buffer
                    break
                continue
        
        sock.close()
        
        if response_data:
            try:
                result = json.loads(response_data.decode('utf-8'))
                if 'result' in result:
                    history = result['result']
                    if isinstance(history, list):
                        print(f"✓ Address history query succeeded!")
                        print(f"  Found {len(history)} transaction entries")
                    else:
                        print(f"✓ Query succeeded but unexpected format: {type(history)}")
                elif 'error' in result:
                    print(f"✗ Query returned error: {result['error']}")
                else:
                    print(f"✗ Unexpected response: {result}")
            except json.JSONDecodeError as e:
                print(f"✗ Failed to parse response: {e}")
        else:
            print(f"✗ No response received (timeout after 10s)")
            print(f"  This suggests electrs may be slow or stuck")
    except socket.timeout:
        print(f"✗ Address history query timed out")
        print(f"  electrs may be slow or still indexing")
    except Exception as e:
        print(f"✗ Query failed: {e}")
    
    print("\n" + "="*60)
    print("DIAGNOSTIC COMPLETE")
    print("="*60)
    print("\nINTERPRETATION:")
    print("- If TEST 4 times out: electrs is stuck on specific scripthash, restart electrs")
    print("- If TEST 3 fails: electrs indexing may be incomplete")
    print("- If TEST 1-2 work but TEST 4 fails: specific scripthash causing hang")
    print("- If TEST 6 times out: electrs may be slow or still syncing/indexing")
    print("\nRECOMMENDATIONS:")
    print("1. Check electrs logs on the server (192.168.7.218)")
    print("2. Verify Bitcoin Core is fully synced and running")
    print("3. Check electrs database/index status")
    print("4. Consider restarting electrs if queries consistently timeout")
    print("5. For production use, implement retry logic with exponential backoff")

if __name__ == "__main__":
    test_electrs_with_protection()
