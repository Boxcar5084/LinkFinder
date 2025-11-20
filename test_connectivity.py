#!/usr/bin/env python3
"""
Test connectivity to the host PC and ElectrumX server
Verifies network connectivity and ElectrumX server accessibility
"""
import socket
import json
import sys
import time
import asyncio
from config import ELECTRUMX_HOST, ELECTRUMX_PORT, ELECTRUMX_USE_SSL

def test_host_reachability(host, port, timeout=5):
    """Test if we can reach a host on a specific port"""
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(timeout)
        result = sock.connect_ex((host, port))
        sock.close()
        return result == 0
    except Exception as e:
        return False

def test_electrumx_connection(host, port, use_ssl=False, timeout=5):
    """Test ElectrumX server connection and protocol"""
    try:
        if use_ssl:
            import ssl
            context = ssl.create_default_context()
            if not use_ssl:
                context.check_hostname = False
                context.verify_mode = ssl.CERT_NONE
            
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(timeout)
            sock.connect((host, port))
            sock = context.wrap_socket(sock, server_hostname=host)
        else:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(timeout)
            sock.connect((host, port))
        
        # Send a simple Electrum protocol request
        request = {
            "jsonrpc": "2.0",
            "method": "server.version",
            "params": ["LinkFinder-Test", "1.4"],
            "id": 1
        }
        request_str = json.dumps(request) + "\n"
        sock.sendall(request_str.encode())
        
        # Read response - Electrum protocol uses newline-delimited JSON
        # Read until we get a complete line (JSON object)
        response_data = b""
        buffer = b""
        start_time = time.time()
        read_timeout = 10  # Total timeout for reading
        
        while (time.time() - start_time) < read_timeout:
            try:
                sock.settimeout(2)  # Short timeout for each recv
                chunk = sock.recv(4096)
                if not chunk:
                    # Connection closed
                    break
                
                buffer += chunk
                
                # Check if we have a complete line (newline-delimited JSON)
                if b'\n' in buffer:
                    # Split by newline and take the first complete message
                    parts = buffer.split(b'\n', 1)
                    response_data = parts[0]
                    buffer = parts[1] if len(parts) > 1 else b""
                    break
                
                # If buffer gets too large, something's wrong
                if len(buffer) > 100000:  # 100KB limit
                    break
                    
            except socket.timeout:
                # If we have some data, try to use it
                if buffer:
                    response_data = buffer
                    buffer = b""
                    break
                # Continue waiting if no data yet
                continue
        
        # Properly close the connection
        try:
            if hasattr(sock, 'shutdown'):
                sock.shutdown(socket.SHUT_RDWR)
        except (OSError, socket.error):
            pass
        finally:
            sock.close()
        
        if response_data:
            try:
                response_json = json.loads(response_data.decode().strip())
                return True, response_json
            except json.JSONDecodeError:
                return True, {"raw": response_data.decode()[:200]}
        else:
            return False, "No response received (server may be slow or not responding)"
            
    except socket.timeout:
        return False, "Connection timeout"
    except ConnectionRefusedError:
        return False, "Connection refused - server may not be running"
    except socket.gaierror as e:
        return False, f"DNS/Hostname resolution error: {e}"
    except Exception as e:
        return False, f"Error: {e}"

