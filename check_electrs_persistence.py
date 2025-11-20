#!/usr/bin/env python3
"""
Check if electrs database is properly persisted
Run this on the Windows host where electrs is running
"""
import subprocess
import sys
import os

def check_docker_volume_mounts():
    """Check if electrs has volume mounts configured"""
    print("Checking Docker volume mounts...")
    try:
        result = subprocess.run(
            ["docker", "inspect", "electrs", "--format", "{{json .Mounts}}"],
            capture_output=True,
            text=True,
            timeout=5
        )
        
        if result.returncode == 0:
            import json
            mounts = json.loads(result.stdout)
            print(f"  Found {len(mounts)} volume mount(s):")
            for mount in mounts:
                print(f"    Source: {mount.get('Source', 'N/A')}")
                print(f"    Destination: {mount.get('Destination', 'N/A')}")
                print(f"    Type: {mount.get('Type', 'N/A')}")
                print()
            return mounts
        else:
            print(f"  ✗ Could not inspect container: {result.stderr}")
            return None
    except Exception as e:
        print(f"  ✗ Error: {e}")
        return None

def check_database_directory():
    """Check if database directory exists and has files"""
    print("Checking database directory inside container...")
    try:
        # Check if /data/bitcoin exists
        result = subprocess.run(
            ["docker", "exec", "electrs", "ls", "-la", "/data"],
            capture_output=True,
            text=True,
            timeout=5
        )
        
        if result.returncode == 0:
            print("  Contents of /data:")
            print(result.stdout)
            
            # Check specifically for bitcoin directory
            result2 = subprocess.run(
                ["docker", "exec", "electrs", "test", "-d", "/data/bitcoin"],
                capture_output=True,
                text=True,
                timeout=5
            )
            
            if result2.returncode == 0:
                print("  ✓ /data/bitcoin directory exists")
                
                # Check for database files
                result3 = subprocess.run(
                    ["docker", "exec", "electrs", "ls", "-lh", "/data/bitcoin"],
                    capture_output=True,
                    text=True,
                    timeout=5
                )
                
                if result3.returncode == 0:
                    files = result3.stdout.strip().split('\n')
                    if len(files) > 1:  # More than just the header
                        print(f"  ✓ Database directory has {len(files)-1} items")
                        print("  Recent files:")
                        for line in files[-5:]:
                            print(f"    {line}")
                        return True
                    else:
                        print("  ⚠️  Database directory is empty")
                        return False
            else:
                print("  ✗ /data/bitcoin directory does not exist")
                return False
        else:
            print(f"  ✗ Could not list /data: {result.stderr}")
            return False
    except Exception as e:
        print(f"  ✗ Error: {e}")
        return False

def check_host_directory():
    """Check if host directory exists (Windows path)"""
    print("\nChecking host directory (Windows)...")
    print("  Note: This check requires access to the Windows host")
    print("  Expected path: C:\\BitcoinCore\\electrs-data\\bitcoin")
    print("  Please verify this directory exists and has files")

def check_electrs_logs_for_indexing():
    """Check electrs logs for indexing messages"""
    print("\nChecking electrs logs for indexing status...")
    try:
        result = subprocess.run(
            ["docker", "logs", "--tail", "50", "electrs"],
            capture_output=True,
            text=True,
            timeout=5
        )
        
        if result.returncode == 0:
            logs = result.stdout.lower()
            
            # Look for indexing indicators
            if "indexing" in logs or "index" in logs:
                print("  Found indexing-related messages in logs")
                # Show relevant lines
                for line in result.stdout.split('\n'):
                    if 'index' in line.lower() or 'sync' in line.lower():
                        print(f"    {line[:100]}")
            
            if "starting" in logs or "initializing" in logs:
                print("  ⚠️  Found startup messages - may indicate fresh start")
            
            if "resuming" in logs or "continuing" in logs:
                print("  ✓ Found resume messages - database is being used")
            
            return True
        else:
            print(f"  ✗ Could not get logs: {result.stderr}")
            return False
    except Exception as e:
        print(f"  ✗ Error: {e}")
        return False

def provide_recommendations(mounts, db_exists):
    """Provide recommendations based on findings"""
    print("\n" + "="*60)
    print("RECOMMENDATIONS")
    print("="*60)
    
    if not mounts:
        print("\n✗ No volume mounts found!")
        print("  Your docker-compose.yml shows a volume mount, but Docker")
        print("  doesn't see it. Try:")
        print("  1. Restart the container: docker-compose down && docker-compose up -d")
        print("  2. Check docker-compose.yml syntax")
        return
    
    if not db_exists:
        print("\n⚠️  Database directory exists but is empty")
        print("  This means:")
        print("  - Volume mount is working")
        print("  - But database hasn't been created yet or was cleared")
        print("  - electrs will start indexing from scratch")
        print("\n  Solutions:")
        print("  1. Let electrs finish indexing (it will create the database)")
        print("  2. Check if database files are in a different location")
        print("  3. Verify ELECTRS_DB_DIR environment variable")
        return
    
    print("\n✓ Volume mount is configured correctly")
    print("✓ Database directory exists and has files")
    print("\nIf indexing still restarts, possible causes:")
    print("  1. Database corruption - check electrs logs for errors")
    print("  2. Wrong database path - verify ELECTRS_DB_DIR matches volume mount")
    print("  3. Permission issues - check file permissions in C:\\BitcoinCore\\electrs-data")
    print("  4. Database format change - electrs version upgrade may require reindex")

def main():
    print("="*60)
    print("ELECTRS PERSISTENCE CHECKER")
    print("="*60)
    print("\nThis script checks if electrs database is properly persisted")
    print("Run this on the Windows host where electrs Docker is running\n")
    
    mounts = check_docker_volume_mounts()
    db_exists = check_database_directory()
    check_host_directory()
    check_electrs_logs_for_indexing()
    
    provide_recommendations(mounts, db_exists)
    
    print("\n" + "="*60)
    print("Next Steps:")
    print("  1. Verify C:\\BitcoinCore\\electrs-data\\bitcoin exists on Windows")
    print("  2. Check file sizes - database should be several GB if indexed")
    print("  3. Monitor electrs logs: docker logs -f electrs")
    print("  4. Check if indexing resumes or starts fresh after restart")
    print("="*60)

if __name__ == "__main__":
    main()

