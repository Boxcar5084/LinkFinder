#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
CHECKPOINT DIAGNOSTIC TOOL - Inspect checkpoint file contents
"""

import pickle
import json
from pathlib import Path
from datetime import datetime

def inspect_checkpoints():
    """Inspect all checkpoint files and show their contents"""
    
    checkpoint_dir = Path("checkpoints")
    
    print("=" * 70)
    print("CHECKPOINT DIAGNOSTIC TOOL")
    print("=" * 70)
    
    # Check if directory exists
    if not checkpoint_dir.exists():
        print("ERROR: checkpoints/ directory does not exist!")
        return
    
    # Find all checkpoint files
    checkpoint_files = list(checkpoint_dir.glob("*.pkl"))
    
    if not checkpoint_files:
        print("No checkpoint files found!")
        return
    
    print(f"\nFound {len(checkpoint_files)} checkpoint files\n")
    
    # Sort by creation time (newest first)
    checkpoint_files.sort(key=lambda f: f.stat().st_ctime, reverse=True)
    
    for idx, cp_file in enumerate(checkpoint_files, 1):
        print(f"\n{'=' * 70}")
        print(f"CHECKPOINT #{idx}: {cp_file.name}")
        print(f"{'=' * 70}")
        
        # File info
        stat = cp_file.stat()
        print(f"File size: {stat.st_size} bytes")
        print(f"Created: {datetime.fromtimestamp(stat.st_ctime)}")
        
        # Load and inspect
        try:
            with open(cp_file, 'rb') as f:
                data = pickle.load(f)
            
            # Top level keys
            print(f"\nTop-level keys: {list(data.keys())}")
            
            # Session ID
            session_id = data.get('session_id', 'N/A')
            print(f"Session ID: {session_id[:16]}...")
            
            # Timestamp
            timestamp = data.get('timestamp', 'N/A')
            print(f"Checkpoint timestamp: {timestamp}")
            
            # State
            state = data.get('state', {})
            print(f"\nState keys: {list(state.keys())}")
            
            # Progress
            progress = state.get('progress', {})
            print(f"\nProgress:")
            for key, value in progress.items():
                print(f"  {key}: {value}")
            
            # Trace state
            trace_state = state.get('trace_state', {})
            print(f"\nTrace state keys: {list(trace_state.keys())}")
            
            if trace_state:
                print("Trace state contents:")
                for key in trace_state:
                    value = trace_state[key]
                    if isinstance(value, (set, list)):
                        print(f"  {key}: {len(value)} items")
                        if len(value) > 0:
                            # Show first few items
                            items = list(value)[:3]
                            print(f"    Sample: {items}")
                    elif isinstance(value, dict):
                        print(f"  {key}: dict with {len(value)} keys")
                    else:
                        print(f"  {key}: {value}")
            
            # Request
            request = state.get('request', {})
            if request:
                print(f"\nRequest parameters:")
                print(f"  list_a: {len(request.get('list_a', []))} addresses")
                print(f"  list_b: {len(request.get('list_b', []))} addresses")
                print(f"  max_depth: {request.get('max_depth', 'N/A')}")
            
        except Exception as e:
            print(f"ERROR loading checkpoint: {e}")

if __name__ == "__main__":
    inspect_checkpoints()