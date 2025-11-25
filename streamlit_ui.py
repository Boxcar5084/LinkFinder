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
from config import EXPORT_DIR

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

def cancel_all_running_sessions():
    """Cancel all running sessions (kill switch)"""
    sessions = get_sessions()
    running_sessions = [s for s in sessions if s.get('status') == 'running']
    
    if not running_sessions:
        st.info("No running sessions to cancel.")
        return 0
    
    cancelled_count = 0
    errors = []
    
    for session in running_sessions:
        session_id = session['session_id']
        try:
            response = requests.post(f"{API_URL}/cancel/{session_id}", timeout=API_TIMEOUT)
            if response.status_code == 200:
                cancelled_count += 1
            else:
                errors.append(f"Session {session_id[:12]}...: Status {response.status_code}")
        except Exception as e:
            errors.append(f"Session {session_id[:12]}...: {str(e)}")
    
    if cancelled_count > 0:
        st.success(f"✅ Cancelled {cancelled_count} running session(s).")
    
    if errors:
        for error in errors:
            st.error(error)
    
    return cancelled_count

def force_checkpoint_all_running_sessions():
    """Force create checkpoints for all running sessions"""
    sessions = get_sessions()
    running_sessions = [s for s in sessions if s.get('status') == 'running']
    
    if not running_sessions:
        st.info("No running sessions to checkpoint.")
        return 0
    
    checkpointed_count = 0
    errors = []
    
    for session in running_sessions:
        session_id = session['session_id']
        try:
            response = requests.post(f"{API_URL}/checkpoint/{session_id}/force", timeout=API_TIMEOUT)
            if response.status_code == 200:
                result = response.json()
                checkpointed_count += 1
                checkpoint_id = result.get('checkpoint_id', 'N/A')
                progress = result.get('progress', {})
                addresses = progress.get('addresses_examined', 0)
                st.success(f"✅ Checkpoint created for session {session_id[:12]}... (ID: {checkpoint_id[:12]}..., {addresses} addresses)")
            else:
                error_msg = response.json().get('message', f"Status {response.status_code}")
                errors.append(f"Session {session_id[:12]}...: {error_msg}")
        except Exception as e:
            errors.append(f"Session {session_id[:12]}...: {str(e)}")
    
    if checkpointed_count > 0:
        st.success(f"✅ Created checkpoints for {checkpointed_count} running session(s).")
    
    if errors:
        for error in errors:
            st.error(error)
    
    return checkpointed_count

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

def save_settings(default_api=None, mempool_api_key=None, electrumx_host=None, electrumx_port=None, electrumx_use_ssl=None, electrumx_cert=None, use_cache=None,
                  mixer_input_threshold=None, mixer_output_threshold=None, suspicious_ratio_threshold=None,
                  skip_mixer_input_threshold=None, skip_mixer_output_threshold=None,
                  skip_distribution_max_inputs=None, skip_distribution_min_outputs=None,
                  max_transactions_per_address=None, max_depth=None, exchange_wallet_threshold=None,
                  max_input_addresses_per_tx=None, max_output_addresses_per_tx=None):
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
        if use_cache is not None:
            payload['use_cache'] = use_cache
        # Threshold settings
        if mixer_input_threshold is not None:
            payload['mixer_input_threshold'] = mixer_input_threshold
        if mixer_output_threshold is not None:
            payload['mixer_output_threshold'] = mixer_output_threshold
        if suspicious_ratio_threshold is not None:
            payload['suspicious_ratio_threshold'] = suspicious_ratio_threshold
        if skip_mixer_input_threshold is not None:
            payload['skip_mixer_input_threshold'] = skip_mixer_input_threshold
        if skip_mixer_output_threshold is not None:
            payload['skip_mixer_output_threshold'] = skip_mixer_output_threshold
        if skip_distribution_max_inputs is not None:
            payload['skip_distribution_max_inputs'] = skip_distribution_max_inputs
        if skip_distribution_min_outputs is not None:
            payload['skip_distribution_min_outputs'] = skip_distribution_min_outputs
        if max_transactions_per_address is not None:
            payload['max_transactions_per_address'] = max_transactions_per_address
        if max_depth is not None:
            payload['max_depth'] = max_depth
        if exchange_wallet_threshold is not None:
            payload['exchange_wallet_threshold'] = exchange_wallet_threshold
        if max_input_addresses_per_tx is not None:
            payload['max_input_addresses_per_tx'] = max_input_addresses_per_tx
        if max_output_addresses_per_tx is not None:
            payload['max_output_addresses_per_tx'] = max_output_addresses_per_tx
        
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
        
        st.divider()
        
        if st.button("Force Checkpoint All Running Sessions", key="force_checkpoint", width='stretch', type="secondary"):
            checkpointed = force_checkpoint_all_running_sessions()
            if checkpointed > 0:
                st.rerun()
        
        if st.button("Cancel All Running Sessions", key="kill_switch", width='stretch', type="primary"):
            cancelled = cancel_all_running_sessions()
            if cancelled > 0:
                st.rerun()

