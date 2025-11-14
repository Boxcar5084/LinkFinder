#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
CHECKPOINT VERIFICATION TOOL - CLEAN FORMAT
Verifies that visited and queued addresses are actually saved in checkpoints
Now includes comprehensive queue analysis and capacity monitoring
"""

import pickle
from pathlib import Path

def verify_checkpoint_addresses():
    """Verify that addresses are saved in checkpoints"""
    
    checkpoint_dir = Path("checkpoints")
    
    if not checkpoint_dir.exists():
        print("[ERROR] Checkpoints directory doesn't exist!")
        return
    
    checkpoint_files = sorted(
        checkpoint_dir.glob("*.pkl"),
        key=lambda f: f.stat().st_ctime,
        reverse=True
    )
    
    if not checkpoint_files:
        print("[ERROR] No checkpoint files found!")
        return
    
    print("=" * 80)
    print("CHECKPOINT VERIFICATION TOOL")
    print("=" * 80)
    
    # Verify latest checkpoint
    latest = checkpoint_files[0]
    print(f"\n[OK] Latest checkpoint: {latest.name}")
    
    with open(latest, 'rb') as f:
        cp_data = pickle.load(f)
    
    state = cp_data.get('state', {})
    trace_state = state.get('trace_state', {})
    
    # Extract addresses
    visited = trace_state.get('visited', [])
    visited_forward = trace_state.get('visited_forward', [])
    visited_backward = trace_state.get('visited_backward', [])
    queued_forward = trace_state.get('queued_forward', [])
    queued_backward = trace_state.get('queued_backward', [])
    
    # Convert to list if it's a set
    if isinstance(visited, set):
        visited = list(visited)
    if isinstance(visited_forward, set):
        visited_forward = list(visited_forward)
    if isinstance(visited_backward, set):
        visited_backward = list(visited_backward)
    if isinstance(queued_forward, set):
        queued_forward = list(queued_forward)
    if isinstance(queued_backward, set):
        queued_backward = list(queued_backward)
    
    # Handle dict format (for visited_forward/backward)
    if isinstance(visited_forward, dict):
        visited_forward = list(visited_forward.keys())
    if isinstance(visited_backward, dict):
        visited_backward = list(visited_backward.keys())
    
    print("\n" + "=" * 80)
    print("CHECKPOINT DATA SUMMARY")
    print("=" * 80)
    print(f"  Total visited:        {len(visited):>8,}")
    print(f"  Forward visited:      {len(visited_forward):>8,}")
    print(f"  Backward visited:     {len(visited_backward):>8,}")
    print(f"  Forward queued:       {len(queued_forward):>8,}")
    print(f"  Backward queued:      {len(queued_backward):>8,}")
    
    # Analyze visited breakdown
    print("\n" + "=" * 80)
    print("VISITED BREAKDOWN")
    print("=" * 80)
    forward_only = len(set(visited_forward) - set(visited_backward))
    backward_only = len(set(visited_backward) - set(visited_forward))
    overlap = len(set(visited_forward) & set(visited_backward))
    
    print(f"  Forward-only:         {forward_only:>8,}")
    print(f"  Backward-only:        {backward_only:>8,}")
    print(f"  Overlap (both):       {overlap:>8,}")
    print(f"  Total unique:         {len(visited):>8,}")
    
    # Queue analysis
    print("\n" + "=" * 80)
    print("QUEUE ANALYSIS")
    print("=" * 80)
    if queued_forward or queued_backward:
        print(f"  [ACTIVE] Queue detected!")
        print(f"  Forward queue size:   {len(queued_forward):>8,} addresses waiting")
        print(f"  Backward queue size:  {len(queued_backward):>8,} addresses waiting")
        print(f"  Total pending:        {len(queued_forward) + len(queued_backward):>8,}")
        print(f"\n  NOTE: Resuming will continue from these queued addresses!")
    else:
        print(f"  [OK] No active queues (queues drain quickly)")
    
    # Show sample addresses
    print("\n" + "=" * 80)
    print("SAMPLE ADDRESSES")
    print("=" * 80)
    
    if visited:
        print(f"\n  Visited addresses ({len(visited)} total):")
        for i, addr in enumerate(visited[:5], 1):
            print(f"    {i}. {addr}")
    else:
        print(f"\n  [ERROR] NO visited addresses found!")
    
    if queued_forward:
        print(f"\n  Forward queued addresses ({len(queued_forward)} total):")
        for i, addr in enumerate(queued_forward[:5], 1):
            print(f"    {i}. {addr}")
    
    if queued_backward:
        print(f"\n  Backward queued addresses ({len(queued_backward)} total):")
        for i, addr in enumerate(queued_backward[:5], 1):
            print(f"    {i}. {addr}")
    
    # Verify address format
    print("\n" + "=" * 80)
    print("ADDRESS FORMAT VERIFICATION")
    print("=" * 80)
    if visited:
        sample_addr = visited[0]
        print(f"  Sample address: {sample_addr}")
        print(f"  Length:         {len(sample_addr)}")
        print(f"  Prefix:         {sample_addr[:3]}")
        
        # Check if it looks like a Bitcoin address
        if sample_addr[0] in ['1', '3', 'b', 'B'] or sample_addr.startswith('bc1'):
            print(f"  [OK] Valid Bitcoin address format!")
        else:
            print(f"  [WARN] Might not be valid Bitcoin address")
    
    # Show file size
    file_size = latest.stat().st_size
    print("\n" + "=" * 80)
    print("FILE METRICS")
    print("=" * 80)
    print(f"  File size: {file_size:,} bytes ({file_size/1024:.2f} KB)")
    if file_size > 1000:
        print(f"  [OK] Size indicates real data")
    else:
        print(f"  [ERROR] File too small (might be mostly empty)")
    
    # Compare multiple checkpoints
    print("\n" + "=" * 80)
    print("CHECKPOINT GROWTH HISTORY (Last 10)")
    print("=" * 80)
    print(f"  {'Timestamp':<22} {'Visited':>12} {'Queued':>12}")
    print("  " + "-" * 50)
    
    for cp_file in checkpoint_files[:10]:
        try:
            with open(cp_file, 'rb') as f:
                data = pickle.load(f)
            
            ts = data.get('state', {}).get('trace_state', {})
            visited_count = len(ts.get('visited', []))
            queued_count = len(ts.get('queued_forward', [])) + len(ts.get('queued_backward', []))
            timestamp = data.get('timestamp', 'N/A')
            
            if isinstance(timestamp, str):
                timestamp = timestamp[:19]
            else:
                timestamp = 'N/A'
            
            print(f"  {timestamp:<22} {visited_count:>12,} {queued_count:>12,}")
        except Exception as e:
            print(f"  Error reading checkpoint: {e}")
    
    print("\n" + "=" * 80)
    print("VERIFICATION RESULT")
    print("=" * 80)
    
    # Final verdict
    if len(visited) > 0:
        print("\n[PASS] VERIFICATION PASSED!")
        print(f"  [OK] Checkpoint contains {len(visited):,} visited addresses")
        if len(visited_forward) > 0 or len(visited_backward) > 0:
            print(f"  [OK] Direction tracking: Forward={len(visited_forward):,}, Backward={len(visited_backward):,}")
        if len(queued_forward) > 0 or len(queued_backward) > 0:
            print(f"  [OK] Queued addresses: Forward={len(queued_forward):,}, Backward={len(queued_backward):,}")
            print(f"  [OK] Ready to resume from queued positions!")
        else:
            print(f"  [OK] Queues clean (efficient processing)")
    else:
        print("\n[FAIL] VERIFICATION FAILED!")
        print("  [ERROR] Checkpoint contains 0 addresses - data not being saved!")
        print("  ACTION: Check that progress_callback is being called in graph_engine.py")
    
    print("\n" + "=" * 80 + "\n")

if __name__ == "__main__":
    verify_checkpoint_addresses()