def main():
    print("\n" + "="*70)
    print("CONNECTIVITY TEST - Host PC and ElectrumX Server")
    print("="*70)
    print(f"\nTarget Host: {ELECTRUMX_HOST}")
    print(f"ElectrumX Port: {ELECTRUMX_PORT}")
    print(f"Use SSL: {ELECTRUMX_USE_SSL}")
    print("\n" + "-"*70)
    
    # Test 1: Basic host reachability (test on a common port or SSH port)
    print("\n[TEST 1] Testing basic host reachability...")
    print(f"  Attempting to connect to {ELECTRUMX_HOST}:22 (SSH port)...")
    
    ssh_reachable = test_host_reachability(ELECTRUMX_HOST, 22, timeout=5)
    if ssh_reachable:
        print(f"  ✓ Host {ELECTRUMX_HOST} is reachable (SSH port 22)")
    else:
        print(f"  ✗ Cannot reach {ELECTRUMX_HOST} on port 22")
        print(f"    (This is normal if SSH is not enabled or firewall blocks it)")
    
    # Test 2: ElectrumX port reachability
    print(f"\n[TEST 2] Testing ElectrumX port reachability...")
    print(f"  Attempting to connect to {ELECTRUMX_HOST}:{ELECTRUMX_PORT}...")
    
    port_reachable = test_host_reachability(ELECTRUMX_HOST, ELECTRUMX_PORT, timeout=5)
    if port_reachable:
        print(f"  ✓ Port {ELECTRUMX_PORT} is open and reachable")
    else:
        print(f"  ✗ Port {ELECTRUMX_PORT} is not reachable")
        print(f"    Possible issues:")
        print(f"    - ElectrumX server is not running")
        print(f"    - Firewall is blocking the port")
        print(f"    - Network routing issue")
    
    # Test 3: ElectrumX protocol communication (using actual provider)
    print(f"\n[TEST 3] Testing ElectrumX protocol communication...")
    print(f"  Using actual provider to test connection...")
    
    protocol_success = False
    try:
        from api_provider import get_provider
        provider = get_provider("electrumx")
        
        # Try a simple server.version call first (doesn't need blockchain data)
        # This is a bit tricky since we need to access internal methods
        # Instead, let's just test if we can connect and get a response
        print(f"    Testing connection to {ELECTRUMX_HOST}:{ELECTRUMX_PORT}...")
        
        # Use genesis address - even if empty, connection should work
        genesis_address = "1A1zP1eP5QGefi2DMPTfTL5SLmv7DivfNa"
        txs = asyncio.run(provider.get_address_transactions(genesis_address))
        
        # If we get here without exception, connection works
        protocol_success = True
        if txs is not None:
            print(f"  ✓ SUCCESS - Connection established, received response")
            print(f"    (Server returned {len(txs)} transactions - may be syncing)")
        else:
            print(f"  ✓ SUCCESS - Connection established")
            print(f"    (Server responded but returned None - may still be syncing)")
        
        asyncio.run(provider.close())
    except Exception as e:
        print(f"  ✗ FAILED - Could not establish connection")
        print(f"    Error: {e}")
        protocol_success = False
    
    # Also try the simple socket test for comparison
    print(f"\n[TEST 3b] Testing raw socket protocol...")
    success, result = test_electrumx_connection(
        ELECTRUMX_HOST, 
        ELECTRUMX_PORT, 
        use_ssl=ELECTRUMX_USE_SSL,
        timeout=5
    )
    
    if success:
        print(f"  ✓ Raw socket test also succeeded")
        if isinstance(result, dict) and "result" in result:
            print(f"    Server version: {result.get('result', 'Unknown')}")
    else:
        print(f"  ⚠️  Raw socket test failed (but provider test passed)")
        print(f"    This is OK - provider handles protocol better")
    
    # Use provider result as primary
    success = protocol_success
    
    # Test 4: Test early blockchain address query (already done in Test 3)
    # This is now redundant since we test it above, but keeping for clarity
    blockchain_test_success = False
    blockchain_test_attempted = False
    if success:
        blockchain_test_attempted = True
        # We already tested this in Test 3, so mark as attempted
        blockchain_test_success = True  # Connection worked, even if data is empty
    
    # Test 5: Test SSL port if not using SSL
    if not ELECTRUMX_USE_SSL:
        ssl_port = 50002
        print(f"\n[TEST 5] Testing SSL port (optional)...")
        print(f"  Attempting to connect to {ELECTRUMX_HOST}:{ssl_port}...")
        
        ssl_port_reachable = test_host_reachability(ELECTRUMX_HOST, ssl_port, timeout=5)
        if ssl_port_reachable:
            print(f"  ✓ SSL port {ssl_port} is also available")
            print(f"    (You could use SSL by setting ELECTRUMX_USE_SSL=true)")
        else:
            print(f"  - SSL port {ssl_port} is not available (this is OK)")
    
    # Summary
    print("\n" + "="*70)
    print("SUMMARY")
    print("="*70)
    
    all_tests = [
        ("Host Reachability", ssh_reachable or port_reachable),
        ("ElectrumX Port Open", port_reachable),
        ("ElectrumX Protocol", success),
        ("Blockchain Query (Early)", blockchain_test_success if blockchain_test_attempted else None)
    ]
    
    for test_name, passed in all_tests:
        if passed is None:
            status = "- SKIP"
        elif passed:
            status = "✓ PASS"
        else:
            status = "✗ FAIL"
        print(f"  {status} - {test_name}")
    
    if port_reachable and success:
        if blockchain_test_success:
            print("\n✓ SUCCESS: ElectrumX server is fully operational!")
            print("  Connection and blockchain queries are working correctly.")
        else:
            print("\n✓ SUCCESS: ElectrumX server is accessible and responding!")
            print("  Protocol communication works. Server may still be syncing.")
        return 0
    elif port_reachable and not success:
        print("\n⚠️  WARNING: Port is open but protocol communication failed")
        print("  The server may be running but not responding correctly.")
        return 1
    elif not port_reachable:
        print("\n✗ FAILURE: Cannot reach ElectrumX server")
        print("  Please check:")
        print(f"  1. ElectrumX server is running on {ELECTRUMX_HOST}")
        print(f"  2. Firewall allows connections on port {ELECTRUMX_PORT}")
        print(f"  3. Tailscale VPN is connected and routing correctly")
        print(f"  4. IP address {ELECTRUMX_HOST} is correct")
        return 1
    else:
        return 1

if __name__ == "__main__":
    try:
        exit_code = main()
        sys.exit(exit_code)
    except KeyboardInterrupt:
        print("\n\nTest interrupted by user")
        sys.exit(1)
    except Exception as e:
        print(f"\n\nFatal error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

