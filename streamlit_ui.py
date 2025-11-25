# -*- coding: utf-8 -*-
import streamlit as st
import requests
import pandas as pd
import pickle
from pathlib import Path
from datetime import datetime
import time

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
    
    if st.button("Refresh Now", use_container_width=True):
        st.rerun()
    
    st.divider()
    st.info(f"API Timeout: {API_TIMEOUT}s\nRefresh: Every 60s (if enabled)")
    
    with st.expander("Debug Info"):
        st.write(f"API URL: {API_URL}")
        
        if st.button("Test API", use_container_width=True):
            try:
                response = requests.get(f"{API_URL}/sessions", timeout=5)
                if response.status_code == 200:
                    st.success("API OK")
                else:
                    st.error(f"Status {response.status_code}")
            except Exception as e:
                st.error(f"Error: {e}")

# Main tabs
tab1, tab2, tab3 = st.tabs(["Active Sessions", "New Trace", "Checkpoints"])

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
                            if st.button("Stop", key=f"cancel_{session_id}", use_container_width=True, type="secondary"):
                                if cancel_session(session_id):
                                    st.rerun()
                    
                    with col2:
                        if status == 'completed':
                            if st.button("Results", key=f"results_{session_id}", use_container_width=True, type="secondary"):
                                try:
                                    results = requests.get(f"{API_URL}/results/{session_id}", timeout=API_TIMEOUT).json()
                                    st.json(results)
                                except Exception as e:
                                    st.error(f"Error: {e}")
                    
                    with col3:
                        if status in ['completed', 'cancelled', 'failed']:
                            if st.button("Delete", key=f"delete_{session_id}", use_container_width=True, type="secondary"):
                                if delete_session(session_id):
                                    st.rerun()
                    
                    st.divider()
                    
                    checkpoint_id = details.get('checkpoint_id')
                    if checkpoint_id:
                        col1, col2 = st.columns([3, 1])
                        with col1:
                            st.success(f"Checkpoint: {checkpoint_id[:16]}...")
                        with col2:
                            if st.button("Delete Checkpoint", key=f"delete_checkpoint_{session_id}", use_container_width=True, type="secondary"):
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
            if st.button("Start Trace", use_container_width=True, type="primary"):
                with st.spinner("Starting..."):
                    start_block_param = start_block if start_block > 0 else None
                    end_block_param = end_block if end_block < 999999999 else None
                    result = start_new_trace(list_a, list_b, max_depth, start_block_param, end_block_param)
                    if result:
                        st.success(f"Started! Session: {result['session_id'][:8]}...")
                        time.sleep(1)
                        st.rerun()
        
        with col2:
            if st.button("Clear", use_container_width=True, type="secondary"):
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
        
        if st.button("Resume Latest", use_container_width=True, type="primary"):
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
                                if st.button("View Path", key=button_key, use_container_width=True):
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
                                    st.caption(f"... and {len(list_a) - 10} more")
                            else:
                                st.info("No addresses")
                        
                        with col2:
                            list_b = request_data.get('list_b', [])
                            st.write(f"**List B ({len(list_b)} addresses)**")
                            if list_b:
                                for addr in list_b[:10]:  # Show first 10
                                    st.code(addr)
                                if len(list_b) > 10:
                                    st.caption(f"... and {len(list_b) - 10} more")
                            else:
                                st.info("No addresses")
                        
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
                col1, col2 = st.columns([3, 1])
                with col1:
                    if st.button("Resume from this Checkpoint", key=f"resume_cp_{idx}_{cp['checkpoint_id']}", use_container_width=True, type="primary"):
                        with st.spinner("Resuming..."):
                            result = resume_from_checkpoint(cp['session_id'], cp['checkpoint_id'])
                            if result:
                                time.sleep(1)
                                st.rerun()
                with col2:
                    if st.button("🗑️ Delete", key=f"delete_cp_{idx}_{cp['checkpoint_id']}", use_container_width=True, type="secondary"):
                        if delete_checkpoint(cp['session_id'], cp['checkpoint_id']):
                            st.rerun()
            
            if idx < len(checkpoints[:20]) - 1:
                st.divider()

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