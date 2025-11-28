#!/usr/bin/env python3
"""
ElectrumX Log Access Utility
Fetches ElectrumX Docker logs via SSH for monitoring and debugging
"""
import sys
import os
import subprocess
from typing import Optional, Tuple, List
from config import SSH_HOST, SSH_USER, SSH_KEY_PATH, SSH_PORT, ELECTRUMX_DOCKER_CONTAINER


def fetch_electrumx_logs(host: str, user: str, container: str, key_path: Optional[str] = None, 
                         port: int = 22, lines: int = 50) -> Tuple[bool, Optional[str]]:
    """
    Fetch ElectrumX Docker logs via SSH using subprocess
    
    Args:
        host: SSH server hostname/IP
        user: SSH username
        container: Docker container name
        key_path: Optional path to SSH private key (used with -i flag)
        port: SSH port
        lines: Number of log lines to fetch
    
    Returns:
        Tuple of (success: bool, logs: Optional[str])
    """
    try:
        # Build SSH command: ssh user@host "docker logs --tail N container"
        ssh_cmd = ["ssh"]
        
        # Add SSH key if provided
        if key_path and os.path.exists(key_path):
            ssh_cmd.extend(["-i", key_path])
        
        # Add port if not default
        if port != 22:
            ssh_cmd.extend(["-p", str(port)])
        
        # Add connection timeout
        ssh_cmd.extend(["-o", "ConnectTimeout=10"])
        
        # Add StrictHostKeyChecking=no to avoid prompts (optional, can be configured)
        ssh_cmd.extend(["-o", "StrictHostKeyChecking=no"])
        
        # Build remote command
        remote_cmd = f"docker logs --tail {lines} {container}"
        ssh_target = f"{user}@{host}"
        
        # Execute: ssh user@host "docker logs --tail N container"
        full_cmd = ssh_cmd + [ssh_target, remote_cmd]
        
        result = subprocess.run(
            full_cmd,
            capture_output=True,
            text=True,
            timeout=30
        )
        
        if result.returncode != 0:
            error_msg = result.stderr.strip() if result.stderr else f"SSH command failed with exit code {result.returncode}"
            return False, error_msg
        
        return True, result.stdout
        
    except subprocess.TimeoutExpired:
        return False, "SSH command timed out after 30 seconds"
    except FileNotFoundError:
        return False, "SSH command not found. Make sure SSH is installed and in PATH"
    except Exception as e:
        return False, f"Error fetching logs: {e}"


def check_electrumx_status(host: str, user: str, container: str, key_path: Optional[str] = None, 
                          port: int = 22) -> Tuple[bool, Optional[dict]]:
    """
    Check ElectrumX Docker container status via SSH using subprocess
    
    Args:
        host: SSH server hostname/IP
        user: SSH username
        container: Docker container name
        key_path: Optional path to SSH private key (used with -i flag)
        port: SSH port
    
    Returns:
        Tuple of (success: bool, status: Optional[dict])
    """
    try:
        # Build SSH command: ssh user@host "docker ps -a --filter name=container ..."
        ssh_cmd = ["ssh"]
        
        # Add SSH key if provided
        if key_path and os.path.exists(key_path):
            ssh_cmd.extend(["-i", key_path])
        
        # Add port if not default
        if port != 22:
            ssh_cmd.extend(["-p", str(port)])
        
        # Add connection timeout
        ssh_cmd.extend(["-o", "ConnectTimeout=10"])
        ssh_cmd.extend(["-o", "StrictHostKeyChecking=no"])
        
        # Build remote command
        remote_cmd = f"docker ps -a --filter name={container} --format '{{{{.Names}}}}\\t{{{{.Status}}}}\\t{{{{.State}}}}'"
        ssh_target = f"{user}@{host}"
        
        # Execute SSH command
        full_cmd = ssh_cmd + [ssh_target, remote_cmd]
        
        result = subprocess.run(
            full_cmd,
            capture_output=True,
            text=True,
            timeout=10
        )
        
        if result.returncode != 0:
            error_msg = result.stderr.strip() if result.stderr else f"Command failed with exit code {result.returncode}"
            return False, {"error": error_msg}
        
        output = result.stdout.strip()
        
        if not output:
            return False, {"error": f"Container '{container}' not found"}
        
        # Parse output
        parts = output.split('\t')
        if len(parts) >= 3:
            status_info = {
                "name": parts[0],
                "status": parts[1],
                "state": parts[2]
            }
            return True, status_info
        else:
            return True, {"raw": output}
        
    except subprocess.TimeoutExpired:
        return False, {"error": "SSH command timed out"}
    except FileNotFoundError:
        return False, {"error": "SSH command not found. Make sure SSH is installed and in PATH"}
    except Exception as e:
        return False, {"error": str(e)}