# Main tabs
tab1, tab2, tab3, tab4, tab5 = st.tabs(["Active Sessions", "New Trace", "Checkpoints", "Found Connections", "Settings"])

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

# ========== TAB 4: FOUND CONNECTIONS ==========
with tab4:
    st.header("Found Connections")
    st.markdown("View connections found in export files")
    
    def get_export_files():
        """Scan exports directory and return list of export files with metadata"""
        export_dir = Path(EXPORT_DIR)
        if not export_dir.exists():
            return []
        
        export_files = []
        json_files = list(export_dir.glob("connections_*.json"))
        
        for json_file in json_files:
            # Parse filename: connections_{session_id}_{timestamp}.json
            filename = json_file.stem  # Remove .json extension
            parts = filename.split('_', 2)  # Split on first two underscores
            if len(parts) >= 3 and parts[0] == 'connections':
                session_id = parts[1]
                timestamp_str = '_'.join(parts[2:])  # Rejoin remaining parts for timestamp
                
                # Find corresponding CSV file
                csv_file = export_dir / f"{filename}.csv"
                
                export_files.append({
                    'session_id': session_id,
                    'timestamp': timestamp_str,
                    'json_path': str(json_file),
                    'csv_path': str(csv_file) if csv_file.exists() else None,
                    'filename': json_file.name
                })
        
        # Sort by timestamp (newest first)
        export_files.sort(key=lambda x: x['timestamp'], reverse=True)
        return export_files
    
    def load_export_connections(json_path):
        """Load and parse JSON export file to extract connections_found array"""
        try:
            with open(json_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
                return data.get('connections_found', [])
        except Exception as e:
            st.error(f"Error loading export file {json_path}: {e}")
            return []
    
    def get_active_session_ids():
        """Fetch active session IDs from API"""
        sessions = get_sessions()
        return [s['session_id'] for s in sessions]
    
    # Get all export files
    all_export_files = get_export_files()
    
    # Filter out files with 0 connections
    export_files = []
    for exp_file in all_export_files:
        connections = load_export_connections(exp_file['json_path'])
        if len(connections) > 0:
            exp_file['connections'] = connections
            export_files.append(exp_file)
    
    if not export_files:
        st.info("No export files with connections found. Export files are created when sessions complete.")
    else:
        # Collect all connections from all export files and group by source/target
        connections_by_pair = {}
        
        for exp_file in export_files:
            connections = exp_file['connections']
            session_id = exp_file['session_id']
            timestamp = exp_file['timestamp']
            
            # Format timestamp for display (YYYYMMDD_HHMMSS -> YYYY-MM-DD HH:MM:SS)
            try:
                if len(timestamp) == 15 and '_' in timestamp:
                    date_part = timestamp[:8]
                    time_part = timestamp[9:]
                    formatted_timestamp = f"{date_part[:4]}-{date_part[4:6]}-{date_part[6:8]} {time_part[:2]}:{time_part[2:4]}:{time_part[4:6]}"
                else:
                    formatted_timestamp = timestamp
            except:
                formatted_timestamp = timestamp
            
            for conn in connections:
                source = conn.get('source', 'N/A')
                target = conn.get('target', 'N/A')
                pair_key = (source, target)
                
                if pair_key not in connections_by_pair:
                    connections_by_pair[pair_key] = []
                
                # Store connection with metadata about which export file it came from
                connections_by_pair[pair_key].append({
                    'connection': conn,
                    'session_id': session_id,
                    'timestamp': formatted_timestamp,
                    'export_file': exp_file
                })
        
        # Calculate summary metrics
        total_connections = sum(len(exp_file['connections']) for exp_file in export_files)
        unique_pairs = len(connections_by_pair)
        
        # Display summary metrics
        col1, col2, col3 = st.columns(3)
        with col1:
            st.metric("Export Files with Connections", len(export_files))
        with col2:
            st.metric("Total Connections", total_connections)
        with col3:
            st.metric("Unique Source/Target Pairs", unique_pairs)
        
        st.divider()
        
        # Display connections grouped by source/target pair, then by path
        for idx, ((source, target), conn_list) in enumerate(connections_by_pair.items()):
            # Truncate addresses for display if too long
            source_display = source[:30] + "..." if len(source) > 30 else source
            target_display = target[:30] + "..." if len(target) > 30 else target
            
            # Group connections by their actual path sequence
            paths_by_sequence = {}
            for conn_data in conn_list:
                conn = conn_data['connection']
                path = conn.get('path', [])
                # Use tuple of path for hashing/comparison
                path_key = tuple(path) if path else tuple()
                
                if path_key not in paths_by_sequence:
                    paths_by_sequence[path_key] = {
                        'path': path,
                        'path_length': conn.get('path_count', len(path)),
                        'depth': conn.get('found_at_depth', 'N/A'),
                        'sessions': []
                    }
                
                # Add session info to this path
                paths_by_sequence[path_key]['sessions'].append({
                    'session_id': conn_data['session_id'],
                    'timestamp': conn_data['timestamp']
                })
            
            unique_paths_count = len(paths_by_sequence)
            
            with st.expander(
                f"**{source_display}** → **{target_display}** ({unique_paths_count} unique path{'s' if unique_paths_count > 1 else ''})",
                expanded=False
            ):
                # Display source and target in full
                col1, col2 = st.columns(2)
                with col1:
                    st.write(f"**Source:**")
                    st.code(source, language=None)
                with col2:
                    st.write(f"**Target:**")
                    st.code(target, language=None)
                
                st.divider()
                
                # Display all unique paths for this source/target pair
                st.write(f"**Unique Paths Found ({unique_paths_count})**")
                
                for path_idx, (path_key, path_data) in enumerate(paths_by_sequence.items()):
                    path = path_data['path']
                    path_length = path_data['path_length']
                    depth = path_data['depth']
                    sessions = path_data['sessions']
                    
                    st.write(f"**Path {path_idx + 1}:**")
                    col_a, col_b = st.columns(2)
                    with col_a:
                        st.write(f"**Path Length:** {path_length} hops")
                        st.write(f"**Found at Depth:** {depth}")
                        st.write(f"**Found in {len(sessions)} session{'s' if len(sessions) > 1 else ''}:**")
                        for sess_info in sessions:
                            st.caption(f"• Session: {sess_info['session_id'][:12]}... | {sess_info['timestamp']}")
                    with col_b:
                        if path:
                            st.write("**Path:**")
                            path_str = ' → '.join(path)
                            st.code(path_str, language=None)
                    
                    if path_idx < len(paths_by_sequence) - 1:
                        st.divider()
            
            if idx < len(connections_by_pair) - 1:
                st.divider()

# ========== TAB 5: SETTINGS ==========
with tab5:
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
        
        # Cache Settings (Troubleshooting)
        st.subheader("Cache Settings")
        st.markdown("Enable or disable transaction caching for troubleshooting")
        
        current_use_cache = current_settings.get('use_cache', True)
        use_cache = st.checkbox(
            "Enable Transaction Cache",
            value=current_use_cache,
            key="settings_use_cache",
            help="When enabled, transactions are cached to speed up subsequent searches. Disable to bypass cache for troubleshooting (e.g., if connections are not being found). Note: Server restart may be required for this setting to take effect."
        )
        
        if not use_cache:
            st.warning("⚠️ Cache is disabled. All transactions will be fetched from the API, which may be slower but ensures fresh data.")
        
        st.divider()
        
        # Tracing Thresholds Settings
        st.subheader("Tracing Thresholds")
        st.markdown("Configure thresholds for transaction filtering and tracing behavior")
        
        # Reset to suggested values button
        col_reset1, col_reset2 = st.columns([1, 4])
        with col_reset1:
            if st.button("🔄 Reset to Suggested Values", key="reset_thresholds", type="secondary", help="Reset all tracing thresholds to their suggested default values"):
                # Suggested/default values
                suggested_values = {
                    'mixer_input_threshold': 30,
                    'mixer_output_threshold': 30,
                    'suspicious_ratio_threshold': 10,
                    'skip_mixer_input_threshold': 50,
                    'skip_mixer_output_threshold': 50,
                    'skip_distribution_max_inputs': 2,
                    'skip_distribution_min_outputs': 100,
                    'max_transactions_per_address': 50,
                    'max_depth': 10,
                    'exchange_wallet_threshold': 1000,
                    'max_input_addresses_per_tx': 50,
                    'max_output_addresses_per_tx': 50
                }
                
                # Save immediately
                with st.spinner("Resetting to suggested values..."):
                    result = save_settings(
                        mixer_input_threshold=suggested_values['mixer_input_threshold'],
                        mixer_output_threshold=suggested_values['mixer_output_threshold'],
                        suspicious_ratio_threshold=suggested_values['suspicious_ratio_threshold'],
                        skip_mixer_input_threshold=suggested_values['skip_mixer_input_threshold'],
                        skip_mixer_output_threshold=suggested_values['skip_mixer_output_threshold'],
                        skip_distribution_max_inputs=suggested_values['skip_distribution_max_inputs'],
                        skip_distribution_min_outputs=suggested_values['skip_distribution_min_outputs'],
                        max_transactions_per_address=suggested_values['max_transactions_per_address'],
                        max_depth=suggested_values['max_depth'],
                        exchange_wallet_threshold=suggested_values['exchange_wallet_threshold'],
                        max_input_addresses_per_tx=suggested_values['max_input_addresses_per_tx'],
                        max_output_addresses_per_tx=suggested_values['max_output_addresses_per_tx']
                    )
                    
                    if result:
                        st.session_state.settings_save_success = True
                        st.success("✅ All thresholds reset to suggested values!")
                        time.sleep(1)
                        st.rerun()
                    else:
                        st.error("Failed to reset thresholds")
        
        with col_reset2:
            st.caption("Click to restore all tracing thresholds to their recommended default values")
        
        st.divider()
        
        # Get current threshold values from settings
        current_mixer_input = current_settings.get('mixer_input_threshold', 30)
        current_mixer_output = current_settings.get('mixer_output_threshold', 30)
        current_suspicious_ratio = current_settings.get('suspicious_ratio_threshold', 10)
        current_skip_mixer_input = current_settings.get('skip_mixer_input_threshold', 50)
        current_skip_mixer_output = current_settings.get('skip_mixer_output_threshold', 50)
        current_skip_dist_max_inputs = current_settings.get('skip_distribution_max_inputs', 2)
        current_skip_dist_min_outputs = current_settings.get('skip_distribution_min_outputs', 100)
        current_max_tx_per_addr = current_settings.get('max_transactions_per_address', 50)
        current_max_depth = current_settings.get('max_depth', 10)
        current_exchange_threshold = current_settings.get('exchange_wallet_threshold', 1000)
        current_max_input_addrs = current_settings.get('max_input_addresses_per_tx', 50)
        current_max_output_addrs = current_settings.get('max_output_addresses_per_tx', 50)
        
        # Mixer Detection Thresholds
        with st.expander("Mixer Detection Thresholds", expanded=False):
            st.markdown("""
            **Purpose:** Identify mixer-like transactions that have many inputs and/or outputs.
            These thresholds help detect privacy-focused transactions that may not be useful for tracing connections.
            """)
            
            st.info("💡 **Suggested Values:** Input: 30, Output: 30, Ratio: 10 | These values are based on typical CoinJoin/mixer patterns where transactions have 30+ inputs/outputs. The ratio of 10 catches extreme imbalances (e.g., 1:10 or 10:1) that indicate suspicious patterns.")
            
            col1, col2 = st.columns(2)
            with col1:
                mixer_input_threshold = st.number_input(
                    "Mixer Input Threshold",
                    min_value=1,
                    max_value=1000,
                    value=current_mixer_input,
                    key="settings_mixer_input",
                    help="Minimum number of inputs to be considered 'mixer-like'. Transactions with this many or more inputs are flagged as potential mixers. Suggested: 30 (typical CoinJoin size)."
                )
            
            with col2:
                mixer_output_threshold = st.number_input(
                    "Mixer Output Threshold",
                    min_value=1,
                    max_value=1000,
                    value=current_mixer_output,
                    key="settings_mixer_output",
                    help="Minimum number of outputs to be considered 'mixer-like'. Transactions with this many or more outputs are flagged as potential mixers. Suggested: 30 (typical CoinJoin size)."
                )
            
            suspicious_ratio_threshold = st.number_input(
                "Suspicious Ratio Threshold",
                min_value=1,
                max_value=100,
                value=current_suspicious_ratio,
                key="settings_suspicious_ratio",
                help="Input:output or output:input ratio to flag as suspicious. Transactions with extreme ratios (e.g., 1 input to 100 outputs) are flagged. Suggested: 10 (catches 10:1 or 1:10 imbalances)."
            )
        
        # Transaction Filtering Thresholds
        with st.expander("Transaction Filtering Thresholds", expanded=False):
            st.markdown("""
            **Purpose:** Filter out extreme mixer transactions that would flood the processing queue.
            These transactions are skipped entirely to improve performance and focus on meaningful connections.
            """)
            
            st.info("💡 **Suggested Values:** Input: 50, Output: 50 | These values filter out extreme mixers (50+ inputs/outputs) that would create thousands of queue entries. This threshold is higher than the detection threshold (30) to allow some mixer analysis while preventing queue flooding from massive CoinJoin transactions.")
            
            col1, col2 = st.columns(2)
            with col1:
                skip_mixer_input_threshold = st.number_input(
                    "Skip Mixer Input Threshold",
                    min_value=1,
                    max_value=1000,
                    value=current_skip_mixer_input,
                    key="settings_skip_mixer_input",
                    help="Minimum inputs for extreme mixer. Transactions with this many or more inputs are completely skipped (prevents queue flooding). Suggested: 50 (filters extreme mixers while allowing smaller ones)."
                )
            
            with col2:
                skip_mixer_output_threshold = st.number_input(
                    "Skip Mixer Output Threshold",
                    min_value=1,
                    max_value=1000,
                    value=current_skip_mixer_output,
                    key="settings_skip_mixer_output",
                    help="Minimum outputs for extreme mixer. Transactions with this many or more outputs are completely skipped (prevents queue flooding). Suggested: 50 (filters extreme mixers while allowing smaller ones)."
                )
        
        # Airdrop/Distribution Detection
        with st.expander("Airdrop/Distribution Detection (MOST IMPORTANT)", expanded=True):
            st.markdown("""
            **Purpose:** Filter out airdrop and distribution transactions that create false connections.
            
            **Why this is critical:** Airdrop transactions typically have 1-2 inputs and hundreds of outputs, 
            connecting many unrelated addresses. These create false positive connections and should be filtered out.
            """)
            
            st.warning("💡 **Suggested Values:** Max Inputs: 2, Min Outputs: 100 | Most airdrops have 1-2 inputs (single funding source) and 100+ outputs (many recipients). This pattern (few inputs, many outputs) is the signature of distribution transactions. Setting max inputs to 2 catches 99% of airdrops while allowing legitimate multi-input transactions. The 100 output threshold ensures we only filter true distributions, not normal transactions with many outputs.")
            
            col1, col2 = st.columns(2)
            with col1:
                skip_distribution_max_inputs = st.number_input(
                    "Max Inputs for Distribution",
                    min_value=1,
                    max_value=10,
                    value=current_skip_dist_max_inputs,
                    key="settings_skip_dist_max_inputs",
                    help="Maximum number of inputs to trigger distribution filter. Transactions with this many or fewer inputs AND the minimum outputs are considered distributions. Suggested: 2 (most airdrops have 1-2 inputs)."
                )
            
            with col2:
                skip_distribution_min_outputs = st.number_input(
                    "Min Outputs for Distribution",
                    min_value=10,
                    max_value=10000,
                    value=current_skip_dist_min_outputs,
                    key="settings_skip_dist_min_outputs",
                    help="Minimum number of outputs to trigger distribution filter. Transactions with max inputs AND this many or more outputs are skipped. Suggested: 100 (catches airdrops while allowing normal transactions)."
                )
        
        # Processing Limits
        with st.expander("Processing Limits", expanded=False):
            st.markdown("""
            **Purpose:** Limit processing to prevent resource exhaustion and focus on relevant transactions.
            """)
            
            st.info("💡 **Suggested Values:** Max TX/Address: 50, Max Depth: 10, Exchange Threshold: 1000 | Limiting to 50 transactions per address balances thoroughness with performance. Depth of 10 allows tracing through multiple hops while preventing infinite loops. Exchange threshold of 1000 identifies high-volume addresses (exchanges, services) that aren't useful for tracing individual connections.")
            
            col1, col2 = st.columns(2)
            with col1:
                max_transactions_per_address = st.number_input(
                    "Max Transactions Per Address",
                    min_value=1,
                    max_value=10000,
                    value=current_max_tx_per_addr,
                    key="settings_max_tx_per_addr",
                    help="Maximum number of transactions to process per address. Addresses with more transactions are limited to this number. Suggested: 50 (balances thoroughness with performance)."
                )
            
            with col2:
                max_depth = st.number_input(
                    "Max Tracing Depth",
                    min_value=1,
                    max_value=50,
                    value=current_max_depth,
                    key="settings_max_depth",
                    help="Maximum depth for tracing connections. Stops tracing after this many hops from the starting addresses. Suggested: 10 (allows multi-hop tracing while preventing infinite loops)."
                )
            
            exchange_wallet_threshold = st.number_input(
                "Exchange Wallet Threshold",
                min_value=100,
                max_value=100000,
                value=current_exchange_threshold,
                key="settings_exchange_threshold",
                help="Addresses with more than this many transactions are considered exchange wallets and are skipped entirely. Exchange wallets have too many transactions to be useful for tracing. Suggested: 1000 (identifies high-volume addresses like exchanges)."
            )
        
        # Address Filtering Limits
        with st.expander("Address Filtering Limits", expanded=False):
            st.markdown("""
            **Purpose:** Prevent queue flooding from transactions with many inputs or outputs.
            These limits cap how many addresses are processed per transaction.
            """)
            
            st.info("💡 **Suggested Values:** Max Input: 50, Max Output: 50 | These limits prevent queue flooding from large transactions while still processing a reasonable number of addresses. Transactions with 50+ inputs/outputs are already filtered by the skip mixer thresholds, so this acts as a safety net for edge cases. The value of 50 matches the skip mixer threshold to maintain consistency.")
            
            col1, col2 = st.columns(2)
            with col1:
                max_input_addresses_per_tx = st.number_input(
                    "Max Input Addresses Per Transaction",
                    min_value=1,
                    max_value=1000,
                    value=current_max_input_addrs,
                    key="settings_max_input_addrs",
                    help="Maximum input addresses to process per transaction. If a transaction has more inputs, only the first N are processed (prevents queue flooding). Suggested: 50 (matches skip mixer threshold, prevents queue flooding)."
                )
            
            with col2:
                max_output_addresses_per_tx = st.number_input(
                    "Max Output Addresses Per Transaction",
                    min_value=1,
                    max_value=1000,
                    value=current_max_output_addrs,
                    key="settings_max_output_addrs",
                    help="Maximum output addresses to process per transaction. If a transaction has more outputs, only the first N are processed (prevents queue flooding). Suggested: 50 (matches skip mixer threshold, prevents queue flooding)."
                )
        
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
                        electrumx_cert=pending.get('electrumx_cert'),
                        use_cache=pending.get('use_cache'),
                        mixer_input_threshold=pending.get('mixer_input_threshold'),
                        mixer_output_threshold=pending.get('mixer_output_threshold'),
                        suspicious_ratio_threshold=pending.get('suspicious_ratio_threshold'),
                        skip_mixer_input_threshold=pending.get('skip_mixer_input_threshold'),
                        skip_mixer_output_threshold=pending.get('skip_mixer_output_threshold'),
                        skip_distribution_max_inputs=pending.get('skip_distribution_max_inputs'),
                        skip_distribution_min_outputs=pending.get('skip_distribution_min_outputs'),
                        max_transactions_per_address=pending.get('max_transactions_per_address'),
                        max_depth=pending.get('max_depth'),
                        exchange_wallet_threshold=pending.get('exchange_wallet_threshold'),
                        max_input_addresses_per_tx=pending.get('max_input_addresses_per_tx'),
                        max_output_addresses_per_tx=pending.get('max_output_addresses_per_tx')
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
                    
                    # Handle cache setting
                    update_use_cache = None
                    if use_cache != current_use_cache:
                        update_use_cache = use_cache
                    
                    # Handle threshold settings
                    update_mixer_input = None
                    update_mixer_output = None
                    update_suspicious_ratio = None
                    update_skip_mixer_input = None
                    update_skip_mixer_output = None
                    update_skip_dist_max_inputs = None
                    update_skip_dist_min_outputs = None
                    update_max_tx_per_addr = None
                    update_max_depth = None
                    update_exchange_threshold = None
                    update_max_input_addrs = None
                    update_max_output_addrs = None
                    
                    if mixer_input_threshold != current_mixer_input:
                        update_mixer_input = mixer_input_threshold
                    if mixer_output_threshold != current_mixer_output:
                        update_mixer_output = mixer_output_threshold
                    if suspicious_ratio_threshold != current_suspicious_ratio:
                        update_suspicious_ratio = suspicious_ratio_threshold
                    if skip_mixer_input_threshold != current_skip_mixer_input:
                        update_skip_mixer_input = skip_mixer_input_threshold
                    if skip_mixer_output_threshold != current_skip_mixer_output:
                        update_skip_mixer_output = skip_mixer_output_threshold
                    if skip_distribution_max_inputs != current_skip_dist_max_inputs:
                        update_skip_dist_max_inputs = skip_distribution_max_inputs
                    if skip_distribution_min_outputs != current_skip_dist_min_outputs:
                        update_skip_dist_min_outputs = skip_distribution_min_outputs
                    if max_transactions_per_address != current_max_tx_per_addr:
                        update_max_tx_per_addr = max_transactions_per_address
                    if max_depth != current_max_depth:
                        update_max_depth = max_depth
                    if exchange_wallet_threshold != current_exchange_threshold:
                        update_exchange_threshold = exchange_wallet_threshold
                    if max_input_addresses_per_tx != current_max_input_addrs:
                        update_max_input_addrs = max_input_addresses_per_tx
                    if max_output_addresses_per_tx != current_max_output_addrs:
                        update_max_output_addrs = max_output_addresses_per_tx
                    
                    # Only save if something changed
                    if (update_provider is not None or update_key is not None or 
                        update_electrumx_host is not None or update_electrumx_port is not None or
                        update_electrumx_use_ssl is not None or update_electrumx_cert is not None or
                        update_use_cache is not None or
                        update_mixer_input is not None or update_mixer_output is not None or
                        update_suspicious_ratio is not None or update_skip_mixer_input is not None or
                        update_skip_mixer_output is not None or update_skip_dist_max_inputs is not None or
                        update_skip_dist_min_outputs is not None or update_max_tx_per_addr is not None or
                        update_max_depth is not None or update_exchange_threshold is not None or
                        update_max_input_addrs is not None or update_max_output_addrs is not None):
                        
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
                                        'use_cache': update_use_cache,
                                        'mixer_input_threshold': update_mixer_input,
                                        'mixer_output_threshold': update_mixer_output,
                                        'suspicious_ratio_threshold': update_suspicious_ratio,
                                        'skip_mixer_input_threshold': update_skip_mixer_input,
                                        'skip_mixer_output_threshold': update_skip_mixer_output,
                                        'skip_distribution_max_inputs': update_skip_dist_max_inputs,
                                        'skip_distribution_min_outputs': update_skip_dist_min_outputs,
                                        'max_transactions_per_address': update_max_tx_per_addr,
                                        'max_depth': update_max_depth,
                                        'exchange_wallet_threshold': update_exchange_threshold,
                                        'max_input_addresses_per_tx': update_max_input_addrs,
                                        'max_output_addresses_per_tx': update_max_output_addrs,
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
                                    electrumx_cert=update_electrumx_cert,
                                    use_cache=update_use_cache,
                                    mixer_input_threshold=update_mixer_input,
                                    mixer_output_threshold=update_mixer_output,
                                    suspicious_ratio_threshold=update_suspicious_ratio,
                                    skip_mixer_input_threshold=update_skip_mixer_input,
                                    skip_mixer_output_threshold=update_skip_mixer_output,
                                    skip_distribution_max_inputs=update_skip_dist_max_inputs,
                                    skip_distribution_min_outputs=update_skip_dist_min_outputs,
                                    max_transactions_per_address=update_max_tx_per_addr,
                                    max_depth=update_max_depth,
                                    exchange_wallet_threshold=update_exchange_threshold,
                                    max_input_addresses_per_tx=update_max_input_addrs,
                                    max_output_addresses_per_tx=update_max_output_addrs
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
        
        st.divider()
        
        # Export File Management
        st.subheader("Export File Management")
        st.markdown("Delete export files that have no connections and are not part of active sessions")
        
        def get_export_files_to_delete():
            """Identify export files that have no connections and are not part of active sessions"""
            export_dir = Path(EXPORT_DIR)
            if not export_dir.exists():
                return []
            
            # Get active session IDs
            sessions = get_sessions()
            active_session_ids = [s['session_id'] for s in sessions]
            files_to_delete = []
            
            json_files = list(export_dir.glob("connections_*.json"))
            for json_file in json_files:
                # Parse session_id from filename
                filename = json_file.stem
                parts = filename.split('_', 2)
                if len(parts) >= 3 and parts[0] == 'connections':
                    session_id = parts[1]
                    
                    # Check if session is active
                    if session_id in active_session_ids:
                        continue
                    
                    # Check if file has connections
                    try:
                        with open(json_file, 'r', encoding='utf-8') as f:
                            data = json.load(f)
                            connections = data.get('connections_found', [])
                            if len(connections) == 0:
                                # Find corresponding CSV file
                                csv_file = export_dir / f"{filename}.csv"
                                files_to_delete.append({
                                    'session_id': session_id,
                                    'json_path': str(json_file),
                                    'csv_path': str(csv_file) if csv_file.exists() else None,
                                    'filename': json_file.name
                                })
                    except Exception:
                        # If we can't read the file, skip it
                        continue
            
            return files_to_delete
        
        def delete_export_files(file_paths):
            """Delete specified export files"""
            deleted = []
            errors = []
            
            for file_info in file_paths:
                try:
                    # Delete JSON file
                    json_path = Path(file_info['json_path'])
                    if json_path.exists():
                        json_path.unlink()
                        deleted.append(file_info['json_path'])
                    
                    # Delete CSV file if it exists
                    if file_info['csv_path']:
                        csv_path = Path(file_info['csv_path'])
                        if csv_path.exists():
                            csv_path.unlink()
                            deleted.append(file_info['csv_path'])
                except Exception as e:
                    errors.append(f"Error deleting {file_info['filename']}: {e}")
            
            return deleted, errors
        
        # Get files eligible for deletion
        files_to_delete = get_export_files_to_delete()
        
        if files_to_delete:
            st.info(f"Found {len(files_to_delete)} export file(s) eligible for deletion")
            
            # Show list of files to be deleted
            with st.expander("View files to be deleted", expanded=False):
                for file_info in files_to_delete:
                    st.write(f"- `{file_info['filename']}` (Session: {file_info['session_id'][:12]}...)")
            
            # Delete button with confirmation
            if 'confirm_delete_exports' not in st.session_state:
                st.session_state.confirm_delete_exports = False
            
            if not st.session_state.confirm_delete_exports:
                if st.button("Delete Empty Export Files", width='stretch', type="secondary"):
                    st.session_state.confirm_delete_exports = True
                    st.rerun()
            else:
                st.warning(f"⚠️ **Confirm Deletion**")
                st.write(f"This will delete {len(files_to_delete)} export file(s) and their corresponding CSV files.")
                st.write("**Files to be deleted:**")
                for file_info in files_to_delete:
                    st.write(f"- `{file_info['filename']}`")
                    if file_info['csv_path']:
                        csv_filename = Path(file_info['csv_path']).name
                        st.write(f"  - `{csv_filename}`")
                
                col1, col2 = st.columns(2)
                with col1:
                    if st.button("Confirm Delete", width='stretch', type="primary"):
                        deleted, errors = delete_export_files(files_to_delete)
                        if errors:
                            for error in errors:
                                st.error(error)
                        if deleted:
                            st.success(f"✅ Deleted {len(deleted)} file(s)")
                            st.session_state.confirm_delete_exports = False
                            time.sleep(1)
                            st.rerun()
                with col2:
                    if st.button("Cancel", width='stretch', type="secondary"):
                        st.session_state.confirm_delete_exports = False
                        st.rerun()
        else:
            st.success("✅ No export files eligible for deletion")
            st.caption("All export files either have connections or are part of active sessions")
        
        st.divider()
        
        # Checkpoint Management
        st.subheader("Checkpoint Management")
        st.markdown("Delete all but the most recent checkpoint for each session")
        
        def get_checkpoints_to_delete():
            """Get list of checkpoints that can be deleted (all but most recent for each session)"""
            try:
                # Get all checkpoints
                checkpoints = get_checkpoints()
                if not checkpoints:
                    return []
                
                # Group checkpoints by session_id
                checkpoints_by_session = {}
                for cp in checkpoints:
                    session_id = cp['session_id']
                    if session_id not in checkpoints_by_session:
                        checkpoints_by_session[session_id] = []
                    checkpoints_by_session[session_id].append(cp)
                
                # For each session, keep only the most recent (first in sorted list)
                # and mark the rest for deletion
                checkpoints_to_delete = []
                for session_id, session_checkpoints in checkpoints_by_session.items():
                    # Sort by timestamp, most recent first
                    session_checkpoints.sort(key=lambda x: x['timestamp'], reverse=True)
                    
                    # Keep the first one (most recent), mark the rest for deletion
                    if len(session_checkpoints) > 1:
                        for checkpoint in session_checkpoints[1:]:
                            checkpoints_to_delete.append({
                                'session_id': checkpoint['session_id'],
                                'checkpoint_id': checkpoint['checkpoint_id'],
                                'timestamp': checkpoint['timestamp']
                            })
                
                return checkpoints_to_delete
            except Exception as e:
                st.error(f"Error getting checkpoints: {e}")
                return []
        
        def cleanup_old_checkpoints():
            """Call API to cleanup old checkpoints"""
            try:
                response = requests.post(f"{API_URL}/checkpoints/cleanup", timeout=API_TIMEOUT)
                if response.status_code == 200:
                    return response.json()
                else:
                    return {'deleted_count': 0, 'errors': [f"API error: {response.status_code}"]}
            except Exception as e:
                return {'deleted_count': 0, 'errors': [f"Error: {e}"]}
        
        # Get checkpoints eligible for deletion
        checkpoints_to_delete = get_checkpoints_to_delete()
        
        if checkpoints_to_delete:
            st.info(f"Found {len(checkpoints_to_delete)} checkpoint(s) eligible for deletion")
            
            # Show list of checkpoints to be deleted
            with st.expander("View checkpoints to be deleted", expanded=False):
                for cp_info in checkpoints_to_delete:
                    st.write(f"- Session: `{cp_info['session_id'][:12]}...` | Checkpoint: `{cp_info['checkpoint_id'][:12]}...` | Timestamp: {cp_info['timestamp']}")
            
            # Delete button with confirmation
            if 'confirm_delete_checkpoints' not in st.session_state:
                st.session_state.confirm_delete_checkpoints = False
            
            if not st.session_state.confirm_delete_checkpoints:
                if st.button("Delete Old Checkpoints", width='stretch', type="secondary"):
                    st.session_state.confirm_delete_checkpoints = True
                    st.rerun()
            else:
                st.warning(f"⚠️ **Confirm Deletion**")
                st.write(f"This will delete {len(checkpoints_to_delete)} checkpoint(s), keeping only the most recent checkpoint for each session.")
                st.write("**Checkpoints to be deleted:**")
                for cp_info in checkpoints_to_delete:
                    st.write(f"- Session: `{cp_info['session_id'][:12]}...` | Checkpoint: `{cp_info['checkpoint_id'][:12]}...`")
                
                col1, col2 = st.columns(2)
                with col1:
                    if st.button("Confirm Delete", width='stretch', type="primary"):
                        result = cleanup_old_checkpoints()
                        if result.get('errors'):
                            for error in result['errors']:
                                st.error(error)
                        if result.get('deleted_count', 0) > 0:
                            st.success(f"✅ Deleted {result['deleted_count']} checkpoint(s)")
                            st.session_state.confirm_delete_checkpoints = False
                            time.sleep(1)
                            st.rerun()
                with col2:
                    if st.button("Cancel", width='stretch', type="secondary"):
                        st.session_state.confirm_delete_checkpoints = False
                        st.rerun()
        else:
            st.success("✅ No checkpoints eligible for deletion")
            st.caption("Each session has only one checkpoint (or no checkpoints)")
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