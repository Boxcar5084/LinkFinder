# Bitcoin Address Linking Application
## Complete Implementation Guide

---

## 1. Project Overview

This application traces connections between two sets of Bitcoin addresses using forensic blockchain analysis. It implements bidirectional address linking through transaction graph traversal, with support for both external APIs (Phase 1) and local node infrastructure (Phase 2).

**Key Features:**
- Bidirectional address tracing between two address sets
- Common-input-ownership heuristic for address clustering
- Block height and transaction filtering
- Automatic checkpointing with resumable queries
- CSV and JSON export formats
- SQLite transaction caching with size limits

---

## 2. Technology Stack

| Component | Technology | Rationale |
|-----------|-----------|-----------|
| Framework | FastAPI | Async support for concurrent API calls; production-ready |
| HTTP Client | httpx | Async-first; better than requests for I/O-bound operations |
| Database | SQLite | Lightweight; perfect for single-machine deployment with size limits |
| Data Processing | pandas, networkx | Address graph construction; efficient set operations |
| Export | csv, json | CSV for Excel/manual analysis; JSON for programmatic reimport |
| Checkpointing | pickle, JSON | Serialization of search state; resumable queries |

---

## 3. Architecture

```
┌─────────────────────────────────────┐
│    FastAPI Application              │
├─────────────────────────────────────┤
│  Route Handlers                     │
│  ├─ POST /trace-addresses           │
│  ├─ POST /resume-trace              │
│  ├─ GET /trace-status/{session_id}  │
│  └─ GET /export-results/{session_id}│
└─────────────────────────────────────┘
           │
           ├──────────────┬──────────────┬──────────────┐
           ▼              ▼              ▼              ▼
    ┌────────────┐ ┌────────────┐ ┌───────────┐ ┌──────────────┐
    │ API Layer  │ │ Graph Eng. │ │ Cache DB  │ │ Checkpoint   │
    │(Strategy)  │ │(Traversal) │ │(SQLite)   │ │ Manager      │
    └────────────┘ └────────────┘ └───────────┘ └──────────────┘
           │              │              │              │
           └──────────────┴──────────────┴──────────────┘
                          │
        ┌─────────────────┼─────────────────┐
        ▼                 ▼                 ▼
    ┌──────────┐   ┌──────────────┐  ┌──────────┐
    │ Blockch. │   │ Mempool.spa. │  │ Local    │
    │ API      │   │ API          │  │ Electrs  │
    │ (ext)    │   │ (ext)        │  │ (Phase2) │
    └──────────┘   └──────────────┘  └──────────┘
```

### Module Breakdown

**1. api_provider.py** - API abstraction layer
**2. graph_engine.py** - Address tracing and clustering logic
**3. cache_manager.py** - Transaction caching with SQLite
**4. checkpoint_manager.py** - Resumable query state management
**5. export_manager.py** - CSV and JSON export
**6. main.py** - FastAPI application and routes

---

## 4. Phase 1: External API Integration

### 4.1 API Provider (Abstraction Layer)

Start with this structure to make switching APIs trivial:

