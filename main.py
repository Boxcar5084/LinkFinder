# -*- coding: utf-8 -*-
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from typing import List, Optional, Dict, Any, Tuple
from contextlib import asynccontextmanager
import uuid
import asyncio
import sqlite3
from datetime import datetime
from api_provider import get_provider, APIProvider
from graph_engine import BitcoinAddressLinker
from cache_manager import TransactionCache
from checkpoint_manager import CheckpointManager
from export_manager import ExportManager
from config import DEFAULT_API, MEMPOOL_API_KEY
from pathlib import Path


async def determine_block_range(
    api: APIProvider,
    list_a: List[str],
    list_b: List[str]
) -> Tuple[Optional[int], Optional[int]]:
    """
    Determine optimal block range by querying addresses.
    
    - Queries all addresses in list_a to find the EARLIEST block (minimum across all)
    - Queries all addresses in list_b to find the LATEST block (maximum across all)
    
    Args:
        api: The API provider to use for queries
        list_a: Source addresses (used to find earliest block)
        list_b: Target addresses (used to find latest block)
    
    Returns:
        Tuple of (earliest_block, latest_block) or (None, None) if no valid blocks found
    """
    print(f"[BLOCK_RANGE] Detecting optimal block range...")
    print(f"[BLOCK_RANGE] Querying {len(list_a)} addresses from list_a for earliest block...")
    
    # Find earliest block from list_a
    earliest_blocks = []
    for address in list_a:
        try:
            block_range = await api.get_address_block_range(address)
            if block_range:
                earliest, _ = block_range
                earliest_blocks.append(earliest)
                print(f"[BLOCK_RANGE]   {address[:16]}...: earliest = {earliest}")
        except Exception as e:
            print(f"[BLOCK_RANGE]   {address[:16]}...: ERROR - {str(e)[:50]}")
            continue
    
    print(f"[BLOCK_RANGE] Querying {len(list_b)} addresses from list_b for latest block...")
    
    # Find latest block from list_b
    latest_blocks = []
    for address in list_b:
        try:
            block_range = await api.get_address_block_range(address)
            if block_range:
                _, latest = block_range
                latest_blocks.append(latest)
                print(f"[BLOCK_RANGE]   {address[:16]}...: latest = {latest}")
        except Exception as e:
            print(f"[BLOCK_RANGE]   {address[:16]}...: ERROR - {str(e)[:50]}")
            continue
    
    # Calculate results
    detected_earliest = min(earliest_blocks) if earliest_blocks else None
    detected_latest = max(latest_blocks) if latest_blocks else None
    
    if detected_earliest is not None and detected_latest is not None:
        print(f"[BLOCK_RANGE] Detected range: {detected_earliest} - {detected_latest}")
    elif detected_earliest is not None:
        print(f"[BLOCK_RANGE] Detected earliest block: {detected_earliest} (no latest found)")
    elif detected_latest is not None:
        print(f"[BLOCK_RANGE] Detected latest block: {detected_latest} (no earliest found)")
    else:
        print(f"[BLOCK_RANGE] Could not detect block range from addresses")
    
    return (detected_earliest, detected_latest)


# Global state
print("[MAIN] Initializing global services...")
cache_manager = TransactionCache()
print(f"[MAIN] Cache manager created: {cache_manager}")
checkpoint_manager = CheckpointManager()
export_manager = ExportManager()
sessions = {}  # session_id -> {status, task, results, checkpoint_id, ...}
print("[MAIN] Global services initialized")

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    yield
    # Shutdown
    cache_manager.close()
    # Cancel all running tasks and save checkpoints
    for session_id, session in sessions.items():
        if session['status'] == 'running' and session.get('task'):
            session['task'].cancel()

app = FastAPI(title="Bitcoin Address Linker", lifespan=lifespan)

class TraceRequest(BaseModel):
    list_a: List[str]
    list_b: List[str]
    max_depth: int = 5
    start_block: Optional[int] = None
    end_block: Optional[int] = None

@app.post("/trace")
async def start_trace(request: TraceRequest):
    """Start new address linking session"""
    if not request.list_a or not request.list_b:
        raise HTTPException(status_code=400, detail="Both lists required")

    session_id = str(uuid.uuid4())

    # Create and store the task with metadata
    task = asyncio.create_task(
        _run_trace_task(session_id, request)
    )

    sessions[session_id] = {
        'status': 'running',
        'progress': 0,
        'task': task,
        'started_at': datetime.now().isoformat(),
        'request': {
            'list_a': request.list_a,
            'list_b': request.list_b,
            'max_depth': request.max_depth,
            'start_block': request.start_block,
            'end_block': request.end_block
        },
        'checkpoint_id': None,
        'trace_state': {
            'visited_forward': {},  # Dict: address -> path
            'visited_backward': {},  # Dict: address -> path
            'visited': set(),
            'connections_found': []
        },
        'last_checkpoint_time': datetime.now()
    }

    return {'session_id': session_id, 'status': 'started'}

