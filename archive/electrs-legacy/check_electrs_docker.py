#!/usr/bin/env python3
"""
Helper script to check electrs Docker configuration and provide recommendations
"""
import subprocess
import sys
import socket

def check_docker_container():
    """Check if electrs container is running"""
    print("Checking Docker container status...")
    try:
        result = subprocess.run(
            ["docker", "ps", "--filter", "name=electrs", "--format", "{{.Names}}\t{{.Status}}"],
            capture_output=True,
            text=True,
            timeout=5
        )
        
        if result.returncode == 0 and result.stdout.strip():
            print(f"  ✓ Container found: {result.stdout.strip()}")
            return True
        else:
            print("  ✗ electrs container not found or not running")
            print("    Try: docker ps -a | grep electrs")
            return False
    except FileNotFoundError:
        print("  ✗ Docker not found - is Docker installed?")
        return False
    except subprocess.TimeoutExpired:
        print("  ✗ Docker command timed out")
        return False
    except Exception as e:
        print(f"  ✗ Error checking Docker: {e}")
        return False

def check_port_accessibility(host, port):
    """Check if port is accessible"""
    print(f"\nChecking port accessibility ({host}:{port})...")
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(3)
        result = sock.connect_ex((host, port))
        sock.close()
        
        if result == 0:
            print(f"  ✓ Port {port} is accessible")
            return True
        else:
            print(f"  ✗ Port {port} is not accessible (connection refused)")
            return False
    except socket.timeout:
        print(f"  ✗ Port {port} connection timed out")
        return False
    except Exception as e:
        print(f"  ✗ Error checking port: {e}")
        return False

def check_electrs_logs():
    """Try to get recent electrs logs"""
    print("\nChecking electrs logs (last 20 lines)...")
    try:
        result = subprocess.run(
            ["docker", "logs", "--tail", "20", "electrs"],
            capture_output=True,
            text=True,
            timeout=5
        )
        
        if result.returncode == 0:
            print("  Recent logs:")
            for line in result.stdout.strip().split('\n')[-10:]:  # Last 10 lines
                print(f"    {line}")
            return True
        else:
            print(f"  ✗ Could not retrieve logs: {result.stderr}")
            return False
    except Exception as e:
        print(f"  ✗ Error getting logs: {e}")
        return False

def check_docker_resources():
    """Check Docker resource usage"""
    print("\nChecking Docker resource usage...")
    try:
        result = subprocess.run(
            ["docker", "stats", "electrs", "--no-stream", "--format", "{{.CPUPerc}}\t{{.MemUsage}}"],
            capture_output=True,
            text=True,
            timeout=5
        )
        
        if result.returncode == 0 and result.stdout.strip():
            print(f"  Resource usage: {result.stdout.strip()}")
            return True
        else:
            print("  ✗ Could not get resource stats")
            return False
    except Exception as e:
        print(f"  ✗ Error checking resources: {e}")
        return False

def provide_recommendations():
    """Provide configuration recommendations"""
    print("\n" + "="*60)
    print("RECOMMENDATIONS")
    print("="*60)
    print("\n1. Check electrs.toml configuration:")
    print("   - Ensure electrum_rpc_addr = \"0.0.0.0:50001\"")
    print("   - Increase max_connections (try 100-200)")
    print("   - Verify daemon_rpc_addr points to Bitcoin Core")
    print("\n2. Check Docker configuration:")
    print("   - Ensure port 50001 is exposed")
    print("   - Check resource limits (memory, CPU)")
    print("   - Verify network mode (host or bridge)")
    print("\n3. Check Bitcoin Core:")
    print("   - Ensure Bitcoin Core is running and synced")
    print("   - Verify RPC is accessible from Docker")
    print("\n4. View detailed guide:")
    print("   - See electrs_config_guide.md for full configuration")

def main():
    print("="*60)
    print("ELECTRS DOCKER CONFIGURATION CHECKER")
    print("="*60)
    
    host = "100.94.34.56"
    port = 50001
    
    container_running = check_docker_container()
    port_accessible = check_port_accessibility(host, port)
    
    if container_running:
        check_electrs_logs()
        check_docker_resources()
    
    provide_recommendations()
    
    print("\n" + "="*60)
    if container_running and port_accessible:
        print("✓ Basic checks passed - electrs appears to be running")
    else:
        print("✗ Some checks failed - review recommendations above")
    print("="*60)

if __name__ == "__main__":
    main()

