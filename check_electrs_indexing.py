#!/usr/bin/env python3
"""
Check electrs indexing status and provide information about sync progress
"""
import socket
import json
import time

def check_electrs_indexing_status():
    """Check if electrs has finished indexing"""
    host = "192.168.7.218"
    port = 50001
    
    print("\n" + "="*60)
    print("ELECTRS INDEXING STATUS CHECK")
    print("="*60)
    
    # Test 1: Check server version (should work even if indexing)
    print("\nTEST 1: Server Version")
    print("-" * 60)
    
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(5)
        sock.connect((host, port))
        
        request = {
            "jsonrpc": "2.0",
            "method": "server.version",
            "params": ["LinkFinder", "1.4"],
            "id": 1
        }
        
        sock.sendall((json.dumps(request) + '\n').encode('utf-8'))
        
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
            result = json.loads(response_data.decode('utf-8'))
            if 'result' in result:
                print(f"  ✓ Server version: {result['result']}")
            else:
                print(f"  Response: {result}")
    except Exception as e:
        print(f"  ✗ Error: {e}")
    
    # Test 2: Check current block height
    print("\nTEST 2: Current Block Height")
    print("-" * 60)
    
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(5)
        sock.connect((host, port))
        
        request = {
            "jsonrpc": "2.0",
            "method": "blockchain.headers.subscribe",
            "params": [],
            "id": 2
        }
        
        sock.sendall((json.dumps(request) + '\n').encode('utf-8'))
        
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
            result = json.loads(response_data.decode('utf-8'))
            if 'result' in result:
                height = result['result'].get('height', 0)
                print(f"  ✓ Current block height: {height:,}")
                return height
            else:
                print(f"  Response: {result}")
    except Exception as e:
        print(f"  ✗ Error: {e}")
    
    return None

def main():
    """Main function to check indexing status"""
    host = "192.168.7.218"
    port = 50001
    
    print("\n" + "="*60)
    print("ELECTRS INDEXING STATUS CHECK")
    print("="*60)
    
    # Test 1: Check server version (should work even if indexing)
    print("\nTEST 1: Server Version")
    print("-" * 60)
    
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(5)
        sock.connect((host, port))
        
        request = {
            "jsonrpc": "2.0",
            "method": "server.version",
            "params": ["LinkFinder", "1.4"],
            "id": 1
        }
        
        sock.sendall((json.dumps(request) + '\n').encode('utf-8'))
        
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
            result = json.loads(response_data.decode('utf-8'))
            if 'result' in result:
                print(f"  ✓ Server version: {result['result']}")
            else:
                print(f"  Response: {result}")
    except Exception as e:
        print(f"  ✗ Error: {e}")
    
    # Test 2: Check current block height
    print("\nTEST 2: Current Block Height")
    print("-" * 60)
    
    current_height = None
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(5)
        sock.connect((host, port))
        
        request = {
            "jsonrpc": "2.0",
            "method": "blockchain.headers.subscribe",
            "params": [],
            "id": 2
        }
        
        sock.sendall((json.dumps(request) + '\n').encode('utf-8'))
        
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
            result = json.loads(response_data.decode('utf-8'))
            if 'result' in result:
                current_height = result['result'].get('height', 0)
                print(f"  ✓ Current block height: {current_height:,}")
            else:
                print(f"  Response: {result}")
    except Exception as e:
        print(f"  ✗ Error: {e}")
    
    # Get current blockchain height for comparison
    
    # Expected current Bitcoin height (approximate)
    expected_height = 924358  # From earlier diagnostic
    
    print("\n" + "="*60)
    print("INDEXING STATUS")
    print("="*60)
    
    if current_height:
        progress = (current_height / expected_height) * 100
        remaining = expected_height - current_height
        
        print(f"\nCurrent electrs height: {current_height:,}")
        print(f"Expected height: {expected_height:,}")
        print(f"Progress: {progress:.1f}%")
        print(f"Remaining blocks: {remaining:,}")
        
        if progress < 100:
            print(f"\n⚠️  electrs is still indexing!")
            print(f"   {progress:.1f}% complete - {remaining:,} blocks remaining")
            
            # Estimate time remaining (rough estimate)
            # Typical indexing: 100-500 blocks/second depending on hardware
            blocks_per_sec_low = 100
            blocks_per_sec_high = 500
            
            time_low = remaining / blocks_per_sec_low / 3600  # hours
            time_high = remaining / blocks_per_sec_high / 3600  # hours
            
            print(f"\nEstimated time remaining:")
            print(f"  Fast (500 blocks/sec): ~{time_high:.1f} hours")
            print(f"  Slow (100 blocks/sec): ~{time_low:.1f} hours")
        else:
            print("\n✓ electrs appears to be fully synced!")
    
    print("\n" + "="*60)
    print("INTERPRETATION")
    print("="*60)
    print("\n'Unavailable index' error means:")
    print("  - electrs is still building its index")
    print("  - It can only serve queries for blocks it has indexed")
    print("  - Address queries require full index to be available")
    print("\nTo check indexing progress:")
    print("  1. Check electrs logs: docker logs electrs -f")
    print("  2. Look for indexing progress messages")
    print("  3. Run this script periodically to check height")
    print("\nTypical indexing speeds:")
    print("  - Fast NVMe SSD: 300-500 blocks/sec")
    print("  - Regular SSD: 150-300 blocks/sec")
    print("  - HDD: 50-150 blocks/sec")
    print("\nSOLUTIONS:")
    print("  1. Wait for indexing to complete (recommended)")
    print("  2. Use alternative APIs temporarily:")
    print("     - Mempool.space API")
    print("     - Blockchain.info API")
    print("  3. Check electrs configuration for performance tuning")
    print("\nYou can switch to another API provider in config.py:")
    print("  DEFAULT_API = 'mempool'  # or 'blockchain'")

if __name__ == "__main__":
    main()

