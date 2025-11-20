#!/usr/bin/env python3
"""
Test script to reproduce the "first query works, subsequent fail" issue
This helps diagnose electrs connection handling problems
"""
import socket
import json
import time

def test_sequential_queries():
    """Test multiple sequential queries to reproduce the issue"""
    host = "100.94.34.56"
    port = 50001
    
    print("\n" + "="*60)
    print("SEQUENTIAL QUERY TEST")
    print("="*60)
    print("Testing if first query works but subsequent queries fail\n")
    
    test_queries = [
        ("blockchain.headers.subscribe", [], "Headers subscribe"),
        ("server.ping", [], "Server ping"),
        ("blockchain.headers.subscribe", [], "Headers subscribe (2nd)"),
        ("server.ping", [], "Server ping (2nd)"),
        ("blockchain.headers.subscribe", [], "Headers subscribe (3rd)"),
    ]
    
    results = []
    
    for i, (method, params, description) in enumerate(test_queries, 1):
        print(f"\nQuery {i}: {description}")
        print("-" * 60)
        
        sock = None
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(10)
            
            connect_start = time.time()
            sock.connect((host, port))
            connect_time = time.time() - connect_start
            print(f"  Connection time: {connect_time:.3f}s")
            
            request = {
                "jsonrpc": "2.0",
                "method": method,
                "params": params,
                "id": i
            }
            
            send_start = time.time()
            sock.sendall((json.dumps(request) + '\n').encode('utf-8'))
            send_time = time.time() - send_start
            print(f"  Send time: {send_time:.3f}s")
            
            # Read response
            response_data = b""
            buffer = b""
            recv_start = time.time()
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
            
            recv_time = time.time() - recv_start
            
            if sock:
                sock.close()
            
            if response_data:
                try:
                    result = json.loads(response_data.decode('utf-8'))
                    if 'result' in result:
                        print(f"  ✓ SUCCESS (response time: {recv_time:.3f}s)")
                        results.append(True)
                    elif 'error' in result:
                        print(f"  ✗ ERROR: {result['error']}")
                        results.append(False)
                    else:
                        print(f"  ✗ UNEXPECTED: {result}")
                        results.append(False)
                except json.JSONDecodeError as e:
                    print(f"  ✗ JSON PARSE ERROR: {e}")
                    print(f"    Response: {response_data[:200]}")
                    results.append(False)
            else:
                print(f"  ✗ TIMEOUT (no response after {recv_time:.3f}s)")
                results.append(False)
            
            # Small delay between queries
            time.sleep(0.5)
            
        except socket.timeout:
            if sock:
                sock.close()
            print(f"  ✗ CONNECTION TIMEOUT")
            results.append(False)
        except ConnectionRefusedError:
            if sock:
                sock.close()
            print(f"  ✗ CONNECTION REFUSED")
            results.append(False)
        except Exception as e:
            if sock:
                sock.close()
            print(f"  ✗ ERROR: {e}")
            results.append(False)
    
    # Summary
    print("\n" + "="*60)
    print("SUMMARY")
    print("="*60)
    print(f"Total queries: {len(test_queries)}")
    print(f"Successful: {sum(results)}")
    print(f"Failed: {len(results) - sum(results)}")
    
    if results[0] and not all(results[1:]):
        print("\n⚠️  PATTERN DETECTED: First query works, subsequent fail!")
        print("   This indicates electrs connection handling issues.")
        print("   Solutions:")
        print("   1. Use connection pooling/reuse")
        print("   2. Check electrs max_connections setting")
        print("   3. Verify Docker resource limits")
        print("   4. Check electrs logs for connection errors")
    elif all(results):
        print("\n✓ All queries succeeded - connection handling is working")
    else:
        print("\n✗ Some queries failed - check electrs status")

if __name__ == "__main__":
    test_sequential_queries()