async def _run_trace_task(session_id: str, request: TraceRequest):
    """Background tracing task with checkpoint support"""
    checkpoint_task = None
    try:
        # FIX #1: Set status to 'running' IMMEDIATELY
        sessions[session_id]['status'] = 'running'
        
        api = get_provider(DEFAULT_API)
        
        # Open connection at the start of search
        if hasattr(api, 'open'):
            await api.open()

        # AUTO-DETECT BLOCK RANGE
        # Query list_a for earliest block, list_b for latest block
        detected_earliest, detected_latest = await determine_block_range(
            api, request.list_a, request.list_b
        )
        
        # Apply detected range as bounds (user values must be within range)
        effective_start_block = request.start_block
        effective_end_block = request.end_block
        
        if detected_earliest is not None:
            if effective_start_block is None or effective_start_block < detected_earliest:
                if effective_start_block is not None:
                    print(f"[BLOCK_RANGE] User start_block ({effective_start_block}) is before earliest activity ({detected_earliest})")
                effective_start_block = detected_earliest
        
        if detected_latest is not None:
            if effective_end_block is None or effective_end_block > detected_latest:
                if effective_end_block is not None:
                    print(f"[BLOCK_RANGE] User end_block ({effective_end_block}) is after latest activity ({detected_latest})")
                effective_end_block = detected_latest
        
        # Log final block range
        print(f"[BLOCK_RANGE] Final block range: {effective_start_block} - {effective_end_block}")
        
        # Store detected and effective block range in session metadata
        sessions[session_id]['block_range'] = {
            'detected_earliest': detected_earliest,
            'detected_latest': detected_latest,
            'user_start_block': request.start_block,
            'user_end_block': request.end_block,
            'effective_start_block': effective_start_block,
            'effective_end_block': effective_end_block
        }

        # Create wrapper linker that updates trace state for checkpointing
        checkpoint_state = sessions[session_id].get('checkpoint_state')
        print(f"[MAIN] Creating linker with cache_manager: {cache_manager}")
        linker = BitcoinAddressLinkerWithCheckpoint(
            api,
            cache_manager,
            session_id,
            sessions,
            checkpoint_state=checkpoint_state,
            export_manager=export_manager
        )
        print(f"[MAIN] Linker created, cache in linker: {linker.linker.cache}")

        # Initialize incremental exports
        csv_path, json_path = export_manager.initialize_incremental_export(session_id)
        sessions[session_id]['exports'] = {'csv': csv_path, 'json': json_path}

        # If resuming from checkpoint, restore existing connections to export files
        # checkpoint_state is retrieved above (line 94)
        if checkpoint_state:
            existing_connections = checkpoint_state.get('connections_found', [])
            if existing_connections:
                print(f"[RESUME] Restoring {len(existing_connections)} connection(s) to export files...")
                # Get progress info from session's trace_state if available
                progress_info = sessions[session_id].get('progress', {})
                addresses_examined = progress_info.get('addresses_examined', 0)
                search_depth = checkpoint_state.get('search_depth', 0)
                
                for conn in existing_connections:
                    # Restore each connection to export files
                    export_manager.append_connection(
                        session_id,
                        conn,
                        addresses_examined,
                        search_depth,
                        None,  # block_range not stored in checkpoint
                        'resumed'
                    )

        # Create connection callback for incremental exports and checkpoint updates
        def connection_callback(connection, total_addresses, search_depth, block_range, status):
            # Save to export files immediately
            export_manager.append_connection(
                session_id,
                connection,
                total_addresses,
                search_depth,
                block_range,
                status
            )
            
            # Update trace_state immediately so checkpoint includes this connection
            if session_id in sessions and 'trace_state' in sessions[session_id]:
                if 'connections_found' not in sessions[session_id]['trace_state']:
                    sessions[session_id]['trace_state']['connections_found'] = []
                
                # Check for duplicates before adding
                connection_key = (connection.get('source'), connection.get('target'))
                existing_connections = sessions[session_id]['trace_state']['connections_found']
                existing_keys = {(c.get('source'), c.get('target')) for c in existing_connections}
                
                if connection_key not in existing_keys:
                    sessions[session_id]['trace_state']['connections_found'].append(connection)
                    print(f"  [CHECKPOINT] Connection added to trace_state: {connection_key[0][:12]}... -> {connection_key[1][:12]}...")

        # NEW: Start periodic checkpoint task
        checkpoint_task = asyncio.create_task(
            _periodic_checkpoint_task(session_id)
        )

        results = await linker.find_connection(
            request.list_a, request.list_b,
            request.max_depth,
            effective_start_block,
            effective_end_block,
            connection_callback=connection_callback
        )

        # Finalize incremental exports
        csv_path, json_path = export_manager.finalize_incremental_export(session_id, results)

        # FIX #2: Update all session fields atomically
        sessions[session_id].update({
            'status': 'completed',
            'results': results,
            'exports': {'csv': csv_path, 'json': json_path},
            'completed_at': datetime.now().isoformat(),
            'task': None  # Clear task reference
        })

        await api.close()

    except asyncio.CancelledError:
        """Graceful cancellation with checkpoint"""
        print(f"[||] Session {session_id} cancellation detected")
        
        # Cancel periodic checkpoint task if running
        if checkpoint_task:
            checkpoint_task.cancel()
        
        # Save current trace state as checkpoint
        trace_state = sessions[session_id].get('trace_state', {})
        
        # Explicitly extract all fields to ensure complete state saving
        visited_forward = trace_state.get('visited_forward', {})
        visited_backward = trace_state.get('visited_backward', {})
        visited = trace_state.get('visited', set())
        queued_forward = trace_state.get('queued_forward', [])
        queued_backward = trace_state.get('queued_backward', [])
        connections_found = trace_state.get('connections_found', [])
        search_depth = trace_state.get('search_depth', 0)
        status = trace_state.get('status', 'cancelled')
        
        checkpoint_data = {
            'session_id': session_id,
            'request': sessions[session_id].get('request'),
            'block_range': sessions[session_id].get('block_range'),  # Save effective block range
            'trace_state': {
                'visited_forward': visited_forward,
                'visited_backward': visited_backward,
                'visited': list(visited) if isinstance(visited, set) else visited,  # Convert set to list for saving
                'queued_forward': queued_forward,
                'queued_backward': queued_backward,
                'connections_found': connections_found,  # CRITICAL: Ensure connections_found is saved
                'search_depth': search_depth,
                'status': status
            },
            'cancelled_at': datetime.now().isoformat(),
            'progress': {
                'addresses_examined': len(visited) if isinstance(visited, set) else len(visited) if isinstance(visited, list) else 0,
                'visited_forward': len(visited_forward),
                'visited_backward': len(visited_backward),
                'connections_found': len(connections_found),  # Add connections_found count to progress
            }
        }

        checkpoint_id = checkpoint_manager.create_checkpoint(session_id, checkpoint_data)

        # FIX #3: Update session status BEFORE returning from exception handler
        sessions[session_id].update({
            'status': 'cancelled',
            'message': 'Trace was cancelled by user',
            'cancelled_at': datetime.now().isoformat(),
            'checkpoint_id': checkpoint_id,
            'checkpoint_message': f'Checkpoint {checkpoint_id} saved. Resume with: /resume/{session_id}/{checkpoint_id}',
            'progress': checkpoint_data['progress'],
            'task': None  # Clear task reference
        })

        print(f"[SAVE] Checkpoint saved on cancel: {checkpoint_id}")
        print(f" Addresses examined: {checkpoint_data['progress']['addresses_examined']}")
        
        # Close connection on cancellation
        try:
            if 'api' in locals():
                await api.close()
        except Exception as close_err:
            print(f"[WARN] Error closing connection on cancel: {close_err}")

    except Exception as e:
        print(f"[ERR] Session {session_id} failed: {e}")
        
        # Cancel periodic checkpoint task
        if checkpoint_task:
            checkpoint_task.cancel()
        
        # FIX #4: Set failed status atomically
        sessions[session_id].update({
            'status': 'failed',
            'error': str(e),
            'failed_at': datetime.now().isoformat(),
            'task': None  # Clear task reference
        })
        
        # Close connection on error
        try:
            if 'api' in locals():
                await api.close()
        except Exception as close_err:
            print(f"[WARN] Error closing connection on error: {close_err}")

# CORRECTED _periodic_checkpoint_task function for main.py

