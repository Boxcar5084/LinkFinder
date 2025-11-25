#!/usr/bin/env python3
"""
Script to identify and remove duplicate export files.
Files are considered duplicates if they contain the same set of connections.
Keeps the file with the most complete data (most connections, then most addresses examined).
"""

import json
import os
from pathlib import Path
from collections import defaultdict
from typing import Dict, List, Set, Tuple

EXPORTS_DIR = Path(__file__).parent / "exports"


def normalize_connection(conn: dict) -> Tuple[str, str, tuple]:
    """Normalize a connection to a tuple of (source, target, path)."""
    source = conn.get("source", "")
    target = conn.get("target", "")
    path = tuple(conn.get("path", []))
    return (source, target, path)


def get_connection_set(data: dict) -> Set[Tuple[str, str, tuple]]:
    """Extract and normalize all connections from export data."""
    connections = data.get("connections_found", [])
    return {normalize_connection(conn) for conn in connections}


def read_export_file(filepath: Path) -> dict:
    """Read and parse a JSON export file."""
    with open(filepath, 'r') as f:
        return json.load(f)


def get_file_completeness(data: dict) -> Tuple[int, int]:
    """Get completeness metrics: (num_connections, total_addresses_examined)."""
    num_connections = len(data.get("connections_found", []))
    total_addresses = data.get("total_addresses_examined", 0)
    return (num_connections, total_addresses)


def find_duplicate_exports():
    """Find duplicate export files and identify which ones to delete."""
    # Step 1: Scan and parse all export files
    json_files = list(EXPORTS_DIR.glob("*.json"))
    file_data = {}
    
    for json_file in json_files:
        try:
            data = read_export_file(json_file)
            connection_set = get_connection_set(data)
            completeness = get_file_completeness(data)
            file_data[json_file] = {
                "data": data,
                "connection_set": connection_set,
                "completeness": completeness
            }
        except Exception as e:
            print(f"Error reading {json_file.name}: {e}")
            continue
    
    # Step 2: Group files by connection sets
    connection_set_to_files = defaultdict(list)
    for filepath, info in file_data.items():
        # Use frozenset to make the connection set hashable
        connection_key = frozenset(info["connection_set"])
        connection_set_to_files[connection_key].append((filepath, info))
    
    # Step 3: Identify duplicates and select files to keep
    files_to_delete = []
    files_to_keep = []
    
    for connection_key, file_list in connection_set_to_files.items():
        if len(file_list) > 1:
            # Multiple files with same connections - find the best one
            print(f"\nFound {len(file_list)} files with identical connections:")
            for filepath, info in file_list:
                num_conn, num_addr = info["completeness"]
                print(f"  - {filepath.name}: {num_conn} connections, {num_addr} addresses examined")
            
            # Sort by completeness (descending)
            sorted_files = sorted(
                file_list,
                key=lambda x: x[1]["completeness"],
                reverse=True
            )
            
            # Keep the best one
            best_file, best_info = sorted_files[0]
            files_to_keep.append(best_file)
            print(f"  → Keeping: {best_file.name}")
            
            # Mark others for deletion
            for filepath, _ in sorted_files[1:]:
                files_to_delete.append(filepath)
                print(f"  → Deleting: {filepath.name}")
        else:
            # Unique file - keep it
            filepath, _ = file_list[0]
            files_to_keep.append(filepath)
    
    return files_to_delete, files_to_keep


def delete_duplicate_files(files_to_delete: List[Path]):
    """Delete duplicate JSON files and their corresponding CSV files."""
    deleted_count = 0
    
    for json_file in files_to_delete:
        # Delete JSON file
        try:
            json_file.unlink()
            print(f"Deleted: {json_file.name}")
            deleted_count += 1
        except Exception as e:
            print(f"Error deleting {json_file.name}: {e}")
        
        # Delete corresponding CSV file
        csv_file = json_file.with_suffix('.csv')
        if csv_file.exists():
            try:
                csv_file.unlink()
                print(f"Deleted: {csv_file.name}")
            except Exception as e:
                print(f"Error deleting {csv_file.name}: {e}")
    
    return deleted_count


def main():
    """Main execution function."""
    print("Scanning export files for duplicates...")
    print(f"Exports directory: {EXPORTS_DIR}")
    
    files_to_delete, files_to_keep = find_duplicate_exports()
    
    print(f"\n{'='*60}")
    print(f"Summary:")
    print(f"  Files to keep: {len(files_to_keep)}")
    print(f"  Files to delete: {len(files_to_delete)}")
    print(f"{'='*60}")
    
    if files_to_delete:
        print("\nProceeding to delete duplicate files...")
        deleted = delete_duplicate_files(files_to_delete)
        print(f"\nSuccessfully deleted {deleted} duplicate file(s) (and their CSV pairs)")
    else:
        print("\nNo duplicate files found.")


if __name__ == "__main__":
    main()

