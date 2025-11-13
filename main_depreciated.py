from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from typing import List, Optional
import uuid
import asyncio
from api_provider import get_provider
from graph_engine import BitcoinAddressLinker
from cache_manager import TransactionCache
from checkpoint_manager import CheckpointManager
from export_manager import ExportManager
from config import DEFAULT_API

app = FastAPI(title="🔗 Bitcoin Address Linker")

# Global state
cache_manager = TransactionCache()
checkpoint_manager = CheckpointManager()
export_manager = ExportManager()
sessions = {}

class TraceRequest(BaseModel):
    list_a: List[str]
    list_b: List[str]
    max_depth: int = 5
    start_block: Optional[int] = None
    end_block: Optional[int] = None

@app.on_event("shutdown")
async def shutdown():
    cache_manager.close()

@app.post("/trace")
async def start_trace(request: TraceRequest):
    """Start new address linking session"""
    if not request.list_a or not request.list_b:
        raise HTTPException(status_code=400, detail="Both lists required")
    
    session_id = str(uuid.uuid4())
    
    # Run tracing asynchronously
    asyncio.create_task(
        _run_trace_task(session_id, request)
    )
    
    return {'session_id': session_id, 'status': 'started'}

async def _run_trace_task(session_id: str, request: TraceRequest):
    """Background tracing task"""
    try:
        sessions[session_id] = {'status': 'running', 'progress': 0}
        
        api = get_provider(DEFAULT_API)
        linker = BitcoinAddressLinker(api, cache_manager)
        
        results = await linker.find_connection(
            request.list_a, request.list_b,
            request.max_depth,
            request.start_block,
            request.end_block
        )
        
        csv_path, json_path = export_manager.export_both(results, session_id)
        
        sessions[session_id] = {
            'status': 'completed',
            'results': results,
            'exports': {'csv': csv_path, 'json': json_path}
        }
        
        await api.close()
        
    except Exception as e:
        sessions[session_id] = {'status': 'failed', 'error': str(e)}
        print(f"❌ Session {session_id} failed: {e}")

@app.get("/status/{session_id}")
async def get_status(session_id: str):
    """Check session status"""
    if session_id not in sessions:
        raise HTTPException(status_code=404, detail="Session not found")
    return sessions[session_id]

@app.get("/results/{session_id}")
async def get_results(session_id: str):
    """Get completed results"""
    if session_id not in sessions:
        raise HTTPException(status_code=404, detail="Session not found")
    
    session = sessions[session_id]
    if session['status'] != 'completed':
        raise HTTPException(status_code=400, detail="Session not completed")
    
    return session['results']

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)