```python
# api_provider.py
from abc import ABC, abstractmethod
from typing import Dict, List, Any, Optional
import httpx
from enum import Enum

class APIProvider(ABC):
    """Base class for blockchain API providers"""
    
    @abstractmethod
    async def get_address_transactions(self, address: str, 
                                      start_block: Optional[int] = None,
                                      end_block: Optional[int] = None) -> List[Dict[str, Any]]:
        """
        Fetch transactions for an address.
        Returns list of dicts with keys: txid, block_height, inputs, outputs, timestamp
        """
        pass
    
    @abstractmethod
    async def validate_address(self, address: str) -> bool:
        """Check if address is valid"""
        pass

class BlockchairProvider(APIProvider):
    def __init__(self, rate_limit_per_sec: int = 3):
        self.base_url = "https://api.blockchair.com/bitcoin"
        self.rate_limit = rate_limit_per_sec
        self.client = None
    
    async def get_address_transactions(self, address: str, 
                                      start_block: Optional[int] = None,
                                      end_block: Optional[int] = None) -> List[Dict]:
        if not self.client:
            self.client = httpx.AsyncClient()
        
        # Blockchair returns max 100 transactions per request
        url = f"{self.base_url}/dashboards/address/{address}?transaction_details=true"
        try:
            response = await self.client.get(url, timeout=30)
            data = response.json()
            
            if 'data' not in data or address not in data['data']:
                return []
            
            txs = data['data'][address].get('transactions', [])
            
            # Filter by block height if specified
            if start_block or end_block:
                txs = [tx for tx in txs 
                      if (not start_block or tx.get('block_id', 0) >= start_block) and
                         (not end_block or tx.get('block_id', 0) <= end_block)]
            
            return txs
        except httpx.HTTPError as e:
            print(f"Error fetching from Blockchair: {e}")
            return []
    
    async def validate_address(self, address: str) -> bool:
        # Blockchair validates during fetch; 26-35 chars for BTC
        return 26 <= len(address) <= 35

class MempoolSpaceProvider(APIProvider):
    def __init__(self):
        self.base_url = "https://mempool.space/api"
        self.client = None
    
    async def get_address_transactions(self, address: str,
                                      start_block: Optional[int] = None,
                                      end_block: Optional[int] = None) -> List[Dict]:
        if not self.client:
            self.client = httpx.AsyncClient()
        
        url = f"{self.base_url}/address/{address}/txs"
        try:
            response = await self.client.get(url, timeout=30)
            txs = response.json()
            
            if not isinstance(txs, list):
                return []
            
            # Filter by block height
            if start_block or end_block:
                txs = [tx for tx in txs
                      if (not start_block or tx.get('status', {}).get('block_height', 0) >= start_block) and
                         (not end_block or tx.get('status', {}).get('block_height', 0) <= end_block)]
            
            return txs
        except httpx.HTTPError as e:
            print(f"Error fetching from Mempool: {e}")
            return []
    
    async def validate_address(self, address: str) -> bool:
        return 26 <= len(address) <= 35
```

### 4.2 Transaction Cache Manager

```python
# cache_manager.py
import sqlite3
import json
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional, Dict, List, Any

class TransactionCache:
    def __init__(self, db_path: str = "blockchain_cache.db", max_size_mb: int = 500):
        self.db_path = db_path
        self.max_size_mb = max_size_mb
        self.conn = None
        self.init_db()
    
    def init_db(self):
        """Initialize SQLite database"""
        self.conn = sqlite3.connect(self.db_path)
        c = self.conn.cursor()
        
        c.execute('''
            CREATE TABLE IF NOT EXISTS cached_transactions (
                address TEXT NOT NULL,
                transactions JSON NOT NULL,
                last_updated TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                block_range TEXT,
                PRIMARY KEY (address, block_range)
            )
        ''')
        
        c.execute('''
            CREATE INDEX IF NOT EXISTS idx_address ON cached_transactions(address)
        ''')
        
        c.execute('''
            CREATE TABLE IF NOT EXISTS cache_metadata (
                key TEXT PRIMARY KEY,
                value TEXT
            )
        ''')
        
        self.conn.commit()
    
    def get_cached(self, address: str, block_range: Optional[tuple] = None) -> Optional[List[Dict]]:
        """Retrieve cached transactions"""
        c = self.conn.cursor()
        range_str = f"{block_range[0]}-{block_range[1]}" if block_range else "all"
        
        c.execute('SELECT transactions, last_updated FROM cached_transactions WHERE address = ? AND block_range = ?',
                 (address, range_str))
        result = c.fetchone()
        
        if result:
            txs, updated = result
            # Invalidate if older than 24 hours
            if datetime.fromisoformat(updated) > datetime.now() - timedelta(hours=24):
                return json.loads(txs)
            else:
                self.delete_cached(address, block_range)
        
        return None
    
    def cache(self, address: str, transactions: List[Dict], block_range: Optional[tuple] = None):
        """Store transactions in cache with size management"""
        c = self.conn.cursor()
        range_str = f"{block_range[0]}-{block_range[1]}" if block_range else "all"
        
        c.execute('INSERT OR REPLACE INTO cached_transactions (address, transactions, block_range) VALUES (?, ?, ?)',
                 (address, json.dumps(transactions), range_str))
        self.conn.commit()
        
        # Check cache size and prune if necessary
        self._enforce_cache_size()
    
    def _enforce_cache_size(self):
        """Remove oldest entries if cache exceeds max size"""
        c = self.conn.cursor()
        c.execute("SELECT page_count * page_size / 1024 / 1024 FROM pragma_page_count(), pragma_page_size()")
        size_mb = c.fetchone()[0]
        
        if size_mb > self.max_size_mb:
            # Delete oldest 10% of entries
            c.execute('DELETE FROM cached_transactions WHERE address IN (SELECT address FROM cached_transactions ORDER BY last_updated ASC LIMIT ?)',
                     (int(self.max_size_mb * 0.1),))
            self.conn.commit()
    
    def delete_cached(self, address: str, block_range: Optional[tuple] = None):
        """Remove specific cache entry"""
        c = self.conn.cursor()
        range_str = f"{block_range[0]}-{block_range[1]}" if block_range else "all"
        c.execute('DELETE FROM cached_transactions WHERE address = ? AND block_range = ?', (address, range_str))
        self.conn.commit()
```