async def _periodic_checkpoint_task(session_id: str):
    """Create checkpoints every 5 minutes while trace is running"""
    CHECKPOINT_INTERVAL = 300  # 5 minutes in seconds
    
    while True:
        try:
            await asyncio.sleep(CHECKPOINT_INTERVAL)
            
            # Only checkpoint if still running
            if sessions.get(session_id, {}).get('status') != 'running':
                break
            
            # Get current trace state from session
            trace_state = sessions[session_id].get('trace_state', {})
            
            # Explicitly extract all fields to ensure complete state saving
            visited_forward = trace_state.get('visited_forward', {})
            visited_backward = trace_state.get('visited_backward', {})
            visited = trace_state.get('visited', set())
            queued_forward = trace_state.get('queued_forward', [])
            queued_backward = trace_state.get('queued_backward', [])
            connections_found = trace_state.get('connections_found', [])
            search_depth = trace_state.get('search_depth', 0)
            status = trace_state.get('status', 'searching')
            
            # Build checkpoint data with all required fields
            checkpoint_data = {
                'session_id': session_id,
                'request': sessions[session_id].get('request'),
                'block_range': sessions[session_id].get('block_range'),  # Save effective block range
                'trace_state': {
                    'visited_forward': visited_forward,  # Dict is already serializable
                    'visited_backward': visited_backward,  # Dict is already serializable
                    'visited': list(visited) if isinstance(visited, set) else visited,  # Convert set to list for saving
                    'queued_forward': queued_forward,
                    'queued_backward': queued_backward,
                    'connections_found': connections_found,  # CRITICAL: Ensure connections_found is saved
                    'search_depth': search_depth,
                    'status': status
                },
                'periodic_checkpoint': True,
                'checkpoint_time': datetime.now().isoformat(),
                'progress': {
                    'addresses_examined': len(visited) if isinstance(visited, set) else len(visited) if isinstance(visited, list) else 0,
                    'visited_forward': len(visited_forward),
                    'visited_backward': len(visited_backward),
                    'connections_found': len(connections_found),  # Add connections_found count to progress
                }
            }
            
            # Save checkpoint
            checkpoint_id = checkpoint_manager.create_checkpoint(session_id, checkpoint_data)
            sessions[session_id]['last_checkpoint_time'] = datetime.now()
            
            print(f"[SAVE] Periodic checkpoint created: {checkpoint_id}")
            print(f" Progress: {checkpoint_data['progress']}")
            
        except asyncio.CancelledError:
            break
        except Exception as e:
            print(f"[ERR] Error in periodic checkpoint: {e}")
            continue

# CORRECTED BitcoinAddressLinkerWithCheckpoint class for main.py

class BitcoinAddressLinkerWithCheckpoint:
    """Extended linker that updates session state for checkpointing AND loads from checkpoint"""

    def __init__(self, api, cache_manager, session_id, sessions_dict, checkpoint_state=None, export_manager=None):
        from graph_engine import BitcoinAddressLinker
        self.linker = BitcoinAddressLinker(api, cache_manager)
        self.session_id = session_id
        self.sessions = sessions_dict
        self.export_manager = export_manager  # Use the global export_manager instance
        
        # Load checkpoint state if resuming
        self.checkpoint_state = checkpoint_state or {}

    async def find_connection(self, list_a, list_b, max_depth, start_block, end_block, 
                             connection_callback=None):
        """Find connections while updating trace state and loading from checkpoint"""
        
        if self.checkpoint_state:
            # RESUMING FROM CHECKPOINT
            print(f"\n[RESUME] Resuming from checkpoint...")
            trace_state = self.checkpoint_state.copy()
            
            # Restore visited DICTIONARIES from checkpoint (not just sets)
            # Handle both dict and list formats (for backward compatibility)
            visited_forward_raw = trace_state.get('visited_forward', {})
            visited_backward_raw = trace_state.get('visited_backward', {})
            visited_raw = trace_state.get('visited', set())
            
            # Convert to proper types if needed
            if isinstance(visited_forward_raw, list):
                # Old format: list of addresses -> convert to dict with paths
                visited_forward = {addr: [addr] for addr in visited_forward_raw}
            elif isinstance(visited_forward_raw, dict):
                visited_forward = visited_forward_raw
            else:
                visited_forward = {}
            
            if isinstance(visited_backward_raw, list):
                # Old format: list of addresses -> convert to dict with paths
                visited_backward = {addr: [addr] for addr in visited_backward_raw}
            elif isinstance(visited_backward_raw, dict):
                visited_backward = visited_backward_raw
            else:
                visited_backward = {}
            
            if isinstance(visited_raw, list):
                visited = set(visited_raw)
            elif isinstance(visited_raw, set):
                visited = visited_raw
            else:
                visited = set()
            
            queued_forward = trace_state.get('queued_forward', [])  # GET QUEUED
            queued_backward = trace_state.get('queued_backward', [])  # GET QUEUED
            connections_found = trace_state.get('connections_found', [])  # GET EXISTING CONNECTIONS
            
            print(f" Previously visited (forward): {len(visited_forward)} addresses")
            print(f" Previously visited (backward): {len(visited_backward)} addresses")
            print(f" Total visited: {len(visited)} addresses")
            print(f" Existing connections: {len(connections_found)} connections")
            print(f" Continuing trace...\n")
            
            # CRITICAL FIX: Pass queued addresses and existing connections to linker for proper resumption
            result = await self.linker.find_connection_with_visited_state(
                list_a, 
                list_b, 
                max_depth, 
                start_block, 
                end_block,
                visited_forward=visited_forward,
                visited_backward=visited_backward,
                queued_forward=queued_forward,     # PASS QUEUED FORWARD
                queued_backward=queued_backward,   # PASS QUEUED BACKWARD
                connections_found=connections_found,  # PASS EXISTING CONNECTIONS
                progress_callback=self._progress_callback,
                connection_callback=connection_callback
            )
        else:
            # FRESH TRACE - call find_connection FIRST
            result = await self.linker.find_connection(
                list_a, list_b, max_depth, start_block, end_block,
                progress_callback=self._progress_callback,
                connection_callback=connection_callback
            )

        # AFTER getting result, extract visited state for checkpoint
        trace_state = {
            'visited_forward': result.get('visited_forward', {}),
            'visited_backward': result.get('visited_backward', {}),
            'visited': result.get('visited', set()),
            'queued_forward': result.get('queued_forward', []),  # SAVE QUEUED
            'queued_backward': result.get('queued_backward', []),  # SAVE QUEUED
            'connections_found': result.get('connections_found', []),
            'search_depth': result.get('search_depth', max_depth),
            'status': result.get('status', 'searching')
        }
        
        # Update session with full trace state
        self.sessions[self.session_id]['trace_state'] = trace_state
        
        # Also update progress for periodic checkpoint
        self.sessions[self.session_id]['progress'] = {
            'addresses_examined': result.get('total_addresses_examined', 0),
            'visited_forward': len(trace_state.get('visited_forward', {})),
            'visited_backward': len(trace_state.get('visited_backward', {})),
            'connections_found': len(trace_state.get('connections_found', []))  # Add connections_found count
        }

        return result

    def _progress_callback(self, progress):
        """Update trace_state as progress is reported with full state from graph_engine"""
        session = self.sessions.get(self.session_id)
        if not session or 'trace_state' not in session:
            return
        
        current = progress.get('current', '')
        
        # Ensure trace_state has all required fields initialized
        if 'visited' not in session['trace_state']:
            session['trace_state']['visited'] = set()
        if 'visited_forward' not in session['trace_state']:
            session['trace_state']['visited_forward'] = {}
        if 'visited_backward' not in session['trace_state']:
            session['trace_state']['visited_backward'] = {}
        if 'queued_forward' not in session['trace_state']:
            session['trace_state']['queued_forward'] = []
        if 'queued_backward' not in session['trace_state']:
            session['trace_state']['queued_backward'] = []
        if 'connections_found' not in session['trace_state']:
            session['trace_state']['connections_found'] = []
        if 'search_depth' not in session['trace_state']:
            session['trace_state']['search_depth'] = 0
        
        # DEFENSIVE FIX: Convert visited from list to set if needed (checkpoint resume issue)
        if isinstance(session['trace_state']['visited'], list):
            session['trace_state']['visited'] = set(session['trace_state']['visited'])
        
        # Add current address to visited set
        session['trace_state']['visited'].add(current)
        
        # Update full state from progress data (passed from graph_engine)
        # These fields contain the complete current state for checkpoint saving
        if 'visited_forward' in progress:
            session['trace_state']['visited_forward'] = progress['visited_forward']
        if 'visited_backward' in progress:
            session['trace_state']['visited_backward'] = progress['visited_backward']
        if 'queued_forward' in progress:
            session['trace_state']['queued_forward'] = progress['queued_forward']
        if 'queued_backward' in progress:
            session['trace_state']['queued_backward'] = progress['queued_backward']
        if 'connections_found' in progress:
            session['trace_state']['connections_found'] = progress['connections_found']
        if 'search_depth' in progress:
            session['trace_state']['search_depth'] = progress['search_depth']




