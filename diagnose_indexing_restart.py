#!/usr/bin/env python3
"""
Diagnose why electrs indexing restarts even though database is persisted
This checks for indexing state files and startup behavior
"""
import subprocess
import sys
import re
from datetime import datetime

def check_startup_behavior():
    """Check electrs logs for startup behavior"""
    print("="*60)
    print("CHECKING ELECTRS STARTUP BEHAVIOR")
    print("="*60)
    print()
    
    try:
        # Get recent logs
        result = subprocess.run(
            ["docker", "logs", "--tail", "100", "electrs"],
            capture_output=True,
            text=True,
            timeout=10
        )
        
        if result.returncode != 0:
            print(f"✗ Could not get logs: {result.stderr}")
            return
        
        logs = result.stdout
        
        # Look for key indicators
        print("Searching for startup indicators...\n")
        
        # Check for database recovery
        if "Recovered from manifest" in logs or "recovering from manifest" in logs.lower():
            print("✓ Database recovery detected")
            for line in logs.split('\n'):
                if 'manifest' in line.lower() and 'recover' in line.lower():
                    print(f"  {line[:120]}")
        else:
            print("⚠️  No database recovery messages found")
        
        print()
        
        # Check for indexing start/resume
        indexing_started = False
        indexing_resumed = False
        
        for line in logs.split('\n'):
            line_lower = line.lower()
            
            # Look for indexing start messages
            if any(phrase in line_lower for phrase in [
                'starting index', 'initializing index', 'indexing from',
                'indexing block', 'starting to index', 'begin indexing'
            ]):
                if not indexing_started:
                    print("⚠️  INDEXING START DETECTED:")
                    indexing_started = True
                print(f"  {line[:120]}")
            
            # Look for resume messages
            if any(phrase in line_lower for phrase in [
                'resuming', 'continuing', 'found existing', 'using existing index'
            ]):
                if not indexing_resumed:
                    print("✓ INDEXING RESUME DETECTED:")
                    indexing_resumed = True
                print(f"  {line[:120]}")
        
        print()
        
        if indexing_started and not indexing_resumed:
            print("⚠️  PROBLEM: Indexing is starting fresh, not resuming!")
            print("   This means the indexing state is not being persisted.")
        elif indexing_resumed:
            print("✓ Indexing is resuming from existing state")
        else:
            print("? Could not determine indexing behavior from logs")
        
    except Exception as e:
        print(f"✗ Error checking logs: {e}")

def check_database_state():
    """Check database state inside container"""
    print("\n" + "="*60)
    print("CHECKING DATABASE STATE")
    print("="*60)
    print()
    
    try:
        # Check what's in /data
        result = subprocess.run(
            ["docker", "exec", "electrs", "ls", "-la", "/data"],
            capture_output=True,
            text=True,
            timeout=5
        )
        
        if result.returncode == 0:
            print("Contents of /data:")
            print(result.stdout)
        else:
            print(f"✗ Could not list /data: {result.stderr}")
            return
        
        # Check for bitcoin directory
        result2 = subprocess.run(
            ["docker", "exec", "electrs", "test", "-d", "/data/bitcoin"],
            capture_output=True,
            text=True,
            timeout=5
        )
        
        if result2.returncode == 0:
            print("\n✓ /data/bitcoin exists")
            
            # Count files
            result3 = subprocess.run(
                ["docker", "exec", "electrs", "find", "/data/bitcoin", "-type", "f", "|", "wc", "-l"],
                shell=True,
                capture_output=True,
                text=True,
                timeout=5
            )
            
            # Try alternative method
            result3 = subprocess.run(
                ["docker", "exec", "electrs", "sh", "-c", "find /data/bitcoin -type f | wc -l"],
                capture_output=True,
                text=True,
                timeout=5
            )
            
            if result3.returncode == 0:
                file_count = result3.stdout.strip()
                print(f"  Database has {file_count} files")
                
                # Check for MANIFEST file (indicates database state)
                result4 = subprocess.run(
                    ["docker", "exec", "electrs", "ls", "/data/bitcoin/MANIFEST-*"],
                    capture_output=True,
                    text=True,
                    timeout=5
                )
                
                if result4.returncode == 0:
                    print("  ✓ MANIFEST file(s) found (database has state)")
                else:
                    print("  ⚠️  No MANIFEST files found")
        else:
            print("✗ /data/bitcoin does not exist")
    
    except Exception as e:
        print(f"✗ Error: {e}")