### 4.3 Checkpoint Manager

```python
# checkpoint_manager.py
import json
import pickle
from pathlib import Path
from datetime import datetime
from typing import Optional, Set, Dict, Any
import uuid

class CheckpointManager:
    def __init__(self, checkpoint_dir: str = "./checkpoints"):
        self.checkpoint_dir = Path(checkpoint_dir)
        self.checkpoint_dir.mkdir(exist_ok=True)
    
    def create_checkpoint(self, session_id: str, state: Dict[str, Any]) -> str:
        """
        Save checkpoint with session state.
        State format:
        {
            'visited_forward': set of addresses traced from list A,
            'visited_backward': set of addresses traced from list B,
            'queue_forward': remaining addresses to trace from A,
            'queue_backward': remaining addresses to trace from B,
            'connections_found': list of connection chains,
            'progress': {'current_depth': int, 'max_depth': int}
        }
        """
        checkpoint_id = str(uuid.uuid4())
        checkpoint_file = self.checkpoint_dir / f"{session_id}_{checkpoint_id}.pkl"
        
        checkpoint_data = {
            'timestamp': datetime.now().isoformat(),
            'session_id': session_id,
            'state': state
        }
        
        with open(checkpoint_file, 'wb') as f:
            pickle.dump(checkpoint_data, f)
        
        return checkpoint_id
    
    def load_checkpoint(self, session_id: str, checkpoint_id: str) -> Optional[Dict[str, Any]]:
        """Load checkpoint by ID"""
        checkpoint_file = self.checkpoint_dir / f"{session_id}_{checkpoint_id}.pkl"
        
        if not checkpoint_file.exists():
            return None
        
        with open(checkpoint_file, 'rb') as f:
            return pickle.load(f)
    
    def list_checkpoints(self, session_id: str) -> list:
        """List all checkpoints for a session, ordered by timestamp"""
        checkpoints = []
        for f in self.checkpoint_dir.glob(f"{session_id}_*.pkl"):
            try:
                with open(f, 'rb') as pf:
                    data = pickle.load(pf)
                    checkpoints.append({
                        'checkpoint_id': f.stem.split('_', 1)[1],
                        'timestamp': data['timestamp'],
                        'file': f
                    })
            except:
                pass
        
        return sorted(checkpoints, key=lambda x: x['timestamp'], reverse=True)
    
    def prompt_resume(self, session_id: str) -> Optional[str]:
        """Prompt user if they want to resume from previous checkpoint"""
        checkpoints = self.list_checkpoints(session_id)
        
        if not checkpoints:
            return None
        
        latest = checkpoints[0]
        print(f"\n📋 Found checkpoint from {latest['timestamp']}")
        response = input("Resume from this checkpoint? (y/n): ").strip().lower()
        
        if response == 'y':
            return latest['checkpoint_id']
        
        return None
```

### 4.4 Graph Engine (Address Tracing)