@app.get("/status/{session_id}")
async def get_status(session_id: str):
    """Check session status"""
    if session_id not in sessions:
        raise HTTPException(status_code=404, detail="Session not found")

    session = sessions[session_id]

    # Don't return the task object in response
    response = {k: v for k, v in session.items() if k != 'task' and k != 'checkpoint_state'}

    return response


@app.get("/results/{session_id}")
async def get_results(session_id: str):
    """Get completed results"""
    if session_id not in sessions:
        raise HTTPException(status_code=404, detail="Session not found")

    session = sessions[session_id]

    if session['status'] != 'completed':
        raise HTTPException(status_code=400, detail="Session not completed")

    return session['results']


def _normalize_trace_state_from_checkpoint(trace_state: Dict[str, Any]) -> Dict[str, Any]:
    """
    Normalize trace_state loaded from checkpoint to ensure proper data types.
    Converts visited from list to set and ensures all required fields exist.
    """
    normalized = trace_state.copy() if trace_state else {}
    
    # Ensure visited is a set (convert from list if needed)
    visited_raw = normalized.get('visited', set())
    if isinstance(visited_raw, list):
        normalized['visited'] = set(visited_raw)
    elif isinstance(visited_raw, set):
        normalized['visited'] = visited_raw
    else:
        normalized['visited'] = set()
    
    # Ensure visited_forward is a dict
    visited_forward_raw = normalized.get('visited_forward', {})
    if isinstance(visited_forward_raw, list):
        normalized['visited_forward'] = {addr: [addr] for addr in visited_forward_raw}
    elif not isinstance(visited_forward_raw, dict):
        normalized['visited_forward'] = {}
    
    # Ensure visited_backward is a dict
    visited_backward_raw = normalized.get('visited_backward', {})
    if isinstance(visited_backward_raw, list):
        normalized['visited_backward'] = {addr: [addr] for addr in visited_backward_raw}
    elif not isinstance(visited_backward_raw, dict):
        normalized['visited_backward'] = {}
    
    # Ensure queued_forward is a list
    if 'queued_forward' not in normalized:
        normalized['queued_forward'] = []
    elif not isinstance(normalized['queued_forward'], list):
        normalized['queued_forward'] = []
    
    # Ensure queued_backward is a list
    if 'queued_backward' not in normalized:
        normalized['queued_backward'] = []
    elif not isinstance(normalized['queued_backward'], list):
        normalized['queued_backward'] = []
    
    # Ensure connections_found is a list
    if 'connections_found' not in normalized:
        normalized['connections_found'] = []
    elif not isinstance(normalized['connections_found'], list):
        normalized['connections_found'] = []
    
    # Ensure search_depth exists
    if 'search_depth' not in normalized:
        normalized['search_depth'] = 0
    
    # Ensure status exists
    if 'status' not in normalized:
        normalized['status'] = 'searching'
    
    return normalized


@app.post("/cancel/{session_id}")
async def cancel_trace(session_id: str):
    """Cancel an in-progress trace (checkpoint will be saved automatically)"""
    if session_id not in sessions:
        raise HTTPException(status_code=404, detail="Session not found")

    session = sessions[session_id]

    # FIX #5: Better status validation
    if session['status'] not in ['running', 'started']:
        return {
            'session_id': session_id,
            'message': f"Cannot cancel session with status: {session['status']}"
        }

    # Cancel the asyncio task (checkpoint will be saved in except block)
    if session.get('task'):
        session['task'].cancel()
        return {
            'session_id': session_id,
            'status': 'cancellation_requested',
            'message': 'Trace cancellation requested. Checkpoint will be saved...'
        }

    return {
        'session_id': session_id,
        'message': 'No active task found'
    }


@app.post("/checkpoint/{session_id}/force")
async def force_checkpoint(session_id: str):
    """Force create a checkpoint for a running session"""
    if session_id not in sessions:
        raise HTTPException(status_code=404, detail="Session not found")

    session = sessions[session_id]

    # Only allow checkpointing for running sessions
    if session['status'] != 'running':
        return {
            'session_id': session_id,
            'message': f"Cannot create checkpoint for session with status: {session['status']}"
        }

    # Get current trace state from session
    trace_state = session.get('trace_state', {})
    
    # Explicitly extract all fields to ensure complete state saving
    visited_forward = trace_state.get('visited_forward', {})
    visited_backward = trace_state.get('visited_backward', {})
    visited = trace_state.get('visited', set())
    queued_forward = trace_state.get('queued_forward', [])
    queued_backward = trace_state.get('queued_backward', [])
    connections_found = trace_state.get('connections_found', [])
    search_depth = trace_state.get('search_depth', 0)
    status = trace_state.get('status', 'searching')
    
    # Build checkpoint data with all required fields
    checkpoint_data = {
        'session_id': session_id,
        'request': session.get('request'),
        'block_range': session.get('block_range'),  # Save effective block range
        'trace_state': {
            'visited_forward': visited_forward,
            'visited_backward': visited_backward,
            'visited': list(visited) if isinstance(visited, set) else visited,
            'queued_forward': queued_forward,
            'queued_backward': queued_backward,
            'connections_found': connections_found,
            'search_depth': search_depth,
            'status': status
        },
        'periodic_checkpoint': False,  # Mark as manual checkpoint
        'checkpoint_time': datetime.now().isoformat(),
        'progress': {
            'addresses_examined': len(visited) if isinstance(visited, set) else len(visited) if isinstance(visited, list) else 0,
            'visited_forward': len(visited_forward),
            'visited_backward': len(visited_backward),
            'connections_found': len(connections_found),
        }
    }
    
    # Save checkpoint
    checkpoint_id = checkpoint_manager.create_checkpoint(session_id, checkpoint_data)
    session['last_checkpoint_time'] = datetime.now()
    
    return {
        'session_id': session_id,
        'checkpoint_id': checkpoint_id,
        'message': 'Checkpoint created successfully',
        'progress': checkpoint_data['progress']
    }


