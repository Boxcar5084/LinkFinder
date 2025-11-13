#!/usr/bin/env python3
import os
import shutil
from pathlib import Path

def clear_cache():
    """Delete and clear all cache files"""
    
    # Find and delete blockchain_cache.db
    cache_locations = [
        "blockchain_cache.db",
        "./blockchain_cache.db",
        "checkpoints/blockchain_cache.db",
        "./__pycache__/",
    ]
    
    for location in cache_locations:
        if os.path.exists(location):
            if os.path.isfile(location):
                os.remove(location)
                print(f"✓ Deleted: {location}")
            elif os.path.isdir(location):
                shutil.rmtree(location)
                print(f"✓ Deleted directory: {location}")
    
    print("\n✓ Cache cleared!")
    print("⚠️  Restart the backend to recreate cache:")
    print("   python main.py")

if __name__ == "__main__":
    clear_cache()