```python
# graph_engine.py
import asyncio
from typing import Set, Dict, List, Tuple, Optional, Any
from collections import deque
import networkx as nx

class BitcoinAddressLinker:
    def __init__(self, api_provider, cache_manager, checkpoint_manager, max_tx_per_address: int = 500):
        self.api = api_provider
        self.cache = cache_manager
        self.checkpoint = checkpoint_manager
        self.max_tx_per_address = max_tx_per_address
        self.coinjoin_patterns = ['coinjoin', 'wasabi', 'samourai']
    
    def _is_coinjoin(self, tx: Dict[str, Any]) -> bool:
        """Detect likely CoinJoin transactions to filter out"""
        # Simple heuristic: many inputs with similar output amounts
        inputs = len(tx.get('inputs', []))
        outputs = len(tx.get('outputs', []))
        
        if inputs < 5 or outputs < 5:
            return False
        
        # Check for suspicious patterns
        tx_str = str(tx).lower()
        for pattern in self.coinjoin_patterns:
            if pattern in tx_str:
                return True
        
        return False
    
    async def get_address_txs(self, address: str, 
                             start_block: Optional[int] = None,
                             end_block: Optional[int] = None) -> List[Dict[str, Any]]:
        """Fetch transactions, checking cache first"""
        block_range = (start_block, end_block) if (start_block or end_block) else None
        
        # Try cache
        cached = self.cache.get_cached(address, block_range)
        if cached:
            return cached
        
        # Fetch from API
        txs = await self.api.get_address_transactions(address, start_block, end_block)
        
        # Filter and limit
        txs = [tx for tx in txs if not self._is_coinjoin(tx)]
        txs = txs[:self.max_tx_per_address]  # Limit to 500
        
        # Cache result
        if txs:
            self.cache.cache(address, txs, block_range)
        
        return txs
    
    def _extract_addresses_from_tx(self, tx: Dict[str, Any], direction: str = 'output') -> Set[str]:
        """Extract addresses from transaction"""
        addresses = set()
        
        if direction == 'output':
            for output in tx.get('outputs', []):
                if isinstance(output, dict) and 'address' in output:
                    addresses.add(output['address'])
                elif isinstance(output, str):
                    addresses.add(output)
        elif direction == 'input':
            for inp in tx.get('inputs', []):
                if isinstance(inp, dict) and 'address' in inp:
                    addresses.add(inp['address'])
        
        return addresses
    
    async def trace_forward(self, address: str, max_depth: int = 5,
                           start_block: Optional[int] = None,
                           end_block: Optional[int] = None,
                           state: Optional[Dict] = None) -> Set[str]:
        """
        Trace FORWARD: Start from address, find all outputs (recipients).
        Uses common-input heuristic: addresses in same tx inputs = same entity.
        """
        if state is None:
            state = {'visited': set(), 'queue': deque([(address, 0)])}
        
        visited = state['visited']
        queue = state['queue']
        
        while queue:
            current_addr, depth = queue.popleft()
            
            if current_addr in visited or depth >= max_depth:
                continue
            
            visited.add(current_addr)
            
            try:
                txs = await self.get_address_txs(current_addr, start_block, end_block)
                
                for tx in txs:
                    # Forward: collect output addresses (recipients)
                    output_addrs = self._extract_addresses_from_tx(tx, direction='output')
                    
                    # Common-input heuristic: all inputs to tx = same entity
                    input_addrs = self._extract_addresses_from_tx(tx, direction='input')
                    
                    for addr in output_addrs | input_addrs:
                        if addr not in visited:
                            queue.append((addr, depth + 1))
            
            except Exception as e:
                print(f"Error tracing {current_addr}: {e}")
        
        return visited
    
    async def trace_backward(self, address: str, max_depth: int = 5,
                            start_block: Optional[int] = None,
                            end_block: Optional[int] = None,
                            state: Optional[Dict] = None) -> Set[str]:
        """
        Trace BACKWARD: Start from address, find all inputs (senders).
        Mirrors forward tracing logic.
        """
        # For backward, we need to find transactions that output to this address,
        # then trace their inputs
        if state is None:
            state = {'visited': set(), 'queue': deque([(address, 0)])}
        
        visited = state['visited']
        queue = state['queue']
        
        while queue:
            current_addr, depth = queue.popleft()
            
            if current_addr in visited or depth >= max_depth:
                continue
            
            visited.add(current_addr)
            
            try:
                txs = await self.get_address_txs(current_addr, start_block, end_block)
                
                for tx in txs:
                    # Backward: collect input addresses (senders)
                    input_addrs = self._extract_addresses_from_tx(tx, direction='input')
                    
                    # Common-input heuristic
                    output_addrs = self._extract_addresses_from_tx(tx, direction='output')
                    
                    for addr in input_addrs | output_addrs:
                        if addr not in visited:
                            queue.append((addr, depth + 1))
            
            except Exception as e:
                print(f"Error tracing backward {current_addr}: {e}")
        
        return visited
    
    async def find_connection(self, list_a: List[str], list_b: List[str],
                             max_depth: int = 5,
                             start_block: Optional[int] = None,
                             end_block: Optional[int] = None,
                             session_id: Optional[str] = None) -> Dict[str, Any]:
        """
        Find connections between two address lists.
        Returns path from any address in list_a to any address in list_b.
        """
        results = {
            'connections_found': [],
            'search_depth': max_depth,
            'total_addresses_examined': 0,
            'session_id': session_id
        }
        
        # Trace forward from list_a
        forward_traces = {}
        for idx, addr in enumerate(list_a):
            print(f"[Forward] Tracing {idx + 1}/{len(list_a)}: {addr}")
            forward_traces[addr] = await self.trace_forward(addr, max_depth, start_block, end_block)
        
        # Trace backward from list_b
        backward_traces = {}
        for idx, addr in enumerate(list_b):
            print(f"[Backward] Tracing {idx + 1}/{len(list_b)}: {addr}")
            backward_traces[addr] = await self.trace_backward(addr, max_depth, start_block, end_block)
        
        # Find intersections
        for addr_a, forward_set in forward_traces.items():
            for addr_b, backward_set in backward_traces.items():
                overlap = forward_set.intersection(backward_set)
                if overlap:
                    results['connections_found'].append({
                        'source': addr_a,
                        'target': addr_b,
                        'meeting_points': list(overlap),
                        'path_length': len(overlap)
                    })
        
        results['total_addresses_examined'] = sum(len(s) for s in forward_traces.values()) + \
                                             sum(len(s) for s in backward_traces.values())
        
        if not results['connections_found']:
            results['status'] = 'No connection found'
        else:
            results['status'] = 'Connection(s) found'
        
        return results
```