@app.post("/resume/{session_id}/{checkpoint_id}")
async def resume_trace(session_id: str, checkpoint_id: str):
    """Resume a cancelled trace from checkpoint"""
    # Load checkpoint
    checkpoint = checkpoint_manager.load_checkpoint(session_id, checkpoint_id)

    if not checkpoint:
        raise HTTPException(status_code=404, detail="Checkpoint not found")

    checkpoint_data = checkpoint['state']
    request_data = checkpoint_data.get('request', {})
    progress = checkpoint_data.get('progress', {})

    print(f"\n[>>] Resuming session {session_id} from checkpoint {checkpoint_id}")
    print(f" Previously examined: {progress.get('addresses_examined', 0)} addresses")

    # FIX #6: Create NEW session for resumed trace (old one is historical)
    # This prevents state confusion
    new_session_id = str(uuid.uuid4())
    
    # Reconstruct request
    request = TraceRequest(
        list_a=request_data.get('list_a', []),
        list_b=request_data.get('list_b', []),
        max_depth=request_data.get('max_depth', 5),
        start_block=request_data.get('start_block'),
        end_block=request_data.get('end_block')
    )

    # Create new task with the resumed session ID
    task = asyncio.create_task(
        _run_trace_task(new_session_id, request)
    )

    # CRITICAL FIX: Store checkpoint state so it gets loaded during tracing
    checkpoint_trace_state = checkpoint_data.get('trace_state', {})
    # Normalize trace_state to ensure proper data types (list->set conversion)
    normalized_trace_state = _normalize_trace_state_from_checkpoint(checkpoint_trace_state)
    
    sessions[new_session_id] = {
        'status': 'running',
        'progress': 0,
        'task': task,
        'started_at': datetime.now().isoformat(),
        'request': {
            'list_a': request.list_a,
            'list_b': request.list_b,
            'max_depth': request.max_depth,
            'start_block': request.start_block,
            'end_block': request.end_block
        },
        'block_range': checkpoint_data.get('block_range'),  # Restore effective block range from checkpoint
        'checkpoint_id': checkpoint_id,
        'trace_state': normalized_trace_state,
        'checkpoint_state': normalized_trace_state,  # PASS TO LINKER
        'resumed_from_session': session_id,  # Track origin
        'last_checkpoint_time': datetime.now()
    }

    return {
        'session_id': new_session_id,
        'status': 'started',
        'message': f'Resumed from checkpoint {checkpoint_id}',
        'previous_session_id': session_id
    }


@app.post("/resume/auto")
async def auto_resume():
    """Automatically resume the most recent checkpoint across all sessions."""
    most_recent = checkpoint_manager.get_most_recent_checkpoint()

    if not most_recent:
        raise HTTPException(
            status_code=404,
            detail="No checkpoints found. Start a new trace first."
        )

    session_id, checkpoint_id, checkpoint_data = most_recent
    
    checkpoint_state = checkpoint_data.get('state', {})
    request_data = checkpoint_state.get('request', {})
    progress = checkpoint_state.get('progress', {})
    checkpoint_trace_state = checkpoint_state.get('trace_state', {})

    print(f"\n[>>] Auto-resuming from session {session_id}")
    print(f" Checkpoint: {checkpoint_id}")
    print(f" Previously examined: {progress.get('addresses_examined', 0)} addresses")

    # Reconstruct the request
    request = TraceRequest(
        list_a=request_data.get('list_a', []),
        list_b=request_data.get('list_b', []),
        max_depth=request_data.get('max_depth', 5),
        start_block=request_data.get('start_block'),
        end_block=request_data.get('end_block')
    )

    # Create new session for resumed trace
    new_session_id = str(uuid.uuid4())
    task = asyncio.create_task(_run_trace_task(new_session_id, request))

    # CRITICAL FIX: Store checkpoint state so it gets loaded during tracing
    # Normalize trace_state to ensure proper data types (list->set conversion)
    normalized_trace_state = _normalize_trace_state_from_checkpoint(checkpoint_trace_state)
    
    sessions[new_session_id] = {
        'status': 'running',
        'progress': 0,
        'task': task,
        'started_at': datetime.now().isoformat(),
        'request': {
            'list_a': request.list_a,
            'list_b': request.list_b,
            'max_depth': request.max_depth,
            'start_block': request.start_block,
            'end_block': request.end_block
        },
        'block_range': checkpoint_state.get('block_range'),  # Restore effective block range from checkpoint
        'checkpoint_id': checkpoint_id,
        'trace_state': normalized_trace_state,
        'checkpoint_state': normalized_trace_state,  # PASS TO LINKER
        'resumed_from_session': session_id,
        'auto_resumed': True,
        'last_checkpoint_time': datetime.now()
    }

    return {
        'session_id': new_session_id,
        'status': 'started',
        'message': 'Auto-resumed from most recent checkpoint',
        'previous_session_id': session_id,
        'checkpoint_id': checkpoint_id,
        'progress': progress
    }


@app.post("/resume/session/{session_id}")
async def auto_resume_session(session_id: str):
    """Automatically resume the most recent checkpoint for a specific session."""
    if session_id not in sessions:
        raise HTTPException(status_code=404, detail="Session not found")

    # Get latest checkpoint for this session
    latest = checkpoint_manager.get_latest_checkpoint_for_session(session_id)

    if not latest:
        raise HTTPException(
            status_code=404,
            detail=f"No checkpoints found for session {session_id}"
        )

    checkpoint_id, checkpoint_data = latest
    checkpoint_state = checkpoint_data.get('state', {})
    request_data = checkpoint_state.get('request', {})
    progress = checkpoint_state.get('progress', {})
    checkpoint_trace_state = checkpoint_state.get('trace_state', {})

    print(f"\n[>>] Auto-resuming session {session_id}")
    print(f" Checkpoint: {checkpoint_id}")
    print(f" Previously examined: {progress.get('addresses_examined', 0)} addresses")

    # Reconstruct request
    request = TraceRequest(
        list_a=request_data.get('list_a', []),
        list_b=request_data.get('list_b', []),
        max_depth=request_data.get('max_depth', 5),
        start_block=request_data.get('start_block'),
        end_block=request_data.get('end_block')
    )

    # Create new session for resumed trace
    new_session_id = str(uuid.uuid4())
    task = asyncio.create_task(_run_trace_task(new_session_id, request))

    # CRITICAL FIX: Store checkpoint state so it gets loaded during tracing
    # Normalize trace_state to ensure proper data types (list->set conversion)
    normalized_trace_state = _normalize_trace_state_from_checkpoint(checkpoint_trace_state)
    
    sessions[new_session_id] = {
        'status': 'running',
        'progress': 0,
        'task': task,
        'started_at': datetime.now().isoformat(),
        'request': {
            'list_a': request.list_a,
            'list_b': request.list_b,
            'max_depth': request.max_depth,
            'start_block': request.start_block,
            'end_block': request.end_block
        },
        'block_range': checkpoint_state.get('block_range'),  # Restore effective block range from checkpoint
        'checkpoint_id': checkpoint_id,
        'trace_state': normalized_trace_state,
        'checkpoint_state': normalized_trace_state,  # PASS TO LINKER
        'resumed_from_session': session_id,
        'auto_resumed': True,
        'last_checkpoint_time': datetime.now()
    }

    return {
        'session_id': new_session_id,
        'status': 'started',
        'message': f'Auto-resumed from latest checkpoint',
        'previous_session_id': session_id,
        'checkpoint_id': checkpoint_id,
        'progress': progress
    }