def check_environment_variables():
    """Check electrs environment variables"""
    print("\n" + "="*60)
    print("CHECKING ENVIRONMENT VARIABLES")
    print("="*60)
    print()
    
    try:
        result = subprocess.run(
            ["docker", "inspect", "electrs", "--format", "{{range .Config.Env}}{{println .}}{{end}}"],
            capture_output=True,
            text=True,
            timeout=5
        )
        
        if result.returncode == 0:
            env_vars = result.stdout.strip().split('\n')
            print("Environment variables:")
            for var in env_vars:
                if 'DB' in var or 'DATA' in var or 'DIR' in var:
                    print(f"  {var}")
            
            # Check specifically for DB_DIR
            db_dir = None
            for var in env_vars:
                if var.startswith('ELECTRS_DB_DIR='):
                    db_dir = var.split('=', 1)[1]
                    print(f"\n✓ ELECTRS_DB_DIR = {db_dir}")
                    break
            
            if not db_dir:
                print("\n⚠️  ELECTRS_DB_DIR not set (using default)")
        else:
            print(f"✗ Could not get environment: {result.stderr}")
    
    except Exception as e:
        print(f"✗ Error: {e}")

def provide_solutions():
    """Provide solutions based on common issues"""
    print("\n" + "="*60)
    print("POSSIBLE SOLUTIONS")
    print("="*60)
    print()
    
    print("If indexing restarts even though database exists:")
    print()
    print("1. CHECK INDEXING STATE FILE:")
    print("   electrs may store indexing progress separately from the database.")
    print("   Check if there's an indexing state file that needs to be persisted:")
    print("   - Look for files like 'index_state', 'progress', or similar")
    print("   - These might be in /data or /data/bitcoin")
    print()
    print("2. CHECK ELECTRS VERSION:")
    print("   Version upgrades may require reindexing:")
    print("   docker exec electrs electrs --version")
    print()
    print("3. CHECK FOR CORRUPTION:")
    print("   Database might be corrupted, causing electrs to restart:")
    print("   - Check logs for corruption errors")
    print("   - Look for 'corrupt', 'invalid', 'error' messages")
    print()
    print("4. CHECK DATABASE PATH:")
    print("   Ensure ELECTRS_DB_DIR matches where database actually is:")
    print("   - Current: Check environment variables above")
    print("   - Expected: Should match volume mount destination")
    print()
    print("5. CHECK PERMISSIONS:")
    print("   Database files might not be writable:")
    print("   - On Windows: Check C:\\BitcoinCore\\electrs-data permissions")
    print("   - Ensure Docker has write access")
    print()
    print("6. CHECK FOR COMPLETE INDEX:")
    print("   electrs might restart if index is incomplete:")
    print("   - Check if previous indexing completed")
    print("   - Look for 'indexing complete' or similar messages in old logs")
    print()
    print("7. UMBREL IMAGE SPECIFIC:")
    print("   The getumbrel/electrs image might use different paths:")
    print("   - Check Umbrel documentation")
    print("   - May need to set different environment variables")
    print("   - Indexing state might be in a different location")

def main():
    print("\n" + "="*60)
    print("ELECTRS INDEXING RESTART DIAGNOSTIC")
    print("="*60)
    print(f"Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print()
    
    check_startup_behavior()
    check_database_state()
    check_environment_variables()
    provide_solutions()
    
    print("\n" + "="*60)
    print("NEXT STEPS")
    print("="*60)
    print("1. Restart electrs and immediately check logs:")
    print("   docker restart electrs && docker logs -f electrs")
    print()
    print("2. Look for these messages in the first 50 lines:")
    print("   - 'Resuming index' or 'Continuing index' = GOOD")
    print("   - 'Starting index' or 'Initializing index' = BAD (restarting)")
    print()
    print("3. Check if there's an indexing state file:")
    print("   docker exec electrs find /data -name '*index*' -o -name '*state*' -o -name '*progress*'")
    print()
    print("4. Compare database size before and after restart:")
    print("   If size resets to small, indexing is restarting")
    print("="*60)

if __name__ == "__main__":
    main()