### 4.5 Export Manager

```python
# export_manager.py
import csv
import json
from pathlib import Path
from typing import Dict, List, Any
from datetime import datetime

class ExportManager:
    def __init__(self, export_dir: str = "./exports"):
        self.export_dir = Path(export_dir)
        self.export_dir.mkdir(exist_ok=True)
    
    def export_to_csv(self, results: Dict[str, Any], session_id: str) -> str:
        """Export connection results to CSV"""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        csv_file = self.export_dir / f"connections_{session_id}_{timestamp}.csv"
        
        with open(csv_file, 'w', newline='') as f:
            writer = csv.writer(f)
            
            # Header
            writer.writerow(['Source Address', 'Target Address', 'Meeting Points', 'Path Length'])
            
            # Data
            for connection in results.get('connections_found', []):
                writer.writerow([
                    connection['source'],
                    connection['target'],
                    '|'.join(connection['meeting_points']),
                    connection['path_length']
                ])
        
        print(f"✅ CSV exported to {csv_file}")
        return str(csv_file)
    
    def export_to_json(self, results: Dict[str, Any], session_id: str) -> str:
        """Export connection results to JSON"""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        json_file = self.export_dir / f"connections_{session_id}_{timestamp}.json"
        
        with open(json_file, 'w') as f:
            json.dump(results, f, indent=2)
        
        print(f"✅ JSON exported to {json_file}")
        return str(json_file)
    
    def export_both(self, results: Dict[str, Any], session_id: str) -> Tuple[str, str]:
        """Export to both CSV and JSON"""
        csv_path = self.export_to_csv(results, session_id)
        json_path = self.export_to_json(results, session_id)
        return csv_path, json_path
```

### 4.6 FastAPI Application

