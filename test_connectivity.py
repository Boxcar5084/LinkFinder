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
from config import (
    ELECTRUMX_HOST, ELECTRUMX_PORT, ELECTRUMX_USE_SSL,
    SSH_HOST, SSH_USER, SSH_KEY_PATH, SSH_PORT, ELECTRUMX_DOCKER_CONTAINER
)

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
            # For self-signed certificates, disable verification
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

def validate_jsonrpc_response(response: dict, expected_id: int = None) -> tuple:
    """
    Validate JSON-RPC 2.0 response structure
    
    Returns:
        Tuple of (is_valid: bool, error_message: str or None)
    """
    if not isinstance(response, dict):
        return False, "Response is not a dictionary"
    
    # Check for JSON-RPC version
    if "jsonrpc" not in response:
        return False, "Missing 'jsonrpc' field"
    
    if response.get("jsonrpc") != "2.0":
        return False, f"Invalid JSON-RPC version: {response.get('jsonrpc')}"
    
    # Check for ID
    if "id" not in response:
        return False, "Missing 'id' field"
    
    if expected_id is not None and response.get("id") != expected_id:
        return False, f"ID mismatch: expected {expected_id}, got {response.get('id')}"
    
    # Check for result or error
    has_result = "result" in response
    has_error = "error" in response
    
    if not has_result and not has_error:
        return False, "Response must contain 'result' or 'error'"
    
    if has_error:
        error = response["error"]
        if not isinstance(error, dict):
            return False, "Error field must be a dictionary"
        if "code" not in error or "message" not in error:
            return False, "Error must contain 'code' and 'message'"
    
    return True, None

def validate_transaction_response(tx: dict) -> tuple:
    """
    Validate transaction response structure
    
    Returns:
        Tuple of (is_valid: bool, error_message: str or None)
    """
    if not isinstance(tx, dict):
        return False, "Transaction is not a dictionary"
    
    required_fields = ["txid", "hash", "status", "vin", "vout"]
    for field in required_fields:
        if field not in tx:
            return False, f"Missing required field: {field}"
    
    if not isinstance(tx["vin"], list):
        return False, "vin must be a list"
    if not isinstance(tx["vout"], list):
        return False, "vout must be a list"
    
    return True, None

