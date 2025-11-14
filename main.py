# -*- coding: utf-8 -*-
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from typing import List, Optional, Dict, Any
import uuid
import asyncio
import sqlite3
from datetime import datetime
from api_provider import get_provider
from graph_engine import BitcoinAddressLinker
from cache_manager import TransactionCache
from checkpoint_manager import CheckpointManager
from export_manager import ExportManager
from config import DEFAULT_API

app = FastAPI(title="Bitcoin Address Linker")

# Global state
print("[MAIN] Initializing global services...")
cache_manager = TransactionCache()
print(f"[MAIN] Cache manager created: {cache_manager}")
checkpoint_manager = CheckpointManager()
export_manager = ExportManager()
sessions = {}  # session_id -> {status, task, results, checkpoint_id, ...}
print("[MAIN] Global services initialized")

class TraceRequest(BaseModel):
    list_a: List[str]
    list_b: List[str]
    max_depth: int = 5
    start_block: Optional[int] = None
    end_block: Optional[int] = None

@app.on_event("shutdown")
async def shutdown():
    cache_manager.close()
    # Cancel all running tasks and save checkpoints
    for session_id, session in sessions.items():
        if session['status'] == 'running' and session.get('task'):
            session['task'].cancel()

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

        # Create wrapper linker that updates trace state for checkpointing
        checkpoint_state = sessions[session_id].get('checkpoint_state')
        print(f"[MAIN] Creating linker with cache_manager: {cache_manager}")
        linker = BitcoinAddressLinkerWithCheckpoint(
            api,
            cache_manager,
            session_id,
            sessions,
            checkpoint_state=checkpoint_state
        )
        print(f"[MAIN] Linker created, cache in linker: {linker.linker.cache}")

        # NEW: Start periodic checkpoint task
        checkpoint_task = asyncio.create_task(
            _periodic_checkpoint_task(session_id)
        )

        results = await linker.find_connection(
            request.list_a, request.list_b,
            request.max_depth,
            request.start_block,
            request.end_block
        )

        csv_path, json_path = export_manager.export_both(results, session_id)

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
        checkpoint_data = {
            'session_id': session_id,
            'request': sessions[session_id].get('request'),
            'trace_state': trace_state,
            'cancelled_at': datetime.now().isoformat(),
            'progress': {
                'addresses_examined': len(trace_state.get('visited', set())),
                'visited_forward': len(trace_state.get('visited_forward', {})),
                'visited_backward': len(trace_state.get('visited_backward', {})),
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
            
            # Extract the visited dictionaries (they should have real data now from graph_engine)
            visited_forward = trace_state.get('visited_forward', {})
            visited_backward = trace_state.get('visited_backward', {})
            visited = trace_state.get('visited', set())
            connections_found = trace_state.get('connections_found', [])
            
            # Build checkpoint data
            # Convert dicts to serializable format (dicts are already serializable, but ensure nested structures are handled)
            checkpoint_data = {
                'session_id': session_id,
                'request': sessions[session_id].get('request'),
                'trace_state': {
                    'visited_forward': visited_forward,  # Dict is already serializable
                    'visited_backward': visited_backward,  # Dict is already serializable
                    'visited': list(visited) if isinstance(visited, set) else visited,  # Convert set to list
                    'queued_forward': trace_state.get('queued_forward', []),
                    'queued_backward': trace_state.get('queued_backward', []),
                    'connections_found': trace_state.get('connections_found', [])
                },
                'periodic_checkpoint': True,
                'checkpoint_time': datetime.now().isoformat(),
                'progress': {
                    'addresses_examined': len(trace_state.get('visited', set())),
                    'visited_forward': len(trace_state.get('visited_forward', {})),
                    'visited_backward': len(trace_state.get('visited_backward', {})),
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

    def __init__(self, api, cache_manager, session_id, sessions_dict, checkpoint_state=None):
        from graph_engine import BitcoinAddressLinker
        self.linker = BitcoinAddressLinker(api, cache_manager)
        self.session_id = session_id
        self.sessions = sessions_dict
        
        # Load checkpoint state if resuming
        self.checkpoint_state = checkpoint_state or {}

    async def find_connection(self, list_a, list_b, max_depth, start_block, end_block):
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
            
            print(f" Previously visited (forward): {len(visited_forward)} addresses")
            print(f" Previously visited (backward): {len(visited_backward)} addresses")
            print(f" Total visited: {len(visited)} addresses")
            print(f" Continuing trace...\n")
            
            # CRITICAL FIX: Pass queued addresses to linker for proper resumption
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
                progress_callback=self._progress_callback
            )
        else:
            # FRESH TRACE - call find_connection FIRST
            result = await self.linker.find_connection(
                list_a, list_b, max_depth, start_block, end_block,
                progress_callback=self._progress_callback
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
            'visited_backward': len(trace_state.get('visited_backward', {}))
        }

        return result

    def _progress_callback(self, progress):
        """Update trace_state as progress is reported"""
        session = self.sessions.get(self.session_id)
        if not session or 'trace_state' not in session:
            return
        
        current = progress.get('current', '')
        direction = progress.get('direction', 'forward')
        
        # Ensure visited_forward and visited_backward are dicts
        if 'visited_forward' not in session['trace_state']:
            session['trace_state']['visited_forward'] = {}
        if 'visited_backward' not in session['trace_state']:
            session['trace_state']['visited_backward'] = {}
        if 'visited' not in session['trace_state']:
            session['trace_state']['visited'] = set()
        
        # Convert to dict if it's a set (backward compatibility)
        if isinstance(session['trace_state']['visited_forward'], set):
            session['trace_state']['visited_forward'] = {addr: [addr] for addr in session['trace_state']['visited_forward']}
        if isinstance(session['trace_state']['visited_backward'], set):
            session['trace_state']['visited_backward'] = {addr: [addr] for addr in session['trace_state']['visited_backward']}
        
        # Add to visited set
        session['trace_state']['visited'].add(current)
        
        # Track direction - graph_engine manages the dict structure, so we just ensure it exists
        # The actual path tracking is done in graph_engine, not here




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
        'checkpoint_id': checkpoint_id,
        'trace_state': checkpoint_trace_state,
        'checkpoint_state': checkpoint_trace_state,  # PASS TO LINKER
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
        'checkpoint_id': checkpoint_id,
        'trace_state': checkpoint_trace_state,
        'checkpoint_state': checkpoint_trace_state,  # PASS TO LINKER
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
        'checkpoint_id': checkpoint_id,
        'trace_state': checkpoint_trace_state,
        'checkpoint_state': checkpoint_trace_state,  # PASS TO LINKER
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

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)