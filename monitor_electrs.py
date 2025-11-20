#!/usr/bin/env python3
"""
Simple script to monitor electrs indexing progress
Run this periodically to check progress: python monitor_electrs.py
"""
import socket
import json
import time
from datetime import datetime

def get_electrs_height():
    """Get current electrs block height"""
    host = "192.168.7.218"
    port = 50001
    
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(5)
        sock.connect((host, port))
        
        request = {
            "jsonrpc": "2.0",
            "method": "blockchain.headers.subscribe",
            "params": [],
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
                return result['result'].get('height', 0)
    except Exception as e:
        print(f"Error: {e}")
        return None
    
    return None

def main():
    expected_height = 924358  # Current Bitcoin blockchain height (approximate)
    
    print(f"\n{'='*60}")
    print(f"ELECTRS INDEXING MONITOR - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"{'='*60}\n")
    
    current_height = get_electrs_height()
    
    if current_height is None:
        print("✗ Could not connect to electrs")
        return
    
    if current_height == 0:
        print("✗ electrs returned height 0 - may be starting up")
        return
    
    progress = (current_height / expected_height) * 100
    remaining = expected_height - current_height
    
    print(f"Current height:  {current_height:,} blocks")
    print(f"Target height:  {expected_height:,} blocks")
    print(f"Progress:       {progress:.2f}%")
    print(f"Remaining:      {remaining:,} blocks")
    
    if progress < 100:
        # Estimate time (rough)
        # Assuming 200 blocks/sec average (middle ground)
        blocks_per_sec = 200
        if remaining > 0:
            hours_remaining = remaining / blocks_per_sec / 3600
            print(f"\n⏱️  Estimated time: ~{hours_remaining:.1f} hours")
        
        print(f"\nStatus: ⚠️  Still indexing...")
        print(f"       Run this script again in a few minutes to check progress")
    else:
        print(f"\nStatus: ✅ Indexing complete!")
        print(f"       electrs is ready to serve queries")

if __name__ == "__main__":
    main()