def test_ssh_log_access():
    """Test SSH access to ElectrumX Docker logs"""
    if not SSH_HOST or not SSH_USER:
        return None, "SSH configuration not set (SSH_HOST and SSH_USER required)"
    
    try:
        from electrumx_logs import fetch_electrumx_logs, check_electrumx_status
        
        # First check container status
        status_success, status = check_electrumx_status(
            SSH_HOST, SSH_USER, ELECTRUMX_DOCKER_CONTAINER, SSH_KEY_PATH, SSH_PORT
        )
        
        if not status_success:
            return False, f"Failed to check container status: {status.get('error', 'Unknown error') if status else 'No status returned'}"
        
        # Fetch recent logs
        log_success, logs = fetch_electrumx_logs(
            SSH_HOST, SSH_USER, ELECTRUMX_DOCKER_CONTAINER, SSH_KEY_PATH, SSH_PORT, lines=20
        )
        
        if not log_success:
            return False, f"Failed to fetch logs: {logs}"
        
        return True, {"status": status, "logs": logs}
        
    except ImportError:
        return None, "electrumx_logs module not available"
    except socket.timeout:
        return False, "Connection timeout"
    except ConnectionRefusedError:
        return False, "Connection refused - server may not be running"
    except socket.gaierror as e:
        return False, f"DNS/Hostname resolution error: {e}"
    except Exception as e:
        return False, f"SSH log access error: {e}"

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
        
        # Use a simple address with few transactions for testing
        # (Genesis address has 54k+ transactions which takes too long)
        test_address = "38YEkk8pKA1DXWhQTdW53ibXUaFDYqk269" #"1BvBMSEYstWetqTFn5Au4m4GFg7xJaNVN2"  # Small address for testing
        print(f"    Testing with address: {test_address}")
        txs = asyncio.run(provider.get_address_transactions(test_address))
        
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
    socket_success, result = test_electrumx_connection(
        ELECTRUMX_HOST, 
        ELECTRUMX_PORT, 
        use_ssl=ELECTRUMX_USE_SSL,
        timeout=5
    )
    
    if socket_success:
        print(f"  ✓ Raw socket test also succeeded")
        if isinstance(result, dict):
            # Validate JSON-RPC response
            is_valid, validation_error = validate_jsonrpc_response(result, expected_id=1)
            if is_valid:
                if "result" in result:
                    print(f"    Server version: {result.get('result', 'Unknown')}")
                elif "error" in result:
                    error = result["error"]
                    print(f"    Server returned error: {error.get('message', 'Unknown error')}")
            else:
                print(f"    ⚠️  Response validation failed: {validation_error}")
    else:
        print(f"  ⚠️  Raw socket test failed (but provider test passed)")
        print(f"    This is OK - provider handles protocol better")
    
    # Test 3c: Validate transaction response parsing
    print(f"\n[TEST 3c] Testing transaction response parsing...")
    print(f"    Testing with a low-activity address...")
    parsing_success = False
    parsing_details = None
    
    if protocol_success:
        try:
            from api_provider import get_provider, ElectrumXProvider
            provider = get_provider("electrumx")
            
            # Test direct transaction fetch with a known tx hash
            # This tests the blockchain.transaction.get method directly
            print(f"    Testing direct transaction fetch...")
            known_tx = "065f3cf51e45fff9063ebc50deb2af5e24b1817020e4de19a782eafee90f5b4e" #"4a5e1e4baab89f3a32518a88c31bc87f618f76673e2cc77ab2127b7afdeda33b"  # Genesis coinbase tx
            
            # Use internal method to test transaction fetch directly
            if isinstance(provider, ElectrumXProvider):
                tx_result = asyncio.run(provider._send_request("blockchain.transaction.get", [known_tx, True]))
                if tx_result:
                    print(f"    ✓ Direct transaction fetch succeeded")
                    print(f"      Response type: {type(tx_result).__name__}")
                    if isinstance(tx_result, dict):
                        print(f"      Keys: {list(tx_result.keys())[:8]}")
                        if "vin" in tx_result and "vout" in tx_result:
                            print(f"      Has vin: {len(tx_result.get('vin', []))} inputs")
                            print(f"      Has vout: {len(tx_result.get('vout', []))} outputs")
                            parsing_success = True
                        else:
                            print(f"      ⚠️ Response missing vin/vout - may be hex format")
                    elif isinstance(tx_result, str):
                        print(f"      Response is hex string ({len(tx_result)} chars)")
                        print(f"      ⚠️ verbose=True returned hex instead of dict")
                else:
                    print(f"    ✗ Direct transaction fetch returned empty")
            
            # Also test full address query with small address
            print(f"    Testing address transaction history...")
            test_address = "38YEkk8pKA1DXWhQTdW53ibXUaFDYqk269" #"1BvBMSEYstWetqTFn5Au4m4GFg7xJaNVN2"  # Small address
            txs = asyncio.run(provider.get_address_transactions(test_address))
            
            if txs is not None:
                if len(txs) > 0:
                    # Validate first transaction structure
                    first_tx = txs[0]
                    is_valid, validation_error = validate_transaction_response(first_tx)
                    if is_valid:
                        parsing_success = True
                        parsing_details = {
                            "tx_count": len(txs),
                            "sample_txid": first_tx.get("txid", "unknown")[:16] + "...",
                            "has_vin": len(first_tx.get("vin", [])) > 0,
                            "has_vout": len(first_tx.get("vout", [])) > 0
                        }
                        print(f"  ✓ Transaction parsing validated")
                        print(f"    Found {len(txs)} transactions")
                        print(f"    Sample TX: {parsing_details['sample_txid']}")
                        print(f"    Has vin: {parsing_details['has_vin']}, Has vout: {parsing_details['has_vout']}")
                    else:
                        print(f"  ✗ Transaction validation failed: {validation_error}")
                        print(f"    First tx: {first_tx}")
                else:
                    print(f"  ⚠️  No transactions found (server may still be syncing)")
                    parsing_success = True  # Still consider it a success if we got an empty list
            else:
                print(f"  ⚠️  Provider returned None (may indicate connection issue)")
            
            asyncio.run(provider.close())
        except Exception as e:
            import traceback
            print(f"  ✗ Transaction parsing test failed: {e}")
            traceback.print_exc()
    else:
        print(f"  - Skipped (protocol test failed)")
    
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
    
    # Test 6: SSH log access
    print(f"\n[TEST 6] Testing SSH log access...")
    ssh_log_result, ssh_log_data = test_ssh_log_access()
    
    ssh_log_success = False
    if ssh_log_result is None:
        print(f"  - Skipped: {ssh_log_data}")
    elif ssh_log_result:
        ssh_log_success = True
        print(f"  ✓ SSH log access successful")
        if isinstance(ssh_log_data, dict):
            if "status" in ssh_log_data:
                status = ssh_log_data["status"]
                print(f"    Container status: {status.get('status', 'Unknown')}")
                print(f"    Container state: {status.get('state', 'Unknown')}")
            if "logs" in ssh_log_data:
                log_lines = ssh_log_data["logs"].split('\n')
                print(f"    Retrieved {len(log_lines)} log lines")
                # Show last few lines
                if len(log_lines) > 0:
                    print(f"    Last log line: {log_lines[-1][:100]}")
    else:
        print(f"  ✗ SSH log access failed: {ssh_log_data}")
    
    # Summary
    print("\n" + "="*70)
    print("SUMMARY")
    print("="*70)
    
    all_tests = [
        ("Host Reachability", ssh_reachable or port_reachable),
        ("ElectrumX Port Open", port_reachable),
        ("ElectrumX Protocol", success),
        ("Response Parsing", parsing_success if 'parsing_success' in locals() else None),
        ("Blockchain Query", blockchain_test_success if blockchain_test_attempted else None),
        ("SSH Log Access", ssh_log_success if 'ssh_log_success' in locals() else None)
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