@app.get("/latest-checkpoint")
async def get_latest_checkpoint_info():
    """Get info about the most recent checkpoint without resuming."""
    most_recent = checkpoint_manager.get_most_recent_checkpoint()

    if not most_recent:
        return {
            'message': 'No checkpoints found',
            'checkpoint_found': False
        }

    session_id, checkpoint_id, checkpoint_data = most_recent
    checkpoint_state = checkpoint_data.get('state', {})
    progress = checkpoint_state.get('progress', {})

    return {
        'checkpoint_found': True,
        'session_id': session_id,
        'checkpoint_id': checkpoint_id,
        'timestamp': checkpoint_data.get('timestamp'),
        'cancelled_at': checkpoint_state.get('cancelled_at'),
        'progress': progress,
        'request': checkpoint_state.get('request', {}),
        'can_resume': True,
        'resume_endpoint': '/resume/auto'
    }


@app.get("/checkpoints/all")
async def list_all_checkpoints():
    """List all checkpoints across all sessions, sorted by recency."""
    all_checkpoints = []

    # Get unique sessions from checkpoint files
    checkpoint_files = list(checkpoint_manager.checkpoint_dir.glob("*.pkl"))

    session_ids = set()
    for f in checkpoint_files:
        session_id = f.stem.split('_')[0]
        session_ids.add(session_id)

    # Get checkpoints for each session
    for session_id in sorted(session_ids):
        checkpoints = checkpoint_manager.list_checkpoints(session_id)
        for cp in checkpoints:
            all_checkpoints.append({
                'session_id': session_id,
                'checkpoint_id': cp['checkpoint_id'],
                'timestamp': cp['timestamp'],
                'in_memory': session_id in sessions,
                'session_status': sessions.get(session_id, {}).get('status', 'unknown')
            })

    # Sort all by timestamp, most recent first
    all_checkpoints.sort(key=lambda x: x['timestamp'], reverse=True)

    return {
        'checkpoints': all_checkpoints,
        'count': len(all_checkpoints),
        'most_recent': all_checkpoints[0] if all_checkpoints else None
    }


@app.get("/sessions")
async def list_sessions():
    """List all sessions and their status"""
    sessions_list = []

    for session_id, session in sessions.items():
        response = {
            'session_id': session_id,
            'status': session.get('status'),
            'started_at': session.get('started_at'),
            'checkpoint_id': session.get('checkpoint_id'),
            'last_checkpoint_time': session.get('last_checkpoint_time')
        }

        sessions_list.append(response)

    return {'sessions': sessions_list, 'count': len(sessions_list)}


@app.get("/checkpoint/{session_id}")
async def get_checkpoint_info(session_id: str):
    """Get checkpoint information for a session"""
    if session_id not in sessions:
        raise HTTPException(status_code=404, detail="Session not found")

    session = sessions[session_id]
    checkpoint_id = session.get('checkpoint_id')

    if not checkpoint_id:
        return {
            'session_id': session_id,
            'message': 'No checkpoint available'
        }

    checkpoint = checkpoint_manager.load_checkpoint(session_id, checkpoint_id)

    if not checkpoint:
        raise HTTPException(status_code=404, detail="Checkpoint not found")

    checkpoint_data = checkpoint['state']

    return {
        'session_id': session_id,
        'checkpoint_id': checkpoint_id,
        'status': session.get('status'),
        'progress': checkpoint_data.get('progress', {}),
        'cancelled_at': checkpoint_data.get('cancelled_at'),
        'can_resume': True
    }


@app.get("/checkpoint/{session_id}/{checkpoint_id}")
async def get_checkpoint_details(session_id: str, checkpoint_id: str):
    """Get detailed checkpoint information including request parameters"""
    checkpoint = checkpoint_manager.load_checkpoint(session_id, checkpoint_id)

    if not checkpoint:
        raise HTTPException(status_code=404, detail="Checkpoint not found")

    checkpoint_data = checkpoint['state']
    request_data = checkpoint_data.get('request', {})
    progress = checkpoint_data.get('progress', {})
    trace_state = checkpoint_data.get('trace_state', {})
    block_range = checkpoint_data.get('block_range', {})

    return {
        'session_id': session_id,
        'checkpoint_id': checkpoint_id,
        'timestamp': checkpoint.get('timestamp'),
        'request': request_data,
        'block_range': block_range,  # Include effective block range
        'progress': progress,
        'trace_state': {
            'connections_found_count': len(trace_state.get('connections_found', [])),
            'visited_forward_count': len(trace_state.get('visited_forward', {})),
            'visited_backward_count': len(trace_state.get('visited_backward', {}))
        },
        'cancelled_at': checkpoint_data.get('cancelled_at'),
        'periodic_checkpoint': checkpoint_data.get('periodic_checkpoint', False),
        'can_resume': True
    }


@app.get("/checkpoints/{session_id}")
async def list_checkpoints(session_id: str):
    """List all checkpoints for a session"""
    checkpoints = checkpoint_manager.list_checkpoints(session_id)

    return {
        'session_id': session_id,
        'checkpoints': [
            {
                'checkpoint_id': cp['checkpoint_id'],
                'timestamp': cp['timestamp']
            }
            for cp in checkpoints
        ],
        'count': len(checkpoints)
    }


@app.delete("/checkpoints/{session_id}/{checkpoint_id}")
async def delete_checkpoint(session_id: str, checkpoint_id: str):
    """Delete a specific checkpoint"""
    success = checkpoint_manager.delete_checkpoint(session_id, checkpoint_id)
    
    if not success:
        raise HTTPException(status_code=404, detail="Checkpoint not found")
    
    return {
        'session_id': session_id,
        'checkpoint_id': checkpoint_id,
        'message': 'Checkpoint deleted successfully'
    }


