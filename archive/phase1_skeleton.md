# Bitcoin Address Linker - Phase 1 Complete Skeleton
## Ready-to-use code templates for Blockchair and Mempool APIs

```python
# ============================================================================
# FILE: requirements.txt
# ============================================================================
fastapi==0.104.0
uvicorn==0.24.0
httpx==0.25.0
pandas==2.1.0
networkx==3.2
pydantic==2.4.0
python-dotenv==1.0.0


# ============================================================================
# FILE: config.py
# ============================================================================
import os
from enum import Enum

class APIProvider(Enum):
    BLOCKCHAIR = "blockchair"
    MEMPOOL = "mempool"
    ELECTRS = "electrs"  # Phase 2

# Configuration
DEFAULT_API = APIProvider.MEMPOOL.value  # Start with Mempool (public, no auth)
BLOCKCHAIR_API_URL = "https://api.blockchair.com/bitcoin"
MEMPOOL_API_URL = "https://mempool.space/api"
ELECTRS_LOCAL_URL = "http://localhost:50002"  # Phase 2

MAX_TRANSACTIONS_PER_ADDRESS = 500
MAX_DEPTH = 5
CACHE_MAX_SIZE_MB = 500
CHECKPOINT_DIR = "./checkpoints"
EXPORT_DIR = "./exports"

# Rate limiting (requests per second)
BLOCKCHAIR_RATE_LIMIT = 3  # Free tier: 3 req/sec
MEMPOOL_RATE_LIMIT = 10  # No strict limit for public API


# ============================================================================
# FILE: api_provider.py
# ============================================================================
import httpx
import asyncio
from abc import ABC, abstractmethod
from typing import Dict, List, Any, Optional
from config import BLOCKCHAIR_API_URL, MEMPOOL_API_URL, ELECTRS_LOCAL_URL

class APIProvider(ABC):
    """Abstract base class for blockchain API providers"""
    
    @abstractmethod
    async def get_address_transactions(self, 
                                      address: str,
                                      start_block: Optional[int] = None,
                                      end_block: Optional[int] = None) -> List[Dict[str, Any]]:
        """Fetch transactions for an address"""
        pass
    
    @abstractmethod
    async def validate_address(self, address: str) -> bool:
        """Validate Bitcoin address format"""
        pass
    
    async def close(self):
        """Close async client"""
        pass


class BlockchairProvider(APIProvider):
    """Blockchair API implementation"""
    
    def __init__(self):
        self.base_url = BLOCKCHAIR_API_URL
        self.client = httpx.AsyncClient()
        self.rate_limit = 3  # Requests per second
        self.last_request_time = 0
    
    async def _rate_limit(self):
        """Implement rate limiting"""
        import time
        elapsed = time.time() - self.last_request_time
        wait_time = (1.0 / self.rate_limit) - elapsed
        if wait_time > 0:
            await asyncio.sleep(wait_time)
        self.last_request_time = time.time()
    
    async def get_address_transactions(self,
                                      address: str,
                                      start_block: Optional[int] = None,
                                      end_block: Optional[int] = None) -> List[Dict]:
        """Fetch transactions from Blockchair"""
        await self._rate_limit()
        
        url = f"{self.base_url}/dashboards/address/{address}?transaction_details=true"
        
        try:
            response = await self.client.get(url, timeout=30)
            data = response.json()
            
            if 'data' not in data or address not in data['data']:
                return []
            
            txs = data['data'][address].get('transactions', [])
            
            # Filter by block height
            if start_block is not None or end_block is not None:
                txs = [
                    tx for tx in txs
                    if (start_block is None or tx.get('block_id', 0) >= start_block) and
                       (end_block is None or tx.get('block_id', 0) <= end_block)
                ]
            
            # Transform to standard format
            return [self._normalize_tx(tx) for tx in txs]
        
        except httpx.HTTPError as e:
            print(f"❌ Blockchair error for {address}: {e}")
            return []
    
    def _normalize_tx(self, tx: Dict) -> Dict:
        """Normalize Blockchair tx format"""
        return {
            'txid': tx.get('hash'),
            'block_height': tx.get('block_id'),
            'timestamp': tx.get('time'),
            'inputs': [{'address': inp['address']} for inp in tx.get('inputs', [])],
            'outputs': [{'address': out['address']} for out in tx.get('outputs', [])],
            'raw': tx
        }
    
    async def validate_address(self, address: str) -> bool:
        """Validate Bitcoin address"""
        # Basic validation: 26-35 chars for legacy/segwit addresses
        return 26 <= len(address) <= 35
    
    async def close(self):
        await self.client.aclose()


class MempoolSpaceProvider(APIProvider):
    """Mempool.space API implementation"""
    
    def __init__(self):
        self.base_url = MEMPOOL_API_URL
        self.client = httpx.AsyncClient()
    
    async def get_address_transactions(self,
                                      address: str,
                                      start_block: Optional[int] = None,
                                      end_block: Optional[int] = None) -> List[Dict]:
        """Fetch transactions from Mempool.space"""
        url = f"{self.base_url}/address/{address}/txs"
        
        try:
            response = await self.client.get(url, timeout=30)
            txs = response.json()
            
            if not isinstance(txs, list):
                return []
            
            # Filter by block height
            if start_block is not None or end_block is not None:
                txs = [
                    tx for tx in txs
                    if (start_block is None or tx.get('status', {}).get('block_height', 0) >= start_block) and
                       (end_block is None or tx.get('status', {}).get('block_height', 0) <= end_block)
                ]
            
            return [self._normalize_tx(tx) for tx in txs]
        
        except httpx.HTTPError as e:
            print(f"❌ Mempool error for {address}: {e}")
            return []
    
    def _normalize_tx(self, tx: Dict) -> Dict:
        """Normalize Mempool tx format"""
        return {
            'txid': tx.get('txid'),
            'block_height': tx.get('status', {}).get('block_height'),
            'timestamp': tx.get('status', {}).get('block_time'),
            'inputs': [{'address': inp.get('prevout', {}).get('scriptpubkey_address')} 
                      for inp in tx.get('vin', [])],
            'outputs': [{'address': out.get('scriptpubkey_address')} 
                       for out in tx.get('vout', [])],
            'raw': tx
        }
    
    async def validate_address(self, address: str) -> bool:
        """Validate Bitcoin address via API"""
        url = f"{self.base_url}/address/{address}"
        try:
            response = await self.client.get(url, timeout=10)
            return response.status_code == 200
        except:
            return False
    
    async def close(self):
        await self.client.aclose()


class ElectrsProvider(APIProvider):
    """Local Electrs REST API implementation (Phase 2)"""
    
    def __init__(self, electrs_url: str = ELECTRS_LOCAL_URL):
        self.base_url = electrs_url
        self.client = httpx.AsyncClient()
    
    async def get_address_transactions(self,
                                      address: str,
                                      start_block: Optional[int] = None,
                                      end_block: Optional[int] = None) -> List[Dict]:
        """Fetch from local Electrs"""
        url = f"{self.base_url}/api/address/{address}/txs"
        
        try:
            response = await self.client.get(url, timeout=30)
            txs = response.json()
            
            if start_block is not None or end_block is not None:
                txs = [
                    tx for tx in txs
                    if (start_block is None or tx.get('status', {}).get('block_height', 0) >= start_block) and
                       (end_block is None or tx.get('status', {}).get('block_height', 0) <= end_block)
                ]
            
            return [self._normalize_tx(tx) for tx in txs]
        
        except Exception as e:
            print(f"❌ Electrs error: {e}")
            return []
    
    def _normalize_tx(self, tx: Dict) -> Dict:
        """Normalize Electrs tx format"""
        return {
            'txid': tx.get('txid'),
            'block_height': tx.get('status', {}).get('block_height'),
            'timestamp': tx.get('status', {}).get('block_time'),
            'inputs': [{'address': inp.get('prevout', {}).get('scriptpubkey_address')}
                      for inp in tx.get('vin', [])],
            'outputs': [{'address': out.get('scriptpubkey_address')}
                       for out in tx.get('vout', [])],
            'raw': tx
        }
    
    async def validate_address(self, address: str) -> bool:
        return True  # Assume valid for local
    
    async def close(self):
        await self.client.aclose()


def get_provider(provider_name: str) -> APIProvider:
    """Factory function to get API provider"""
    if provider_name.lower() == 'blockchair':
        return BlockchairProvider()
    elif provider_name.lower() == 'mempool':
        return MempoolSpaceProvider()
    elif provider_name.lower() == 'electrs':
        return ElectrsProvider()
    else:
        raise ValueError(f"Unknown provider: {provider_name}")


# ============================================================================
# FILE: cache_manager.py
# ============================================================================
import sqlite3
import json
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional, Dict, List, Any
from config import CACHE_MAX_SIZE_MB, CHECKPOINT_DIR

class TransactionCache:
    """SQLite-based transaction cache with size limits"""
    
    def __init__(self, db_path: str = "blockchain_cache.db", max_size_mb: int = CACHE_MAX_SIZE_MB):
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
                size_bytes INTEGER,
                PRIMARY KEY (address, block_range)
            )
        ''')
        
        c.execute('CREATE INDEX IF NOT EXISTS idx_address ON cached_transactions(address)')
        c.execute('CREATE INDEX IF NOT EXISTS idx_updated ON cached_transactions(last_updated)')
        
        self.conn.commit()
        print(f"✅ Cache initialized at {self.db_path}")
    
    def get_cached(self, address: str, block_range: Optional[tuple] = None) -> Optional[List[Dict]]:
        """Retrieve cached transactions"""
        c = self.conn.cursor()
        range_str = f"{block_range[0]}-{block_range[1]}" if block_range else "all"
        
        c.execute('''
            SELECT transactions, last_updated 
            FROM cached_transactions 
            WHERE address = ? AND block_range = ?
        ''', (address, range_str))
        
        result = c.fetchone()
        if result:
            txs_json, updated = result
            # Invalidate if older than 24 hours
            updated_dt = datetime.fromisoformat(updated)
            if updated_dt > datetime.now() - timedelta(hours=24):
                return json.loads(txs_json)
            else:
                self.delete_cached(address, block_range)
        
        return None
    
    def cache(self, address: str, transactions: List[Dict], block_range: Optional[tuple] = None):
        """Store transactions in cache"""
        c = self.conn.cursor()
        range_str = f"{block_range[0]}-{block_range[1]}" if block_range else "all"
        tx_json = json.dumps(transactions)
        size_bytes = len(tx_json.encode('utf-8'))
        
        c.execute('''
            INSERT OR REPLACE INTO cached_transactions 
            (address, transactions, block_range, size_bytes) 
            VALUES (?, ?, ?, ?)
        ''', (address, tx_json, range_str, size_bytes))
        
        self.conn.commit()
        self._enforce_cache_size()
    
    def _enforce_cache_size(self):
        """Remove oldest entries if cache exceeds max size"""
        c = self.conn.cursor()
        c.execute("SELECT page_count * page_size / 1024 / 1024 FROM pragma_page_count(), pragma_page_size()")
        size_mb = c.fetchone()[0]
        
        if size_mb > self.max_size_mb:
            print(f"⚠️  Cache size {size_mb}MB exceeds limit {self.max_size_mb}MB, pruning...")
            # Delete oldest 10%
            c.execute('''
                DELETE FROM cached_transactions 
                WHERE address IN (
                    SELECT address FROM cached_transactions 
                    ORDER BY last_updated ASC 
                    LIMIT (SELECT COUNT(*) / 10 FROM cached_transactions)
                )
            ''')
            self.conn.commit()
    
    def delete_cached(self, address: str, block_range: Optional[tuple] = None):
        """Remove specific cache entry"""
        c = self.conn.cursor()
        range_str = f"{block_range[0]}-{block_range[1]}" if block_range else "all"
        c.execute('DELETE FROM cached_transactions WHERE address = ? AND block_range = ?',
                 (address, range_str))
        self.conn.commit()
    
    def close(self):
        if self.conn:
            self.conn.close()


# ============================================================================
# FILE: checkpoint_manager.py
# ============================================================================
import json
import pickle
from pathlib import Path
from datetime import datetime
from typing import Optional, Dict, Any
import uuid
from config import CHECKPOINT_DIR

class CheckpointManager:
    """Manages query checkpoints for resumable sessions"""
    
    def __init__(self, checkpoint_dir: str = CHECKPOINT_DIR):
        self.checkpoint_dir = Path(checkpoint_dir)
        self.checkpoint_dir.mkdir(exist_ok=True)
    
    def create_checkpoint(self, session_id: str, state: Dict[str, Any]) -> str:
        """Create and save checkpoint"""
        checkpoint_id = str(uuid.uuid4())
        checkpoint_file = self.checkpoint_dir / f"{session_id}_{checkpoint_id}.pkl"
        
        checkpoint_data = {
            'timestamp': datetime.now().isoformat(),
            'session_id': session_id,
            'state': state
        }
        
        with open(checkpoint_file, 'wb') as f:
            pickle.dump(checkpoint_data, f)
        
        print(f"💾 Checkpoint saved: {checkpoint_id}")
        return checkpoint_id
    
    def load_checkpoint(self, session_id: str, checkpoint_id: str) -> Optional[Dict[str, Any]]:
        """Load checkpoint by ID"""
        checkpoint_file = self.checkpoint_dir / f"{session_id}_{checkpoint_id}.pkl"
        
        if not checkpoint_file.exists():
            return None
        
        with open(checkpoint_file, 'rb') as f:
            return pickle.load(f)
    
    def list_checkpoints(self, session_id: str) -> list:
        """List all checkpoints for session"""
        checkpoints = []
        for f in self.checkpoint_dir.glob(f"{session_id}_*.pkl"):
            try:
                with open(f, 'rb') as pf:
                    data = pickle.load(pf)
                    checkpoints.append({
                        'checkpoint_id': f.stem.split('_', 1)[1],
                        'timestamp': data['timestamp'],
                        'file': str(f)
                    })
            except Exception as e:
                print(f"Error loading checkpoint: {e}")
        
        return sorted(checkpoints, key=lambda x: x['timestamp'], reverse=True)
    
    def prompt_resume(self, session_id: str) -> Optional[str]:
        """Interactive prompt to resume from checkpoint"""
        checkpoints = self.list_checkpoints(session_id)
        
        if not checkpoints:
            return None
        
        latest = checkpoints[0]
        print(f"\n📋 Found checkpoint from {latest['timestamp']}")
        response = input("Resume from this checkpoint? (y/n): ").strip().lower()
        
        return latest['checkpoint_id'] if response == 'y' else None


# ============================================================================
# FILE: graph_engine.py
# ============================================================================
import asyncio
from typing import Set, Dict, List, Tuple, Optional, Any
from collections import deque
from api_provider import APIProvider
from cache_manager import TransactionCache
from config import MAX_TRANSACTIONS_PER_ADDRESS

class BitcoinAddressLinker:
    """Graph traversal engine for Bitcoin address linking"""
    
    def __init__(self, api_provider: APIProvider, cache_manager: TransactionCache,
                 max_tx_per_address: int = MAX_TRANSACTIONS_PER_ADDRESS):
        self.api = api_provider
        self.cache = cache_manager
        self.max_tx_per_address = max_tx_per_address
        self.coinjoin_patterns = ['coinjoin', 'wasabi', 'samourai', 'whirlpool']
    
    def _is_coinjoin(self, tx: Dict[str, Any]) -> bool:
        """Detect likely CoinJoin transactions"""
        inputs_count = len(tx.get('inputs', []))
        outputs_count = len(tx.get('outputs', []))
        
        # CoinJoin characteristics: many inputs and outputs
        if inputs_count < 5 or outputs_count < 5:
            return False
        
        # Check for known patterns
        tx_str = str(tx).lower()
        for pattern in self.coinjoin_patterns:
            if pattern in tx_str:
                return True
        
        return False
    
    async def get_address_txs(self, address: str,
                             start_block: Optional[int] = None,
                             end_block: Optional[int] = None) -> List[Dict[str, Any]]:
        """Fetch transactions with caching"""
        block_range = (start_block, end_block) if (start_block or end_block) else None
        
        # Check cache
        cached = self.cache.get_cached(address, block_range)
        if cached:
            print(f"📦 Cache hit: {address} ({len(cached)} txs)")
            return cached
        
        # Fetch from API
        print(f"🔍 Fetching: {address}")
        txs = await self.api.get_address_transactions(address, start_block, end_block)
        
        # Filter and limit
        txs = [tx for tx in txs if not self._is_coinjoin(tx)]
        txs = txs[:self.max_tx_per_address]
        
        # Cache result
        if txs:
            self.cache.cache(address, txs, block_range)
        
        return txs
    
    def _extract_addresses(self, tx: Dict[str, Any], direction: str = 'output') -> Set[str]:
        """Extract unique addresses from transaction"""
        addresses = set()
        
        key = 'outputs' if direction == 'output' else 'inputs'
        for item in tx.get(key, []):
            if isinstance(item, dict) and 'address' in item:
                addr = item['address']
                if addr and addr != 'None':  # Filter out nulls
                    addresses.add(addr)
        
        return addresses
    
    async def trace_forward(self, address: str, max_depth: int = 5,
                           start_block: Optional[int] = None,
                           end_block: Optional[int] = None) -> Set[str]:
        """
        Trace forward: Find all addresses reachable from starting address.
        Uses common-input heuristic.
        """
        visited = set()
        queue = deque([(address, 0)])
        
        while queue:
            current, depth = queue.popleft()
            
            if current in visited or depth >= max_depth:
                continue
            
            visited.add(current)
            print(f"  [→] Depth {depth}: {current}")
            
            try:
                txs = await self.get_address_txs(current, start_block, end_block)
                
                for tx in txs:
                    # Forward: outputs (recipients) + common-input heuristic
                    outputs = self._extract_addresses(tx, 'output')
                    inputs = self._extract_addresses(tx, 'input')
                    
                    for addr in outputs | inputs:
                        if addr not in visited:
                            queue.append((addr, depth + 1))
            
            except Exception as e:
                print(f"  ❌ Error tracing {current}: {e}")
        
        return visited
    
    async def trace_backward(self, address: str, max_depth: int = 5,
                            start_block: Optional[int] = None,
                            end_block: Optional[int] = None) -> Set[str]:
        """
        Trace backward: Find all addresses that can reach starting address.
        Mirrors forward logic.
        """
        visited = set()
        queue = deque([(address, 0)])
        
        while queue:
            current, depth = queue.popleft()
            
            if current in visited or depth >= max_depth:
                continue
            
            visited.add(current)
            print(f"  [←] Depth {depth}: {current}")
            
            try:
                txs = await self.get_address_txs(current, start_block, end_block)
                
                for tx in txs:
                    # Backward: inputs (senders) + common-input heuristic
                    inputs = self._extract_addresses(tx, 'input')
                    outputs = self._extract_addresses(tx, 'output')
                    
                    for addr in inputs | outputs:
                        if addr not in visited:
                            queue.append((addr, depth + 1))
            
            except Exception as e:
                print(f"  ❌ Error tracing {current}: {e}")
        
        return visited
    
    async def find_connection(self, list_a: List[str], list_b: List[str],
                             max_depth: int = 5,
                             start_block: Optional[int] = None,
                             end_block: Optional[int] = None) -> Dict[str, Any]:
        """Find connections between two address lists"""
        results = {
            'connections_found': [],
            'search_depth': max_depth,
            'total_addresses_examined': 0,
            'block_range': (start_block, end_block),
            'status': 'searching'
        }
        
        print(f"\n🔗 Linking {len(list_a)} addresses with {len(list_b)} addresses")
        print(f"   Depth: {max_depth}, Blocks: {start_block} - {end_block}\n")
        
        # Trace forward from list_a
        forward_traces = {}
        print("📤 Forward tracing (List A):")
        for idx, addr in enumerate(list_a, 1):
            print(f"[{idx}/{len(list_a)}] {addr}")
            forward_traces[addr] = await self.trace_forward(addr, max_depth, start_block, end_block)
        
        # Trace backward from list_b
        backward_traces = {}
        print("\n📥 Backward tracing (List B):")
        for idx, addr in enumerate(list_b, 1):
            print(f"[{idx}/{len(list_b)}] {addr}")
            backward_traces[addr] = await self.trace_backward(addr, max_depth, start_block, end_block)
        
        # Find intersections
        print("\n🔎 Finding intersections...")
        for addr_a, forward_set in forward_traces.items():
            for addr_b, backward_set in backward_traces.items():
                overlap = forward_set & backward_set
                if overlap:
                    results['connections_found'].append({
                        'source': addr_a,
                        'target': addr_b,
                        'meeting_points': sorted(list(overlap)),
                        'path_count': len(overlap)
                    })
        
        results['total_addresses_examined'] = sum(len(s) for s in forward_traces.values()) + \
                                             sum(len(s) for s in backward_traces.values())
        
        if results['connections_found']:
            results['status'] = 'connected'
        else:
            results['status'] = 'no_connection'
        
        return results


# ============================================================================
# FILE: export_manager.py
# ============================================================================
import csv
import json
from pathlib import Path
from typing import Dict, List, Any, Tuple
from datetime import datetime
from config import EXPORT_DIR

class ExportManager:
    """Handles CSV and JSON exports"""
    
    def __init__(self, export_dir: str = EXPORT_DIR):
        self.export_dir = Path(export_dir)
        self.export_dir.mkdir(exist_ok=True)
    
    def export_to_csv(self, results: Dict[str, Any], session_id: str) -> str:
        """Export to CSV format"""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        csv_file = self.export_dir / f"connections_{session_id}_{timestamp}.csv"
        
        with open(csv_file, 'w', newline='', encoding='utf-8') as f:
            writer = csv.writer(f)
            writer.writerow(['Source', 'Target', 'Meeting Points', 'Path Count'])
            
            for conn in results.get('connections_found', []):
                writer.writerow([
                    conn['source'],
                    conn['target'],
                    '|'.join(conn['meeting_points']),
                    conn['path_count']
                ])
        
        print(f"✅ CSV saved: {csv_file}")
        return str(csv_file)
    
    def export_to_json(self, results: Dict[str, Any], session_id: str) -> str:
        """Export to JSON format"""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        json_file = self.export_dir / f"connections_{session_id}_{timestamp}.json"
        
        with open(json_file, 'w', encoding='utf-8') as f:
            json.dump(results, f, indent=2)
        
        print(f"✅ JSON saved: {json_file}")
        return str(json_file)
    
    def export_both(self, results: Dict[str, Any], session_id: str) -> Tuple[str, str]:
        """Export to both formats"""
        csv_path = self.export_to_csv(results, session_id)
        json_path = self.export_to_json(results, session_id)
        return csv_path, json_path


# ============================================================================
# FILE: main.py
# ============================================================================
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
```

## Usage Example

```bash
# 1. Install dependencies
pip install -r requirements.txt

# 2. Start server
python main.py

# 3. Start tracing
curl -X POST http://localhost:8000/trace \\
  -H "Content-Type: application/json" \\
  -d '{
    "list_a": ["1A1z7agoat4FqCnf4Xy7jJn1eJd7azHXzA"],
    "list_b": ["1dice8EMCQAqQwSnBHWNNNNNNN9h7qL5g"],
    "max_depth": 5,
    "start_block": 700000,
    "end_block": 750000
  }'

# 4. Check status
curl http://localhost:8000/status/{session_id}

# 5. Get results
curl http://localhost:8000/results/{session_id}
```
