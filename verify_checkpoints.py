#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
CHECKPOINT VERIFICATION TOOL
Verifies that visited and queued addresses are actually saved in checkpoints
"""

import pickle
from pathlib import Path
from collections import Counter

def verify_checkpoint_addresses():
    """Verify that addresses are saved in checkpoints"""
    
    checkpoint_dir = Path("checkpoints")
    
    if not checkpoint_dir.exists():
        print("âŒ Checkpoints directory doesn't exist!")
        return
    
    checkpoint_files = sorted(
        checkpoint_dir.glob("*.pkl"),
        key=lambda f: f.stat().st_ctime,
        reverse=True
    )
    
    if not checkpoint_files:
        print("âŒ No checkpoint files found!")
        return
    
    print("=" * 80)
    print("CHECKPOINT VERIFICATION TOOL")
    print("=" * 80)
    
    # Verify latest checkpoint
    latest = checkpoint_files[0]
    print(f"\nâœ“ Latest checkpoint: {latest.name}")
    
    with open(latest, 'rb') as f:
        cp_data = pickle.load(f)
    
    state = cp_data.get('state', {})
    trace_state = state.get('trace_state', {})
    
    # Extract addresses
    visited = trace_state.get('visited', [])
    visited_forward = trace_state.get('visited_forward', [])
    visited_backward = trace_state.get('visited_backward', [])
    
    # Convert to list if it's a set
    if isinstance(visited, set):
        visited = list(visited)
    if isinstance(visited_forward, set):
        visited_forward = list(visited_forward)
    if isinstance(visited_backward, set):
        visited_backward = list(visited_backward)
    
    print(f"\nðŸ“Š CHECKPOINT DATA:")
    print(f"  Total visited: {len(visited)}")
    print(f"  Forward visited: {len(visited_forward)}")
    print(f"  Backward visited: {len(visited_backward)}")
    
    # Show sample addresses
    if visited:
        print(f"\n  âœ“ Sample visited addresses:")
        for addr in visited[:5]:
            print(f"    - {addr}")
    else:
        print(f"\n  âŒ NO visited addresses found!")
    
    if visited_forward:
        print(f"\n  âœ“ Sample forward addresses:")
        for addr in visited_forward[:5]:
            print(f"    - {addr}")
    else:
        print(f"\n  âš ï¸  NO forward addresses (might be normal if only backward trace done)")
    
    if visited_backward:
        print(f"\n  âœ“ Sample backward addresses:")
        for addr in visited_backward[:5]:
            print(f"    - {addr}")
    else:
        print(f"\n  âš ï¸  NO backward addresses (might be normal if only forward trace done)")
    
    # Verify address format
    print(f"\nðŸ” ADDRESS FORMAT VERIFICATION:")
    if visited:
        sample_addr = visited[0]
        print(f"  Sample address: {sample_addr}")
        print(f"  Length: {len(sample_addr)}")
        print(f"  Starts with: {sample_addr[:3]}")
        
        # Check if it looks like a Bitcoin address
        if sample_addr[0] in ['1', '3', 'b', 'B'] or sample_addr.startswith('bc1'):
            print(f"  âœ“ Looks like valid Bitcoin address!")
        else:
            print(f"  âš ï¸  Might not be valid Bitcoin address")
    
    # Show file size
    file_size = latest.stat().st_size
    print(f"\nðŸ“¦ FILE SIZE: {file_size:,} bytes")
    if file_size > 1000:
        print(f"  âœ“ Size looks good (contains real data)")
    else:
        print(f"  âŒ File too small (might be mostly empty)")
    
    # Compare multiple checkpoints
    print(f"\nðŸ“ˆ GROWTH OVER TIME:")
    for cp_file in checkpoint_files[:5]:
        with open(cp_file, 'rb') as f:
            data = pickle.load(f)
        
        ts = data.get('state', {}).get('trace_state', {})
        visited_count = len(ts.get('visited', []))
        timestamp = data.get('timestamp', 'N/A')[:16]
        
        print(f"  {timestamp}: {visited_count} addresses")
    
    print("\n" + "=" * 80)
    
    # Final verdict
    if len(visited) > 0:
        print("\nâœ… VERIFICATION PASSED!")
        print(f"   Checkpoint contains {len(visited)} visited addresses")
        if len(visited_forward) > 0 or len(visited_backward) > 0:
            print(f"   Direction tracking: Forward={len(visited_forward)}, Backward={len(visited_backward)}")
    else:
        print("\nâŒ VERIFICATION FAILED!")
        print("   Checkpoint contains 0 addresses - data not being saved!")
        print("   Check that progress_callback is being called in graph_engine.py")

if __name__ == "__main__":
    verify_checkpoint_addresses()