def analyze_logs(logs: str) -> dict:
    """
    Analyze ElectrumX logs for common issues
    
    Args:
        logs: Log output as string
    
    Returns:
        Dictionary with analysis results
    """
    analysis = {
        "errors": [],
        "warnings": [],
        "info": [],
        "connection_issues": False,
        "indexing_status": None,
        "sync_status": None
    }
    
    log_lines = logs.split('\n')
    
    for line in log_lines:
        line_lower = line.lower()
        
        # Check for errors
        if 'error' in line_lower or 'exception' in line_lower or 'failed' in line_lower:
            if 'error' in line_lower:
                analysis["errors"].append(line[:200])  # Truncate long lines
        
        # Check for warnings
        if 'warning' in line_lower or 'warn' in line_lower:
            analysis["warnings"].append(line[:200])
        
        # Check for connection issues
        if any(term in line_lower for term in ['connection refused', 'timeout', 'connection error', 'network error']):
            analysis["connection_issues"] = True
        
        # Check for indexing status
        if 'index' in line_lower:
            if 'indexing' in line_lower or 'indexed' in line_lower:
                analysis["indexing_status"] = line[:200]
        
        # Check for sync status
        if 'sync' in line_lower or 'syncing' in line_lower or 'synced' in line_lower:
            analysis["sync_status"] = line[:200]
    
    return analysis


def main():
    """CLI interface for ElectrumX log access"""
    import argparse
    
    parser = argparse.ArgumentParser(description="Fetch and analyze ElectrumX Docker logs via SSH")
    parser.add_argument("--host", help="SSH host (overrides config)", default=SSH_HOST)
    parser.add_argument("--user", help="SSH username (overrides config)", default=SSH_USER)
    parser.add_argument("--key", help="SSH key path (overrides config)", default=SSH_KEY_PATH)
    parser.add_argument("--port", type=int, help="SSH port (overrides config)", default=SSH_PORT)
    parser.add_argument("--container", help="Docker container name (overrides config)", default=ELECTRUMX_DOCKER_CONTAINER)
    parser.add_argument("--lines", type=int, help="Number of log lines to fetch", default=50)
    parser.add_argument("--status", action="store_true", help="Check container status only")
    parser.add_argument("--analyze", action="store_true", help="Analyze logs for issues")
    
    args = parser.parse_args()
    
    # Validate required parameters
    if not args.host:
        print("[ERROR] SSH host not specified. Set SSH_HOST in config or use --host")
        sys.exit(1)
    
    if not args.user:
        print("[ERROR] SSH user not specified. Set SSH_USER in config or use --user")
        sys.exit(1)
    
    # Check container status if requested
    if args.status:
        print(f"\n[STATUS] Checking ElectrumX container status...")
        print(f"  Host: {args.host}:{args.port}")
        print(f"  User: {args.user}")
        print(f"  Container: {args.container}\n")
        
        success, status = check_electrumx_status(
            args.host, args.user, args.container, args.key, args.port
        )
        
        if success and status:
            print("✓ Container Status:")
            for key, value in status.items():
                print(f"  {key}: {value}")
        else:
            print("✗ Failed to get container status")
            if status and "error" in status:
                print(f"  Error: {status['error']}")
            sys.exit(1)
        
        return
    
    # Fetch logs
    print(f"\n[LOGS] Fetching ElectrumX logs...")
    print(f"  Host: {args.host}:{args.port}")
    print(f"  User: {args.user}")
    print(f"  Container: {args.container}")
    print(f"  Lines: {args.lines}\n")
    
    success, logs = fetch_electrumx_logs(
        args.host, args.user, args.container, args.key, args.port, args.lines
    )
    
    if not success:
        print(f"✗ Failed to fetch logs: {logs}")
        sys.exit(1)
    
    if not logs:
        print("⚠ No logs returned")
        return
    
    # Display logs
    print("=" * 70)
    print("ELECTRUMX LOGS")
    print("=" * 70)
    print(logs)
    print("=" * 70)
    
    # Analyze if requested
    if args.analyze:
        print("\n[ANALYSIS] Analyzing logs for issues...\n")
        analysis = analyze_logs(logs)
        
        if analysis["errors"]:
            print(f"⚠ Found {len(analysis['errors'])} error(s):")
            for error in analysis["errors"][:5]:  # Show first 5
                print(f"  - {error}")
        
        if analysis["warnings"]:
            print(f"\n⚠ Found {len(analysis['warnings'])} warning(s):")
            for warning in analysis["warnings"][:5]:  # Show first 5
                print(f"  - {warning}")
        
        if analysis["connection_issues"]:
            print("\n⚠ Connection issues detected in logs")
        
        if analysis["indexing_status"]:
            print(f"\n[INFO] Indexing status: {analysis['indexing_status']}")
        
        if analysis["sync_status"]:
            print(f"\n[INFO] Sync status: {analysis['sync_status']}")
        
        if not any([analysis["errors"], analysis["warnings"], analysis["connection_issues"]]):
            print("✓ No major issues detected in logs")


if __name__ == "__main__":
    main()