@app.post("/checkpoints/cleanup")
async def cleanup_old_checkpoints():
    """Delete all but the most recent checkpoint for each session"""
    try:
        deleted_count, errors = checkpoint_manager.cleanup_old_checkpoints()
        
        return {
            'deleted_count': deleted_count,
            'errors': errors,
            'message': f'Cleaned up {deleted_count} old checkpoint(s), keeping most recent for each session'
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error cleaning up checkpoints: {str(e)}")


@app.post("/cleanup/{session_id}")
async def cleanup_session(session_id: str):
    """Cleanup a completed or cancelled session"""
    if session_id not in sessions:
        raise HTTPException(status_code=404, detail="Session not found")

    session = sessions[session_id]
    
    if session['status'] not in ['completed', 'cancelled', 'failed']:
        return {
            'session_id': session_id,
            'message': f"Cannot cleanup session with status: {session['status']}. Only completed, cancelled, or failed sessions can be cleaned up."
        }

    # Remove from memory
    del sessions[session_id]
    
    return {
        'session_id': session_id,
        'message': 'Session cleaned up successfully'
    }


@app.delete("/sessions/{session_id}")
async def delete_session(session_id: str):
    """Force delete a session"""
    if session_id not in sessions:
        raise HTTPException(status_code=404, detail="Session not found")

    session = sessions[session_id]
    
    # Cancel task if still running
    if session['status'] == 'running' and session.get('task'):
        session['task'].cancel()
    
    # Remove from memory
    del sessions[session_id]
    
    return {
        'session_id': session_id,
        'message': 'Session deleted successfully'
    }

@app.get("/cache/stats")
async def get_cache_stats():
    """Get cache performance statistics"""
    stats = cache_manager.get_cache_stats()
    return stats

@app.get("/cache/test")
async def test_cache():
    """Test cache functionality - store and retrieve a test entry"""
    test_address = "test_address_12345"
    test_txs = [{"txid": "test1", "value": 100}, {"txid": "test2", "value": 200}]
    
    # Try to get (should be None)
    cached_before = cache_manager.get_cached(test_address)
    
    # Store
    cache_manager.store(test_address, test_txs)
    
    # Try to get again (should return the data)
    cached_after = cache_manager.get_cached(test_address)
    
    # Clean up test entry
    conn = sqlite3.connect(cache_manager.db_path)
    c = conn.cursor()
    c.execute('DELETE FROM cached_transactions WHERE address = ?', (test_address,))
    conn.commit()
    conn.close()
    
    return {
        "test_address": test_address,
        "cached_before_store": cached_before is not None,
        "cached_after_store": cached_after is not None,
        "data_matches": cached_after == test_txs if cached_after else False,
        "cache_working": cached_after == test_txs,
        "stats": cache_manager.get_cache_stats()
    }


# ========== SETTINGS ENDPOINTS ==========

class SettingsUpdate(BaseModel):
    default_api: Optional[str] = None
    mempool_api_key: Optional[str] = None
    electrumx_host: Optional[str] = None
    electrumx_port: Optional[int] = None
    electrumx_use_ssl: Optional[str] = None
    electrumx_cert: Optional[str] = None
    use_cache: Optional[bool] = None
    # Threshold settings
    mixer_input_threshold: Optional[int] = None
    mixer_output_threshold: Optional[int] = None
    suspicious_ratio_threshold: Optional[int] = None
    skip_mixer_input_threshold: Optional[int] = None
    skip_mixer_output_threshold: Optional[int] = None
    skip_distribution_max_inputs: Optional[int] = None
    skip_distribution_min_outputs: Optional[int] = None
    max_transactions_per_address: Optional[int] = None
    max_depth: Optional[int] = None
    exchange_wallet_threshold: Optional[int] = None
    max_input_addresses_per_tx: Optional[int] = None
    max_output_addresses_per_tx: Optional[int] = None


def _read_env_file() -> Dict[str, str]:
    """Read current .env file contents"""
    env_path = Path(".env")
    env_vars = {}
    if env_path.exists():
        with open(env_path, 'r') as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith('#') and '=' in line:
                    key, value = line.split('=', 1)
                    env_vars[key.strip()] = value.strip()
    return env_vars


def _write_env_file(env_vars: Dict[str, str]):
    """Write .env file with updated values"""
    env_path = Path(".env")
    
    # Read existing file to preserve comments and order
    lines = []
    existing_keys = set()
    
    if env_path.exists():
        with open(env_path, 'r') as f:
            for line in f:
                stripped = line.strip()
                if stripped and not stripped.startswith('#') and '=' in stripped:
                    key = stripped.split('=', 1)[0].strip()
                    existing_keys.add(key)
                    if key in env_vars:
                        lines.append(f"{key}={env_vars[key]}\n")
                    else:
                        lines.append(line)
                else:
                    lines.append(line)
    
    # Add any new keys that weren't in the file
    for key, value in env_vars.items():
        if key not in existing_keys:
            lines.append(f"{key}={value}\n")
    
    # Write the file
    with open(env_path, 'w') as f:
        f.writelines(lines)


@app.get("/settings")
async def get_settings():
    """Get current application settings"""
    import os
    
    # Re-read from environment to get current values
    env_vars = _read_env_file()
    
    from config import (
        USE_CACHE,
        MIXER_INPUT_THRESHOLD,
        MIXER_OUTPUT_THRESHOLD,
        SUSPICIOUS_RATIO_THRESHOLD,
        SKIP_MIXER_INPUT_THRESHOLD,
        SKIP_MIXER_OUTPUT_THRESHOLD,
        SKIP_DISTRIBUTION_MAX_INPUTS,
        SKIP_DISTRIBUTION_MIN_OUTPUTS,
        MAX_TRANSACTIONS_PER_ADDRESS,
        MAX_DEPTH,
        EXCHANGE_WALLET_THRESHOLD,
        MAX_INPUT_ADDRESSES_PER_TX,
        MAX_OUTPUT_ADDRESSES_PER_TX
    )
    
    return {
        'default_api': env_vars.get('DEFAULT_API', DEFAULT_API),
        'mempool_api_key': env_vars.get('MEMPOOL_API_KEY', ''),
        'mempool_api_key_set': bool(env_vars.get('MEMPOOL_API_KEY', '')),
        'electrumx_host': env_vars.get('ELECTRUMX_HOST', ''),
        'electrumx_port': env_vars.get('ELECTRUMX_PORT', ''),
        'electrumx_use_ssl': env_vars.get('ELECTRUMX_USE_SSL', ''),
        'electrumx_cert': env_vars.get('ELECTRUMX_CERT', ''),
        'use_cache': USE_CACHE,
        'available_providers': ['mempool', 'blockchain', 'electrumx'],
        # Threshold settings
        'mixer_input_threshold': int(env_vars.get('MIXER_INPUT_THRESHOLD', MIXER_INPUT_THRESHOLD)),
        'mixer_output_threshold': int(env_vars.get('MIXER_OUTPUT_THRESHOLD', MIXER_OUTPUT_THRESHOLD)),
        'suspicious_ratio_threshold': int(env_vars.get('SUSPICIOUS_RATIO_THRESHOLD', SUSPICIOUS_RATIO_THRESHOLD)),
        'skip_mixer_input_threshold': int(env_vars.get('SKIP_MIXER_INPUT_THRESHOLD', SKIP_MIXER_INPUT_THRESHOLD)),
        'skip_mixer_output_threshold': int(env_vars.get('SKIP_MIXER_OUTPUT_THRESHOLD', SKIP_MIXER_OUTPUT_THRESHOLD)),
        'skip_distribution_max_inputs': int(env_vars.get('SKIP_DISTRIBUTION_MAX_INPUTS', SKIP_DISTRIBUTION_MAX_INPUTS)),
        'skip_distribution_min_outputs': int(env_vars.get('SKIP_DISTRIBUTION_MIN_OUTPUTS', SKIP_DISTRIBUTION_MIN_OUTPUTS)),
        'max_transactions_per_address': int(env_vars.get('MAX_TRANSACTIONS_PER_ADDRESS', MAX_TRANSACTIONS_PER_ADDRESS)),
        'max_depth': int(env_vars.get('MAX_DEPTH', MAX_DEPTH)),
        'exchange_wallet_threshold': int(env_vars.get('EXCHANGE_WALLET_THRESHOLD', EXCHANGE_WALLET_THRESHOLD)),
        'max_input_addresses_per_tx': int(env_vars.get('MAX_INPUT_ADDRESSES_PER_TX', MAX_INPUT_ADDRESSES_PER_TX)),
        'max_output_addresses_per_tx': int(env_vars.get('MAX_OUTPUT_ADDRESSES_PER_TX', MAX_OUTPUT_ADDRESSES_PER_TX))
    }


@app.post("/settings")
async def update_settings(settings: SettingsUpdate):
    """Update application settings and persist to .env file"""
    import os
    
    # Read current env vars
    env_vars = _read_env_file()
    
    updated = []
    
    # Update DEFAULT_API if provided
    if settings.default_api is not None:
        valid_providers = ['mempool', 'blockchain', 'electrumx']
        if settings.default_api.lower() not in valid_providers:
            raise HTTPException(
                status_code=400, 
                detail=f"Invalid provider. Must be one of: {', '.join(valid_providers)}"
            )
        env_vars['DEFAULT_API'] = settings.default_api.lower()
        os.environ['DEFAULT_API'] = settings.default_api.lower()
        updated.append('default_api')
    
    # Update MEMPOOL_API_KEY if provided
    if settings.mempool_api_key is not None:
        env_vars['MEMPOOL_API_KEY'] = settings.mempool_api_key
        os.environ['MEMPOOL_API_KEY'] = settings.mempool_api_key
        updated.append('mempool_api_key')
    
    # Update ElectrumX settings if provided
    if settings.electrumx_host is not None:
        env_vars['ELECTRUMX_HOST'] = settings.electrumx_host
        os.environ['ELECTRUMX_HOST'] = settings.electrumx_host
        updated.append('electrumx_host')
    
    if settings.electrumx_port is not None:
        env_vars['ELECTRUMX_PORT'] = str(settings.electrumx_port)
        os.environ['ELECTRUMX_PORT'] = str(settings.electrumx_port)
        updated.append('electrumx_port')
    
    if settings.electrumx_use_ssl is not None:
        env_vars['ELECTRUMX_USE_SSL'] = settings.electrumx_use_ssl.lower()
        os.environ['ELECTRUMX_USE_SSL'] = settings.electrumx_use_ssl.lower()
        updated.append('electrumx_use_ssl')
    
    if settings.electrumx_cert is not None:
        env_vars['ELECTRUMX_CERT'] = settings.electrumx_cert
        os.environ['ELECTRUMX_CERT'] = settings.electrumx_cert
        updated.append('electrumx_cert')
    
    # Update USE_CACHE if provided
    if settings.use_cache is not None:
        env_vars['USE_CACHE'] = 'true' if settings.use_cache else 'false'
        os.environ['USE_CACHE'] = env_vars['USE_CACHE']
        updated.append('use_cache')
    
    # Update threshold settings if provided
    if settings.mixer_input_threshold is not None:
        env_vars['MIXER_INPUT_THRESHOLD'] = str(settings.mixer_input_threshold)
        os.environ['MIXER_INPUT_THRESHOLD'] = str(settings.mixer_input_threshold)
        updated.append('mixer_input_threshold')
    
    if settings.mixer_output_threshold is not None:
        env_vars['MIXER_OUTPUT_THRESHOLD'] = str(settings.mixer_output_threshold)
        os.environ['MIXER_OUTPUT_THRESHOLD'] = str(settings.mixer_output_threshold)
        updated.append('mixer_output_threshold')
    
    if settings.suspicious_ratio_threshold is not None:
        env_vars['SUSPICIOUS_RATIO_THRESHOLD'] = str(settings.suspicious_ratio_threshold)
        os.environ['SUSPICIOUS_RATIO_THRESHOLD'] = str(settings.suspicious_ratio_threshold)
        updated.append('suspicious_ratio_threshold')
    
    if settings.skip_mixer_input_threshold is not None:
        env_vars['SKIP_MIXER_INPUT_THRESHOLD'] = str(settings.skip_mixer_input_threshold)
        os.environ['SKIP_MIXER_INPUT_THRESHOLD'] = str(settings.skip_mixer_input_threshold)
        updated.append('skip_mixer_input_threshold')
    
    if settings.skip_mixer_output_threshold is not None:
        env_vars['SKIP_MIXER_OUTPUT_THRESHOLD'] = str(settings.skip_mixer_output_threshold)
        os.environ['SKIP_MIXER_OUTPUT_THRESHOLD'] = str(settings.skip_mixer_output_threshold)
        updated.append('skip_mixer_output_threshold')
    
    if settings.skip_distribution_max_inputs is not None:
        env_vars['SKIP_DISTRIBUTION_MAX_INPUTS'] = str(settings.skip_distribution_max_inputs)
        os.environ['SKIP_DISTRIBUTION_MAX_INPUTS'] = str(settings.skip_distribution_max_inputs)
        updated.append('skip_distribution_max_inputs')
    
    if settings.skip_distribution_min_outputs is not None:
        env_vars['SKIP_DISTRIBUTION_MIN_OUTPUTS'] = str(settings.skip_distribution_min_outputs)
        os.environ['SKIP_DISTRIBUTION_MIN_OUTPUTS'] = str(settings.skip_distribution_min_outputs)
        updated.append('skip_distribution_min_outputs')
    
    if settings.max_transactions_per_address is not None:
        env_vars['MAX_TRANSACTIONS_PER_ADDRESS'] = str(settings.max_transactions_per_address)
        os.environ['MAX_TRANSACTIONS_PER_ADDRESS'] = str(settings.max_transactions_per_address)
        updated.append('max_transactions_per_address')
    
    if settings.max_depth is not None:
        env_vars['MAX_DEPTH'] = str(settings.max_depth)
        os.environ['MAX_DEPTH'] = str(settings.max_depth)
        updated.append('max_depth')
    
    if settings.exchange_wallet_threshold is not None:
        env_vars['EXCHANGE_WALLET_THRESHOLD'] = str(settings.exchange_wallet_threshold)
        os.environ['EXCHANGE_WALLET_THRESHOLD'] = str(settings.exchange_wallet_threshold)
        updated.append('exchange_wallet_threshold')
    
    if settings.max_input_addresses_per_tx is not None:
        env_vars['MAX_INPUT_ADDRESSES_PER_TX'] = str(settings.max_input_addresses_per_tx)
        os.environ['MAX_INPUT_ADDRESSES_PER_TX'] = str(settings.max_input_addresses_per_tx)
        updated.append('max_input_addresses_per_tx')
    
    if settings.max_output_addresses_per_tx is not None:
        env_vars['MAX_OUTPUT_ADDRESSES_PER_TX'] = str(settings.max_output_addresses_per_tx)
        os.environ['MAX_OUTPUT_ADDRESSES_PER_TX'] = str(settings.max_output_addresses_per_tx)
        updated.append('max_output_addresses_per_tx')
    
    # Write to .env file
    _write_env_file(env_vars)
    
    # Reload config module to pick up new values
    import importlib
    import config
    importlib.reload(config)
    
    return {
        'message': 'Settings updated successfully',
        'updated_fields': updated,
        'current_settings': {
            'default_api': env_vars.get('DEFAULT_API', 'mempool'),
            'mempool_api_key_set': bool(env_vars.get('MEMPOOL_API_KEY', '')),
            'use_cache': env_vars.get('USE_CACHE', 'true').lower() == 'true'
        }
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)