```python
# main.py
from fastapi import FastAPI, HTTPException, BackgroundTasks
from pydantic import BaseModel
from typing import List, Optional
import uuid
import asyncio
from api_provider import BlockchairProvider, MempoolSpaceProvider
from graph_engine import BitcoinAddressLinker
from cache_manager import TransactionCache
from checkpoint_manager import CheckpointManager
from export_manager import ExportManager

app = FastAPI(title="Bitcoin Address Linker")

# Initialize components
api_provider = MempoolSpaceProvider()  # Switch to Blockchair if needed
cache_manager = TransactionCache(max_size_mb=500)
checkpoint_manager = CheckpointManager()
export_manager = ExportManager()
linker = BitcoinAddressLinker(api_provider, cache_manager, checkpoint_manager)

class TraceRequest(BaseModel):
    list_a: List[str]
    list_b: List[str]
    max_depth: int = 5
    start_block: Optional[int] = None
    end_block: Optional[int] = None
    auto_save_interval: int = 10  # checkpoints per N addresses

class ResumeRequest(BaseModel):
    session_id: str
    checkpoint_id: str

sessions = {}  # Track active sessions

@app.post("/trace-addresses")
async def trace_addresses(request: TraceRequest, background_tasks: BackgroundTasks):
    """Start new address tracing session"""
    session_id = str(uuid.uuid4())
    
    # Validate inputs
    if not request.list_a or not request.list_b:
        raise HTTPException(status_code=400, detail="Both lists must have addresses")
    
    # Start tracing in background
    background_tasks.add_task(
        run_trace_session,
        session_id,
        request.list_a,
        request.list_b,
        request.max_depth,
        request.start_block,
        request.end_block
    )
    
    return {
        'session_id': session_id,
        'status': 'Tracing started'
    }

async def run_trace_session(session_id: str, list_a: List[str], list_b: List[str],
                           max_depth: int, start_block: Optional[int], end_block: Optional[int]):
    """Run tracing and save results"""
    try:
        sessions[session_id] = {'status': 'running', 'progress': 0}
        
        results = await linker.find_connection(
            list_a, list_b, max_depth, start_block, end_block, session_id
        )
        
        # Export results
        export_manager.export_both(results, session_id)
        
        sessions[session_id] = {'status': 'completed', 'results': results}
    except Exception as e:
        sessions[session_id] = {'status': 'failed', 'error': str(e)}
        print(f"Session {session_id} failed: {e}")

@app.get("/trace-status/{session_id}")
async def get_trace_status(session_id: str):
    """Check status of tracing session"""
    if session_id not in sessions:
        raise HTTPException(status_code=404, detail="Session not found")
    
    return sessions[session_id]

@app.get("/export-results/{session_id}")
async def get_results(session_id: str):
    """Get results of completed session"""
    if session_id not in sessions:
        raise HTTPException(status_code=404, detail="Session not found")
    
    session = sessions[session_id]
    if session['status'] != 'completed':
        raise HTTPException(status_code=400, detail="Session not completed")
    
    return session['results']

@app.post("/resume-trace")
async def resume_trace(request: ResumeRequest, background_tasks: BackgroundTasks):
    """Resume from checkpoint"""
    checkpoint_data = checkpoint_manager.load_checkpoint(request.session_id, request.checkpoint_id)
    
    if not checkpoint_data:
        raise HTTPException(status_code=404, detail="Checkpoint not found")
    
    # Resume would require storing original parameters
    # Implementation depends on your checkpoint strategy
    return {'message': 'Resume functionality - implement based on checkpoint state'}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
```

---

## 5. Phase 2: Local Electrs Integration

Once your Electrs instance finishes syncing:

```python
# electrs_provider.py
class ElectrsProvider(APIProvider):
    def __init__(self, electrs_url: str = "http://localhost:50002"):
        self.base_url = electrs_url
        self.client = None
    
    async def get_address_transactions(self, address: str,
                                      start_block: Optional[int] = None,
                                      end_block: Optional[int] = None) -> List[Dict]:
        if not self.client:
            self.client = httpx.AsyncClient()
        
        # Electrs REST API
        url = f"{self.base_url}/api/address/{address}/txs"
        response = await self.client.get(url)
        txs = response.json()
        
        # Filter by block height
        if start_block or end_block:
            txs = [tx for tx in txs
                  if (not start_block or tx['status']['block_height'] >= start_block) and
                     (not end_block or tx['status']['block_height'] <= end_block)]
        
        return txs
```

Switch in main.py:
```python
# When Electrs is ready:
api_provider = ElectrsProvider("http://localhost:50002")
```

---

## 6. Running the Application

```bash
# Install dependencies
pip install fastapi uvicorn httpx pandas networkx

# Start server
python main.py

# Make request
curl -X POST http://localhost:8000/trace-addresses \
  -H "Content-Type: application/json" \
  -d '{
    "list_a": ["address1", "address2"],
    "list_b": ["address3", "address4"],
    "max_depth": 5,
    "start_block": 700000,
    "end_block": 750000
  }'

# Check status
curl http://localhost:8000/trace-status/{session_id}
```

---

## 7. Best Practices & Optimizations

1. **Rate Limiting**: Implement exponential backoff for API failures
2. **Batch Operations**: Process multiple seeds concurrently with `asyncio.gather()`
3. **Memory Management**: Monitor cache size; prune old entries automatically
4. **Checkpointing Frequency**: Save every 10-50 addresses traced
5. **Error Recovery**: Resume from checkpoint on network failures
6. **Block Filtering**: Always use block ranges to reduce dataset size

---

## 8. Future Enhancements

- [ ] Change address detection heuristic
- [ ] Payment channel analysis
- [ ] Temporal graph analysis
- [ ] Integration with blockchain.com/Chainalysis APIs for labeling
- [ ] Web UI dashboard for visualization
- [ ] Multi-chain support (Ethereum, Monero, etc.)
