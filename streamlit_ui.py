# -*- coding: utf-8 -*-
import streamlit as st
import requests
import pandas as pd
import pickle
from pathlib import Path
from datetime import datetime
import time
import socket
import json

# Check for dialog support (Streamlit 1.34+)
if hasattr(st, "dialog"):
    dialog_decorator = st.dialog
elif hasattr(st, "experimental_dialog"):
    dialog_decorator = st.experimental_dialog
else:
    dialog_decorator = None

# Define dialog function if supported
if dialog_decorator:
    @dialog_decorator("Full Address List")
    def view_full_list_dialog(title, addresses):
        st.info(f"📋 **{title} - All {len(addresses)} Addresses**")
        addresses_text = '\n'.join(addresses)
        st.text_area(
            f"All addresses from {title}",
            value=addresses_text,
            height=300,
            help="Select all (Ctrl+A / Cmd+A) and copy (Ctrl+C / Cmd+C) to copy all addresses"
        )

# Configuration
API_URL = "http://localhost:8000"
API_TIMEOUT = 600

# Page config
st.set_page_config(
    page_title="LinkFinder - Bitcoin Address Linker",
    page_icon="ðŸ”—",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Initialize session state
if 'auto_refresh_enabled' not in st.session_state:
    st.session_state.auto_refresh_enabled = False
if 'completed_sessions' not in st.session_state:
    st.session_state.completed_sessions = {}
if 'show_connectivity_warning' not in st.session_state:
    st.session_state.show_connectivity_warning = False
if 'pending_electrumx_settings' not in st.session_state:
    st.session_state.pending_electrumx_settings = None
if 'test_connection_result' not in st.session_state:
    st.session_state.test_connection_result = None
if 'settings_save_success' not in st.session_state:
    st.session_state.settings_save_success = False
if 'show_full_address_list' not in st.session_state:
    st.session_state.show_full_address_list = None  # Format: {'type': 'list_a' or 'list_b', 'checkpoint_id': str, 'addresses': list}

# Custom CSS
st.markdown("""
<style>
    .stTabs [data-baseweb="tab-list"] button {
        font-size: 16px;
    }
    .checkpoint-stat {
        padding: 1rem;
        background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
        border-radius: 0.5rem;
        color: white;
        text-align: center;
    }
</style>
""", unsafe_allow_html=True)

# Helper functions
def get_sessions():
    """Fetch all active sessions"""
    try:
        response = requests.get(f"{API_URL}/sessions", timeout=API_TIMEOUT)
        if response.status_code == 200:
            return response.json().get('sessions', [])
    except requests.exceptions.Timeout:
        st.warning(f"Server timeout (>{API_TIMEOUT}s).")
        return []
    except Exception as e:
        st.error(f"Error: {e}")
    return []

def get_checkpoints():
    """Fetch all available checkpoints"""
    try:
        response = requests.get(f"{API_URL}/checkpoints/all", timeout=API_TIMEOUT)
        if response.status_code == 200:
            return response.json().get('checkpoints', [])
    except requests.exceptions.Timeout:
        st.warning(f"Server timeout (>{API_TIMEOUT}s).")
        return []
    except Exception as e:
        st.error(f"Error: {e}")
    return []

def get_session_details(session_id):
    """Fetch detailed status for a session"""
    try:
        response = requests.get(f"{API_URL}/status/{session_id}", timeout=API_TIMEOUT)
        if response.status_code == 200:
            return response.json()
    except requests.exceptions.Timeout:
        st.warning(f"Timeout fetching details.")
        return None
    except Exception as e:
        st.error(f"Error: {e}")
    return None

def start_new_trace(list_a, list_b, max_depth, start_block, end_block):
    """Start a new trace session"""
    try:
        payload = {
            "list_a": list_a,
            "list_b": list_b,
            "max_depth": max_depth,
            "start_block": start_block,
            "end_block": end_block
        }
        response = requests.post(f"{API_URL}/trace", json=payload, timeout=API_TIMEOUT)
        if response.status_code == 200:
            return response.json()
        else:
            st.error(f"Failed: {response.text}")
    except Exception as e:
        st.error(f"Error: {e}")
    return None

def cancel_session(session_id):
    """Cancel a running session"""
    try:
        response = requests.post(f"{API_URL}/cancel/{session_id}", timeout=API_TIMEOUT)
        if response.status_code == 200:
            st.success(f"Cancellation requested!")
            return True
    except Exception as e:
        st.error(f"Error: {e}")
    return False

def resume_auto():
    """Auto-resume from most recent checkpoint"""
    try:
        response = requests.post(f"{API_URL}/resume/auto", timeout=API_TIMEOUT)
        if response.status_code == 200:
            result = response.json()
            st.success(f"Resumed! New session: {result['session_id'][:8]}...")
            return result
        else:
            st.error("No checkpoints available")
    except Exception as e:
        st.error(f"Error: {e}")
    return None

def delete_session(session_id):
    """Delete a session"""
    try:
        response = requests.delete(f"{API_URL}/sessions/{session_id}", timeout=API_TIMEOUT)
        if response.status_code == 200:
            st.success("Deleted")
            return True
    except Exception as e:
        st.error(f"Error: {e}")
    return False

def delete_checkpoint(session_id, checkpoint_id):
    """Delete a checkpoint"""
    try:
        response = requests.delete(f"{API_URL}/checkpoints/{session_id}/{checkpoint_id}", timeout=API_TIMEOUT)
        if response.status_code == 200:
            st.success("Checkpoint deleted")
            return True
        else:
            st.error(f"Failed to delete checkpoint: {response.text}")
    except Exception as e:
        st.error(f"Error: {e}")
    return False

def get_checkpoint_details(session_id, checkpoint_id):
    """Get detailed checkpoint information"""
    try:
        response = requests.get(f"{API_URL}/checkpoint/{session_id}/{checkpoint_id}", timeout=API_TIMEOUT)
        if response.status_code == 200:
            return response.json()
        else:
            st.error(f"Failed to get checkpoint details: {response.text}")
    except Exception as e:
        st.error(f"Error: {e}")
    return None

def resume_from_checkpoint(session_id, checkpoint_id):
    """Resume from a specific checkpoint"""
    try:
        response = requests.post(f"{API_URL}/resume/{session_id}/{checkpoint_id}", timeout=API_TIMEOUT)
        if response.status_code == 200:
            result = response.json()
            st.success(f"Resumed! New session: {result['session_id'][:8]}...")
            return result
        else:
            st.error(f"Failed to resume: {response.text}")
    except Exception as e:
        st.error(f"Error: {e}")
    return None

def get_status_badge(status):
    """Return status badge"""
    badges = {
        'running': '[RUNNING]',
        'completed': '[COMPLETED]',
        'cancelled': '[CANCELLED]',
        'failed': '[FAILED]'
    }
    return badges.get(status, '[UNKNOWN]')

def load_checkpoint_data(session_id, checkpoint_id):
    """Load checkpoint file and return data"""
    try:
        checkpoint_file = Path("checkpoints") / f"{session_id}_{checkpoint_id}.pkl"
        if checkpoint_file.exists():
            with open(checkpoint_file, 'rb') as f:
                return pickle.load(f)
    except Exception as e:
        st.error(f"Error loading checkpoint: {e}")
    return None

def get_settings():
    """Fetch current settings from API"""
    try:
        response = requests.get(f"{API_URL}/settings", timeout=API_TIMEOUT)
        if response.status_code == 200:
            return response.json()
    except requests.exceptions.Timeout:
        st.warning(f"Server timeout (>{API_TIMEOUT}s).")
        return None
    except Exception as e:
        st.error(f"Error fetching settings: {e}")
    return None

def test_electrumx_connectivity(host, port, use_ssl=False, cert=None, timeout=5):
    """
    Test ElectrumX server connectivity
    
    Args:
        host: Server hostname or IP
        port: Server port
        use_ssl: Whether to use SSL connection
        cert: Optional SSL certificate path
        timeout: Connection timeout in seconds
    
    Returns:
        Tuple of (success: bool, error_message: str)
    """
    if not host or not port:
        return False, "Host and port must be provided"
    
    try:
        # Test basic port reachability first
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(timeout)
        result = sock.connect_ex((host, port))
        sock.close()
        
        if result != 0:
            return False, f"Cannot reach {host}:{port} - connection refused or port closed"
        
        # If SSL is enabled, test SSL connection
        if use_ssl:
            try:
                import ssl
                context = ssl.create_default_context()
                if cert:
                    context.load_verify_locations(cert)
                else:
                    context.check_hostname = False
                    context.verify_mode = ssl.CERT_NONE
                
                sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                sock.settimeout(timeout)
                sock.connect((host, port))
                sock = context.wrap_socket(sock, server_hostname=host)
                
                # Try a simple Electrum protocol request
                request = {
                    "jsonrpc": "2.0",
                    "method": "server.version",
                    "params": ["LinkFinder-Test", "1.4"],
                    "id": 1
                }
                request_str = json.dumps(request) + "\n"
                sock.sendall(request_str.encode())
                
                # Read response with timeout
                sock.settimeout(2)
                response_data = sock.recv(4096)
                
                try:
                    if hasattr(sock, 'shutdown'):
                        sock.shutdown(socket.SHUT_RDWR)
                except:
                    pass
                sock.close()
                
                if response_data:
                    try:
                        response_json = json.loads(response_data.decode().strip())
                        if "result" in response_json or "error" in response_json:
                            return True, "Server is reachable and responding"
                    except json.JSONDecodeError:
                        return True, "Server is reachable (protocol response unclear)"
                else:
                    return False, "Server is reachable but not responding to protocol requests"
                    
            except ssl.SSLError as e:
                return False, f"SSL connection error: {str(e)}"
            except socket.timeout:
                return False, f"SSL connection timeout to {host}:{port}"
            except Exception as e:
                return False, f"SSL connection error: {str(e)}"
        else:
            # Test TCP connection with protocol request
            try:
                sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                sock.settimeout(timeout)
                sock.connect((host, port))
                
                # Try a simple Electrum protocol request
                request = {
                    "jsonrpc": "2.0",
                    "method": "server.version",
                    "params": ["LinkFinder-Test", "1.4"],
                    "id": 1
                }
                request_str = json.dumps(request) + "\n"
                sock.sendall(request_str.encode())
                
                # Read response with timeout
                sock.settimeout(2)
                response_data = sock.recv(4096)
                
                try:
                    if hasattr(sock, 'shutdown'):
                        sock.shutdown(socket.SHUT_RDWR)
                except:
                    pass
                sock.close()
                
                if response_data:
                    try:
                        response_json = json.loads(response_data.decode().strip())
                        if "result" in response_json or "error" in response_json:
                            return True, "Server is reachable and responding"
                    except json.JSONDecodeError:
                        return True, "Server is reachable (protocol response unclear)"
                else:
                    return False, "Server is reachable but not responding to protocol requests"
                    
            except socket.timeout:
                return False, f"Connection timeout to {host}:{port}"
            except Exception as e:
                return False, f"Protocol test error: {str(e)}"
        
        return True, "Server is reachable"
        
    except socket.gaierror as e:
        return False, f"DNS/Hostname resolution error: {str(e)}"
    except socket.timeout:
        return False, f"Connection timeout to {host}:{port}"
    except Exception as e:
        return False, f"Connection error: {str(e)}"

def save_settings(default_api=None, mempool_api_key=None, electrumx_host=None, electrumx_port=None, electrumx_use_ssl=None, electrumx_cert=None):
    """Save settings to API"""
    try:
        payload = {}
        if default_api is not None:
            payload['default_api'] = default_api
        if mempool_api_key is not None:
            payload['mempool_api_key'] = mempool_api_key
        if electrumx_host is not None:
            payload['electrumx_host'] = electrumx_host
        if electrumx_port is not None:
            payload['electrumx_port'] = electrumx_port
        if electrumx_use_ssl is not None:
            payload['electrumx_use_ssl'] = electrumx_use_ssl
        if electrumx_cert is not None:
            payload['electrumx_cert'] = electrumx_cert
        
        response = requests.post(f"{API_URL}/settings", json=payload, timeout=API_TIMEOUT)
        if response.status_code == 200:
            return response.json()
        else:
            st.error(f"Failed to save settings: {response.text}")
    except Exception as e:
        st.error(f"Error saving settings: {e}")
    return None

# Header
st.title("Bitcoin Address Linker")
st.markdown("Manage sessions, trace addresses, and control checkpoints")

# Sidebar - Controls
with st.sidebar:
    st.header("Controls")
    
    st.session_state.auto_refresh_enabled = st.checkbox(
        "Enable Auto-Refresh",
        value=st.session_state.auto_refresh_enabled,
        help="Auto-refresh every 20 seconds"
    )
    
    if st.button("Refresh Now", width='stretch'):
        st.rerun()
    
    st.divider()
    st.info(f"API Timeout: {API_TIMEOUT}s\nRefresh: Every 60s (if enabled)")
    
    with st.expander("Debug Info"):
        st.write(f"API URL: {API_URL}")
        
        if st.button("Test API", width='stretch'):
            try:
                response = requests.get(f"{API_URL}/sessions", timeout=5)
                if response.status_code == 200:
                    st.success("API OK")
                else:
                    st.error(f"Status {response.status_code}")
            except Exception as e:
                st.error(f"Error: {e}")

# Main tabs
tab1, tab2, tab3, tab4 = st.tabs(["Active Sessions", "New Trace", "Checkpoints", "Settings"])

# ========== TAB 1: ACTIVE SESSIONS ==========
with tab1:
    st.header("Active Sessions")
    
    sessions = get_sessions()
    
    if not sessions:
        st.info("No sessions")
    else:
        # Metrics
        col1, col2, col3, col4 = st.columns(4)
        
        running = len([s for s in sessions if s['status'] == 'running'])
        completed = len([s for s in sessions if s['status'] == 'completed'])
        cancelled = len([s for s in sessions if s['status'] == 'cancelled'])
        failed = len([s for s in sessions if s['status'] == 'failed'])
        
        with col1:
            st.metric("Running", running)
        with col2:
            st.metric("Completed", completed)
        with col3:
            st.metric("Cancelled", cancelled)
        with col4:
            st.metric("Failed", failed)
        
        st.divider()
        
        # NEW: Latest Checkpoint Progress
        st.subheader("Latest Checkpoint Progress")
        
        checkpoints = get_checkpoints()
        if checkpoints:
            latest = checkpoints[0]
            cp_data = load_checkpoint_data(latest['session_id'], latest['checkpoint_id'])
            
            if cp_data:
                state = cp_data.get('state', {})
                progress = state.get('progress', {})
                trace_state = state.get('trace_state', {})
                
                # Display progress in 4 columns
                col1, col2, col3, col4 = st.columns(4)
                
                with col1:
                    st.metric(
                        "Addresses Examined",
                        progress.get('addresses_examined', 0)
                    )
                
                with col2:
                    st.metric(
                        "Forward Trace",
                        progress.get('visited_forward', 0)
                    )
                
                with col3:
                    st.metric(
                        "Backward Trace",
                        progress.get('visited_backward', 0)
                    )
                
                with col4:
                    st.metric(
                        "Connections",
                        len(trace_state.get('connections_found', []))
                    )
                
                # Timestamp info
                timestamp = cp_data.get('timestamp', 'N/A')
                session_id = latest['session_id'][:8]
                st.caption(f"Latest checkpoint: {timestamp} | Session: {session_id}...")
        else:
            st.info("No checkpoints yet. Start a trace to see progress.")
        
        st.divider()
        
        # Sessions list
        for session in sessions:
            session_id = session['session_id']
            status = session['status']
            status_badge = get_status_badge(status)
            
            if status == 'completed' and session_id in st.session_state.completed_sessions:
                details = st.session_state.completed_sessions[session_id]
            else:
                details = get_session_details(session_id)
                if status == 'completed':
                    st.session_state.completed_sessions[session_id] = details
            
            with st.expander(
                f"{status_badge} {session_id[:12]}...",
                expanded=(status == 'running')
            ):
                if details:
                    col1, col2, col3 = st.columns(3)
                    
                    with col1:
                        st.write(f"**Session ID**")
                        st.code(session_id[:20] + "...")
                    
                    with col2:
                        st.write(f"**Status**")
                        st.write(status_badge)
                    
                    with col3:
                        st.write(f"**Started**")
                        start_time = session.get('started_at', 'N/A')
                        if start_time != 'N/A':
                            start_dt = datetime.fromisoformat(start_time)
                            elapsed = datetime.now() - start_dt.replace(tzinfo=None)
                            st.write(f"{elapsed.seconds}s ago")
                    
                    st.divider()
                    
                    request_info = details.get('request', {})
                    if request_info:
                        st.write("**Input Parameters**")
                        
                        col1, col2 = st.columns(2)
                        
                        with col1:
                            st.write(f"**List A ({len(request_info.get('list_a', []))} addresses)**")
                            list_a = request_info.get('list_a', [])
                            for addr in list_a:
                                st.code(addr)
                        
                        with col2:
                            st.write(f"**List B ({len(request_info.get('list_b', []))} addresses)**")
                            list_b = request_info.get('list_b', [])
                            for addr in list_b:
                                st.code(addr)
                        
                        st.divider()
                        
                        col1, col2, col3 = st.columns(3)
                        with col1:
                            st.metric("Max Depth", request_info.get('max_depth', 'N/A'))
                        with col2:
                            start_block = request_info.get('start_block')
                            st.metric("Start Block", start_block if start_block else "None")
                        with col3:
                            end_block = request_info.get('end_block')
                            st.metric("End Block", end_block if end_block else "None")
                    
                    st.divider()
                    
                    progress = details.get('progress', {})
                    if progress:
                        col1, col2, col3, col4 = st.columns(4)
                        with col1:
                            st.metric("Addresses Examined", progress.get('addresses_examined', 0))
                        with col2:
                            st.metric("Forward", progress.get('visited_forward', 0))
                        with col3:
                            st.metric("Backward", progress.get('visited_backward', 0))
                        with col4:
                            st.metric("Connections Found", progress.get('connections_found', 0))
                    
                    # Display connections if available
                    trace_state = details.get('trace_state', {})
                    connections_found = trace_state.get('connections_found', [])
                    if connections_found:
                        with st.expander(f"View {len(connections_found)} Connection(s)", expanded=False):
                            for idx, conn in enumerate(connections_found, 1):
                                st.write(f"**Connection {idx}:**")
                                col1, col2 = st.columns(2)
                                with col1:
                                    st.write(f"**Source:** `{conn.get('source', 'N/A')}`")
                                    st.write(f"**Target:** `{conn.get('target', 'N/A')}`")
                                    st.write(f"**Path Length:** {conn.get('path_count', 'N/A')}")
                                    st.write(f"**Found at Depth:** {conn.get('found_at_depth', 'N/A')}")
                                with col2:
                                    path = conn.get('path', [])
                                    if path:
                                        st.write("**Path:**")
                                        path_str = ' → '.join(path)
                                        st.code(path_str, language=None)
                                if idx < len(connections_found):
                                    st.divider()
                    
                    st.divider()
                    
                    col1, col2, col3 = st.columns(3)
                    
                    with col1:
                        if status == 'running':
                            if st.button("Stop", key=f"cancel_{session_id}", width='stretch', type="secondary"):
                                if cancel_session(session_id):
                                    st.rerun()
                    
                    with col2:
                        if status == 'completed':
                            if st.button("Results", key=f"results_{session_id}", width='stretch', type="secondary"):
                                try:
                                    results = requests.get(f"{API_URL}/results/{session_id}", timeout=API_TIMEOUT).json()
                                    st.json(results)
                                except Exception as e:
                                    st.error(f"Error: {e}")
                    
                    with col3:
                        if status in ['completed', 'cancelled', 'failed']:
                            if st.button("Delete", key=f"delete_{session_id}", width='stretch', type="secondary"):
                                if delete_session(session_id):
                                    st.rerun()
                    
                    st.divider()
                    
                    checkpoint_id = details.get('checkpoint_id')
                    if checkpoint_id:
                        col1, col2 = st.columns([3, 1])
                        with col1:
                            st.success(f"Checkpoint: {checkpoint_id[:16]}...")
                        with col2:
                            if st.button("Delete Checkpoint", key=f"delete_checkpoint_{session_id}", width='stretch', type="secondary"):
                                if delete_checkpoint(session_id, checkpoint_id):
                                    st.rerun()

# ========== TAB 2: NEW TRACE ==========
with tab2:
    st.header("Start New Trace")
    st.markdown("Enter Bitcoin addresses to trace connections")
    
    col1, col2 = st.columns(2)
    
    with col1:
        st.subheader("List A")
        list_a_text = st.text_area(
            "Enter addresses (one per line)",
            height=200,
            key="list_a"
        )
    
    with col2:
        st.subheader("List B")
        list_b_text = st.text_area(
            "Enter addresses (one per line)",
            height=200,
            key="list_b"
        )
    
    st.divider()
    
    max_depth = 5
    start_block = 0
    end_block = 999999999
    
    with st.expander("Advanced Options", expanded=False):
        col1, col2, col3 = st.columns(3)
        
        with col1:
            max_depth = st.slider("Max Depth", 1, 10, 5)
        with col2:
            start_block = st.number_input("Start Block", 0, value=0)
        with col3:
            end_block = st.number_input("End Block", 0, value=999999999)
    
    st.divider()
    
    list_a = [addr.strip() for addr in list_a_text.split('\n') if addr.strip()]
    list_b = [addr.strip() for addr in list_b_text.split('\n') if addr.strip()]
    
    if list_a and list_b:
        st.info(f"Ready: {len(list_a)} -> {len(list_b)} addresses (Depth: {max_depth})")
        
        col1, col2 = st.columns(2)
        
        with col1:
            if st.button("Start Trace", width='stretch', type="primary"):
                with st.spinner("Starting..."):
                    start_block_param = start_block if start_block > 0 else None
                    end_block_param = end_block if end_block < 999999999 else None
                    result = start_new_trace(list_a, list_b, max_depth, start_block_param, end_block_param)
                    if result:
                        st.success(f"Started! Session: {result['session_id'][:8]}...")
                        time.sleep(1)
                        st.rerun()
        
        with col2:
            if st.button("Clear", width='stretch', type="secondary"):
                st.rerun()
    else:
        st.warning("Enter addresses in both lists")

# ========== TAB 3: CHECKPOINTS ==========
with tab3:
    st.header("Checkpoints & Recovery")
    
    checkpoints = get_checkpoints()
    
    st.info(f"Total: {len(checkpoints)} checkpoints")
    
    if not checkpoints:
        st.warning("No checkpoints. Cancel a session to create one.")
    else:
        latest = checkpoints[0]
        
        st.subheader("Latest Checkpoint")
        col1, col2, col3 = st.columns(3)
        
        with col1:
            st.metric("Session", latest['session_id'][:12] + "...")
        with col2:
            st.metric("Status", latest['session_status'].upper())
        with col3:
            st.metric("Time", latest['timestamp'][:19])
        
        st.divider()
        
        if st.button("Resume Latest", width='stretch', type="primary"):
            with st.spinner("Resuming..."):
                result = resume_auto()
                if result:
                    time.sleep(1)
                    st.rerun()
        
        st.divider()
        
        st.subheader(f"All Checkpoints ({len(checkpoints)})")
        
        # Display checkpoints with details and actions
        for idx, cp in enumerate(checkpoints[:20]):
            # Get checkpoint details
            cp_details = get_checkpoint_details(cp['session_id'], cp['checkpoint_id'])
            
            # Create a row layout with expander and delete button
            # Use columns at the same level, not nested
            col_expander, col_delete = st.columns([5, 1])
            
            with col_expander:
                # Expander in its own column
                with st.expander(
                    f"**{cp['timestamp'][:19]}** | Session: {cp['session_id'][:12]}... | Status: {cp['session_status'].upper()}",
                    expanded=False
                ):
                    # Basic info
                    col1, col2, col3, col4 = st.columns(4)
                    with col1:
                        st.write(f"**Session ID**")
                        st.code(cp['session_id'][:20] + "...")
                    with col2:
                        st.write(f"**Checkpoint ID**")
                        st.code(cp['checkpoint_id'][:20] + "...")
                    with col3:
                        st.write(f"**Status**")
                        st.write(cp['session_status'].upper())
                    with col4:
                        st.write(f"**Timestamp**")
                        st.write(cp['timestamp'][:19])
                    
                    if cp_details:
                        # Progress metrics
                        progress = cp_details.get('progress', {})
                        if progress:
                            st.divider()
                            st.write("**Progress**")
                            col1, col2, col3, col4 = st.columns(4)
                            with col1:
                                st.metric("Addresses Examined", progress.get('addresses_examined', 0))
                            with col2:
                                st.metric("Forward", progress.get('visited_forward', 0))
                            with col3:
                                st.metric("Backward", progress.get('visited_backward', 0))
                            with col4:
                                st.metric("Connections", progress.get('connections_found', 0))
                        
                        # Load full checkpoint data to get connections
                        cp_full_data = load_checkpoint_data(cp['session_id'], cp['checkpoint_id'])
                        connections_found = []
                        if cp_full_data:
                            trace_state = cp_full_data.get('state', {}).get('trace_state', {})
                            connections_found = trace_state.get('connections_found', [])
                        
                        # Display connections found
                        if connections_found:
                            st.divider()
                            st.write(f"**Connections Found ({len(connections_found)})**")
                            
                            # Track which connection path to show using session state
                            path_display_key = f"show_path_{idx}_{cp['checkpoint_id']}"
                            
                            for conn_idx, conn in enumerate(connections_found):
                                source = conn.get('source', 'N/A')
                                target = conn.get('target', 'N/A')
                                path = conn.get('path', [])
                                path_length = conn.get('path_count', len(path))
                                
                                # Create a clickable connection display
                                col1, col2, col3 = st.columns([3, 1, 1])
                                with col1:
                                    st.write(f"**{conn_idx + 1}.** `{source[:20]}...` → `{target[:20]}...`")
                                with col2:
                                    st.caption(f"Path: {path_length} hops")
                                with col3:
                                    # Button to show full path
                                    button_key = f"show_path_btn_{idx}_{cp['checkpoint_id']}_{conn_idx}"
                                    if st.button("View Path", key=button_key, width='stretch'):
                                        if path:
                                            # Store which connection to show in session state
                                            st.session_state[path_display_key] = conn_idx
                                            
                                            # Show toast notification
                                            try:
                                                toast_msg = f"Showing path: {source[:12]}... → {target[:12]}... ({path_length} hops)"
                                                st.toast(toast_msg, icon="🔗")
                                            except (AttributeError, TypeError):
                                                # Fallback: toast not available
                                                pass
                                            st.rerun()
                            
                            # Display the selected path if one was clicked
                            if path_display_key in st.session_state:
                                selected_idx = st.session_state[path_display_key]
                                if selected_idx < len(connections_found):
                                    selected_conn = connections_found[selected_idx]
                                    selected_source = selected_conn.get('source', 'N/A')
                                    selected_target = selected_conn.get('target', 'N/A')
                                    selected_path = selected_conn.get('path', [])
                                    selected_length = selected_conn.get('path_count', len(selected_path))
                                    
                                    st.divider()
                                    st.markdown("### 🔗 Connection Path Details")
                                    
                                    col_a, col_b = st.columns(2)
                                    with col_a:
                                        st.markdown(f"**From:**\n`{selected_source}`")
                                    with col_b:
                                        st.markdown(f"**To:**\n`{selected_target}`")
                                    
                                    st.markdown(f"**Path Length:** {selected_length} hops")
                                    st.markdown("**Full Path:**")
                                    
                                    # Display path with better formatting - each address on its own line with arrows
                                    path_html = ""
                                    for i, addr in enumerate(selected_path):
                                        if i < len(selected_path) - 1:
                                            path_html += f"`{addr}` → "
                                        else:
                                            path_html += f"`{addr}`"
                                    
                                    st.markdown(path_html)
                                    
                                    # Button to close/hide the path
                                    if st.button("Close", key=f"close_path_{idx}_{cp['checkpoint_id']}"):
                                        if path_display_key in st.session_state:
                                            del st.session_state[path_display_key]
                                        st.rerun()
                                    
                                    st.divider()
                        
                        # Request parameters (list_a and list_b)
                        request_data = cp_details.get('request', {})
                        if request_data:
                            st.divider()
                            st.write("**Request Parameters**")
                            
                            col1, col2 = st.columns(2)
                            with col1:
                                list_a = request_data.get('list_a', [])
                                st.write(f"**List A ({len(list_a)} addresses)**")
                                if list_a:
                                    for addr in list_a[:10]:  # Show first 10
                                        st.code(addr)
                                    if len(list_a) > 10:
                                        list_key = f"show_list_a_{cp['checkpoint_id']}"
                                        if st.button(
                                            f"📋 ... and {len(list_a) - 10} more (click to view all)",
                                            key=list_key,
                                            help="Click to view all addresses in a copyable format"
                                        ):
                                            if dialog_decorator:
                                                view_full_list_dialog("List A", list_a)
                                            else:
                                                st.session_state.show_full_address_list = {
                                                    'type': 'list_a',
                                                    'checkpoint_id': cp['checkpoint_id'],
                                                    'addresses': list_a
                                                }
                                                try:
                                                    st.toast(f"Showing all {len(list_a)} addresses from List A", icon="📋")
                                                except:
                                                    pass
                                                st.rerun()
                                else:
                                    st.info("No addresses")
                            
                            with col2:
                                list_b = request_data.get('list_b', [])
                                st.write(f"**List B ({len(list_b)} addresses)**")
                                if list_b:
                                    for addr in list_b[:10]:  # Show first 10
                                        st.code(addr)
                                    if len(list_b) > 10:
                                        list_key = f"show_list_b_{cp['checkpoint_id']}"
                                        if st.button(
                                            f"📋 ... and {len(list_b) - 10} more (click to view all)",
                                            key=list_key,
                                            help="Click to view all addresses in a copyable format"
                                        ):
                                            if dialog_decorator:
                                                view_full_list_dialog("List B", list_b)
                                            else:
                                                st.session_state.show_full_address_list = {
                                                    'type': 'list_b',
                                                    'checkpoint_id': cp['checkpoint_id'],
                                                    'addresses': list_b
                                                }
                                                try:
                                                    st.toast(f"Showing all {len(list_b)} addresses from List B", icon="📋")
                                                except:
                                                    pass
                                                st.rerun()
                                else:
                                    st.info("No addresses")
                            
                            # Show full address list dialog (Fallback for older Streamlit versions)
                            if (not dialog_decorator and 
                                st.session_state.show_full_address_list and 
                                st.session_state.show_full_address_list.get('checkpoint_id') == cp['checkpoint_id']):
                                full_list_data = st.session_state.show_full_address_list
                                list_type = full_list_data.get('type', '').upper()
                                addresses = full_list_data.get('addresses', [])
                                
                                st.divider()
                                st.info(f"📋 **Full {list_type} - All {len(addresses)} Addresses**")
                                
                                # Create a single text string with all addresses (one per line)
                                addresses_text = '\n'.join(addresses)
                                
                                # Display in a text area that can be copied
                                st.text_area(
                                    f"All addresses from {list_type}",
                                    value=addresses_text,
                                    height=300,
                                    key=f"full_list_{full_list_data.get('type')}_{cp['checkpoint_id']}",
                                    help="Select all (Ctrl+A / Cmd+A) and copy (Ctrl+C / Cmd+C) to copy all addresses"
                                )
                                
                                # Close button
                                if st.button("Close", key=f"close_full_list_{cp['checkpoint_id']}"):
                                    st.session_state.show_full_address_list = None
                                    st.rerun()
                                
                                st.divider()
                            
                            # Additional request parameters
                            col1, col2, col3 = st.columns(3)
                            with col1:
                                st.metric("Max Depth", request_data.get('max_depth', 'N/A'))
                            with col2:
                                start_block = request_data.get('start_block')
                                st.metric("Start Block", start_block if start_block else "None")
                            with col3:
                                end_block = request_data.get('end_block')
                                st.metric("End Block", end_block if end_block else "None")
                
                    # Action buttons
                    st.divider()
                    if st.button("Resume from this Checkpoint", key=f"resume_cp_{idx}_{cp['checkpoint_id']}", width='stretch', type="primary"):
                        with st.spinner("Resuming..."):
                            result = resume_from_checkpoint(cp['session_id'], cp['checkpoint_id'])
                            if result:
                                time.sleep(1)
                                st.rerun()
            
            with col_delete:
                if st.button("🗑️ Delete", key=f"delete_cp_{idx}_{cp['checkpoint_id']}", width='stretch', type="secondary"):
                    if delete_checkpoint(cp['session_id'], cp['checkpoint_id']):
                        st.rerun()
            
            if idx < len(checkpoints[:20]) - 1:
                st.divider()

# ========== TAB 4: SETTINGS ==========
with tab4:
    st.header("Settings")
    st.markdown("Configure API provider and authentication")
    
    # Fetch current settings
    current_settings = get_settings()
    
    if current_settings:
        st.divider()
        
        # API Provider Selection
        st.subheader("API Provider")
        st.markdown("Select which blockchain API to use for address lookups")
        
        provider_options = {
            'mempool': 'Mempool.space (Recommended)',
            'blockchain': 'Blockchain.info',
            'electrumx': 'ElectrumX (Self-hosted)'
        }
        
        current_provider = current_settings.get('default_api', 'mempool')
        
        # Find index of current provider
        provider_keys = list(provider_options.keys())
        current_index = provider_keys.index(current_provider) if current_provider in provider_keys else 0
        
        selected_provider = st.selectbox(
            "Default API Provider",
            options=provider_keys,
            format_func=lambda x: provider_options[x],
            index=current_index,
            key="settings_provider"
        )
        
        # Provider descriptions
        provider_descriptions = {
            'mempool': "Public API with good rate limits. Supports API keys for higher limits.",
            'blockchain': "Blockchain.info public API. More restrictive rate limits.",
            'electrumx': "Connect to your own ElectrumX server. Requires server configuration in .env file."
        }
        st.caption(provider_descriptions.get(selected_provider, ""))
        
        st.divider()
        
        # Conditionally show Mempool API Key only when Mempool is selected
        if selected_provider == 'mempool':
            st.subheader("Mempool.space API Key")
            st.markdown("Enter your Mempool.space API key for higher rate limits")
            
            # Show if key is currently set
            if current_settings.get('mempool_api_key_set'):
                st.success("API key is currently set")
            else:
                st.info("No API key configured (using public rate limits)")
            
            mempool_api_key = st.text_input(
                "API Key",
                type="password",
                placeholder="Enter your Mempool.space API key",
                key="settings_mempool_key",
                help="Get an API key from mempool.space for higher rate limits"
            )
            
            # Option to clear the key
            clear_key = st.checkbox("Clear existing API key", key="settings_clear_key")
        else:
            mempool_api_key = ""
            clear_key = False
        
        # Conditionally show ElectrumX configuration when ElectrumX is selected
        if selected_provider == 'electrumx':
            st.divider()
            st.subheader("ElectrumX Server Configuration")
            st.markdown("Configure your ElectrumX server connection details")
            
            # Get current values or defaults
            current_host = current_settings.get('electrumx_host', '')
            current_port = current_settings.get('electrumx_port', '50001')
            current_use_ssl = current_settings.get('electrumx_use_ssl', 'false').lower() == 'true'
            current_cert = current_settings.get('electrumx_cert', '')
            
            col1, col2 = st.columns(2)
            
            with col1:
                electrumx_host = st.text_input(
                    "Server Host (IP or hostname)",
                    value=current_host,
                    placeholder="e.g., 100.94.34.56",
                    key="settings_electrumx_host",
                    help="IP address or hostname of your ElectrumX server"
                )
            
            with col2:
                electrumx_port = st.number_input(
                    "Server Port",
                    min_value=1,
                    max_value=65535,
                    value=int(current_port) if current_port.isdigit() else 50001,
                    key="settings_electrumx_port",
                    help="Port number (50001 for TCP, 50002 for SSL)"
                )
            
            electrumx_use_ssl = st.checkbox(
                "Use SSL Connection",
                value=current_use_ssl,
                key="settings_electrumx_ssl",
                help="Enable SSL/TLS encryption (required for port 50002)"
            )
            
            electrumx_cert = st.text_input(
                "SSL Certificate Path (Optional)",
                value=current_cert,
                placeholder="Leave empty to disable certificate verification",
                key="settings_electrumx_cert",
                help="Path to SSL certificate file for verification"
            )
            
            # Test Connection button
            st.divider()
            col_test1, col_test2 = st.columns([1, 3])
            with col_test1:
                if st.button("Test Connection", key="test_electrumx_connection", width='stretch', type="secondary"):
                    if electrumx_host and electrumx_port:
                        with st.spinner("Testing connection..."):
                            success, error_message = test_electrumx_connectivity(
                                electrumx_host,
                                electrumx_port,
                                electrumx_use_ssl,
                                electrumx_cert if electrumx_cert else None,
                                timeout=5
                            )
                            st.session_state.test_connection_result = {
                                'success': success,
                                'error_message': error_message,
                                'host': electrumx_host,
                                'port': electrumx_port
                            }
                            st.rerun()
                    else:
                        st.session_state.test_connection_result = {
                            'success': False,
                            'error_message': 'Host and port must be provided',
                            'host': electrumx_host or 'N/A',
                            'port': electrumx_port or 'N/A'
                        }
                        st.rerun()
            
            # Display test connection result
            if st.session_state.test_connection_result:
                result = st.session_state.test_connection_result
                if result.get('host') == electrumx_host and result.get('port') == electrumx_port:
                    if result.get('success'):
                        st.success(f"✅ Connection successful! Server at `{result.get('host')}:{result.get('port')}` is reachable and responding.")
                    else:
                        st.error(f"❌ Connection failed: {result.get('error_message', 'Unknown error')}")
                else:
                    # Result is for different host/port, clear it
                    st.session_state.test_connection_result = None
        else:
            electrumx_host = None
            electrumx_port = None
            electrumx_use_ssl = None
            electrumx_cert = None
            # Clear test result when not on ElectrumX tab
            if st.session_state.test_connection_result:
                st.session_state.test_connection_result = None
        
        st.divider()
        
        # Show success message if settings were just saved
        if st.session_state.settings_save_success:
            st.success("Settings saved successfully!")
            st.session_state.settings_save_success = False
        
        # Handle connectivity warning dialog
        if st.session_state.show_connectivity_warning and st.session_state.pending_electrumx_settings:
            st.error("⚠️ **ElectrumX Server Connectivity Warning**")
            pending = st.session_state.pending_electrumx_settings
            error_msg = pending.get('error_message', 'Unknown error')
            
            st.warning(f"""
**Server is not reachable:**
- Host: `{pending.get('host', 'N/A')}`
- Port: `{pending.get('port', 'N/A')}`
- Error: {error_msg}

You can still save these settings, but the server may not be accessible when using ElectrumX provider.
            """)
            
            col_warn1, col_warn2 = st.columns(2)
            with col_warn1:
                if st.button("Save Anyway", key="save_anyway", width='stretch', type="secondary"):
                    # Clear warning state first
                    st.session_state.show_connectivity_warning = False
                    # Proceed with save using pending settings
                    pending = st.session_state.pending_electrumx_settings
                    result = save_settings(
                        default_api=pending.get('default_api'),
                        mempool_api_key=pending.get('mempool_api_key'),
                        electrumx_host=pending.get('electrumx_host'),
                        electrumx_port=pending.get('electrumx_port'),
                        electrumx_use_ssl=pending.get('electrumx_use_ssl'),
                        electrumx_cert=pending.get('electrumx_cert')
                    )
                    st.session_state.pending_electrumx_settings = None
                    # Clear test connection result to avoid duplicates
                    st.session_state.test_connection_result = None
                    if result:
                        st.session_state.settings_save_success = True
                        st.rerun()
            with col_warn2:
                if st.button("Cancel", key="cancel_save", width='stretch', type="primary"):
                    # Clear warning state and pending settings
                    st.session_state.show_connectivity_warning = False
                    st.session_state.pending_electrumx_settings = None
                    st.rerun()
            
            st.divider()
        
        # Save button (only show if warning is not displayed)
        if not (st.session_state.show_connectivity_warning and st.session_state.pending_electrumx_settings):
            col1, col2 = st.columns([1, 3])
            
            with col1:
                if st.button("Save Settings", width='stretch', type="primary"):
                    # Prepare update payload
                    update_provider = selected_provider if selected_provider != current_provider else None
                    
                    # Handle API key (only if Mempool is selected)
                    update_key = None
                    if selected_provider == 'mempool':
                        if clear_key:
                            update_key = ""  # Clear the key
                        elif mempool_api_key:
                            update_key = mempool_api_key  # Set new key
                    
                    # Handle ElectrumX settings (only if ElectrumX is selected)
                    update_electrumx_host = None
                    update_electrumx_port = None
                    update_electrumx_use_ssl = None
                    update_electrumx_cert = None
                    
                    if selected_provider == 'electrumx':
                        # Check if values changed from current settings
                        current_host = current_settings.get('electrumx_host', '')
                        current_port = current_settings.get('electrumx_port', '50001')
                        current_use_ssl = current_settings.get('electrumx_use_ssl', 'false').lower() == 'true'
                        current_cert = current_settings.get('electrumx_cert', '')
                        
                        if electrumx_host and electrumx_host != current_host:
                            update_electrumx_host = electrumx_host
                        if electrumx_port and str(electrumx_port) != str(current_port):
                            update_electrumx_port = electrumx_port
                        if electrumx_use_ssl != current_use_ssl:
                            update_electrumx_use_ssl = 'true' if electrumx_use_ssl else 'false'
                        # Allow empty cert to clear it
                        if electrumx_cert != current_cert:
                            update_electrumx_cert = electrumx_cert
                    
                    # Only save if something changed
                    if (update_provider is not None or update_key is not None or 
                        update_electrumx_host is not None or update_electrumx_port is not None or
                        update_electrumx_use_ssl is not None or update_electrumx_cert is not None):
                        
                        # Test connectivity if ElectrumX settings are being updated or provider is being switched to ElectrumX
                        connectivity_test_failed = False
                        should_test_connectivity = (
                            selected_provider == 'electrumx' and 
                            (update_electrumx_host is not None or update_electrumx_port is not None or update_provider == 'electrumx')
                        )
                        
                        if should_test_connectivity:
                            # Use the new values if provided, otherwise use form values
                            test_host = update_electrumx_host if update_electrumx_host is not None else electrumx_host
                            test_port = update_electrumx_port if update_electrumx_port is not None else electrumx_port
                            test_ssl = update_electrumx_use_ssl == 'true' if update_electrumx_use_ssl is not None else electrumx_use_ssl
                            test_cert = update_electrumx_cert if update_electrumx_cert is not None else electrumx_cert
                            
                            if test_host and test_port:
                                with st.spinner("Testing server connectivity..."):
                                    success, error_message = test_electrumx_connectivity(
                                        test_host, 
                                        test_port, 
                                        test_ssl,
                                        test_cert if test_cert else None,
                                        timeout=5
                                    )
                                
                                if not success:
                                    # Store pending settings and show warning
                                    st.session_state.pending_electrumx_settings = {
                                        'default_api': update_provider,
                                        'mempool_api_key': update_key,
                                        'electrumx_host': update_electrumx_host,
                                        'electrumx_port': update_electrumx_port,
                                        'electrumx_use_ssl': update_electrumx_use_ssl,
                                        'electrumx_cert': update_electrumx_cert,
                                        'host': test_host,
                                        'port': test_port,
                                        'error_message': error_message
                                    }
                                    st.session_state.show_connectivity_warning = True
                                    connectivity_test_failed = True
                                    st.rerun()
                        
                        # Connectivity test passed or not needed, proceed with save
                        if not connectivity_test_failed:
                            with st.spinner("Saving settings..."):
                                result = save_settings(
                                    default_api=update_provider,
                                    mempool_api_key=update_key,
                                    electrumx_host=update_electrumx_host,
                                    electrumx_port=update_electrumx_port,
                                    electrumx_use_ssl=update_electrumx_use_ssl,
                                    electrumx_cert=update_electrumx_cert
                                )
                                
                                if result:
                                    # Clear test connection result to avoid duplicates
                                    st.session_state.test_connection_result = None
                                    st.session_state.settings_save_success = True
                                    st.rerun()
                    else:
                        st.info("No changes to save")
            
            with col2:
                st.caption("Settings are saved to the .env file and persist across restarts")
        
        st.divider()
        
        # Current Configuration Display
        with st.expander("Current Configuration", expanded=False):
            config_dict = {
                'default_api': current_settings.get('default_api', 'mempool'),
                'mempool_api_key_set': current_settings.get('mempool_api_key_set', False),
                'available_providers': current_settings.get('available_providers', [])
            }
            
            # Add ElectrumX configuration if available
            electrumx_config = {}
            if current_settings.get('electrumx_host'):
                electrumx_config['host'] = current_settings.get('electrumx_host')
            if current_settings.get('electrumx_port'):
                electrumx_config['port'] = current_settings.get('electrumx_port')
            if current_settings.get('electrumx_use_ssl'):
                electrumx_config['use_ssl'] = current_settings.get('electrumx_use_ssl').lower() == 'true'
            if current_settings.get('electrumx_cert'):
                electrumx_config['cert'] = current_settings.get('electrumx_cert')
            
            if electrumx_config:
                config_dict['electrumx'] = electrumx_config
            
            st.json(config_dict)
    else:
        st.error("Could not load settings. Make sure the API server is running.")
        if st.button("Retry", width='stretch'):
            st.rerun()

# Footer
st.divider()
st.markdown(f"""
<div style='text-align: center; color: gray; font-size: 12px;'>
    <p>Bitcoin Address Linker | Streamlit UI</p>
    <p>Updated: {datetime.now().strftime('%H:%M:%S')}</p>
</div>
""", unsafe_allow_html=True)

# Auto-refresh
if st.session_state.auto_refresh_enabled:
    time.sleep(60)
    st.rerun()