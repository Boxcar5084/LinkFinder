# Bitcoin Address Linker - Quick Start Guide

## What You Have

1. **implementation_guide.md** - Full architecture, design patterns, and best practices
2. **phase1_skeleton.md** - Complete, copy-paste ready code for Phase 1

## Quick Start (5 Minutes)

### Step 1: Clone/Create Project
```bash
mkdir bitcoin-address-linker
cd bitcoin-address-linker
```

### Step 2: Copy Phase 1 Skeleton Code
Create these 6 Python files from `phase1_skeleton.md`:
- `config.py` - Configuration constants
- `api_provider.py` - API abstraction layer
- `cache_manager.py` - Transaction caching
- `checkpoint_manager.py` - Session resumption
- `graph_engine.py` - Address tracing logic
- `main.py` - FastAPI application
- `requirements.txt` - Dependencies
- `export_manager.py` - CSV/JSON export

### Step 3: Install & Run
```bash
pip install -r requirements.txt
python main.py
```

Server runs on http://localhost:8000

## API Usage

### Start Tracing
```bash
curl -X POST http://localhost:8000/trace \
  -H "Content-Type: application/json" \
  -d '{
    "list_a": ["1A1z7agoat4FqCnf4Xy7jJn1eJd7azHXzA"],
    "list_b": ["1dice8EMCQAqQwSnBHWNNNN..."],
    "max_depth": 5,
    "start_block": 700000,
    "end_block": 750000
  }'
```

Response:
```json
{
  "session_id": "abc123...",
  "status": "started"
}
```

### Check Status
```bash
curl http://localhost:8000/status/abc123...
```

### Get Results (When Complete)
```bash
curl http://localhost:8000/results/abc123...
```

## What Happens

1. **Phase 1 (Now)**: Uses external APIs (Mempool.space - free, no auth)
   - Fetches transaction histories
   - Applies common-input heuristic
   - Traces bidirectionally through graph
   - Exports results as CSV + JSON

2. **Phase 2 (After Node Sync)**: Switch to local Electrs
   - Just change `DEFAULT_API = "electrs"` in config.py
   - Same logic, instant local access

## Key Features

✅ Bidirectional address linking  
✅ Common-input ownership heuristic  
✅ Block range filtering  
✅ CoinJoin detection (filters out obfuscated transactions)  
✅ SQLite transaction caching (size-limited)  
✅ Checkpoint/resumable queries  
✅ CSV + JSON export  
✅ API-agnostic design (switch APIs easily)  
✅ Async/concurrent tracing  
✅ Rate limiting built-in  

## Configuration

Edit `config.py` to customize:

```python
MAX_TRANSACTIONS_PER_ADDRESS = 500      # Limit per address
MAX_DEPTH = 5                            # How deep to trace
CACHE_MAX_SIZE_MB = 500                 # Cache size limit
BLOCKCHAIR_RATE_LIMIT = 3               # Requests/sec for Blockchair
```

## Switching APIs

### To Blockchair (if you prefer):
```python
# In main.py
api = get_provider("blockchair")  # Instead of DEFAULT_API
```

### To Local Electrs (Phase 2):
```python
# In config.py
DEFAULT_API = "electrs"
ELECTRS_LOCAL_URL = "http://localhost:50002"
```

Then restart:
```bash
python main.py
```

## File Structure
```
bitcoin-address-linker/
├── config.py              # Settings
├── api_provider.py        # Blockchair/Mempool/Electrs abstraction
├── cache_manager.py       # SQLite transaction cache
├── checkpoint_manager.py  # Session resumption
├── graph_engine.py        # Address tracing algorithm
├── export_manager.py      # CSV/JSON export
├── main.py                # FastAPI server
├── requirements.txt       # Python dependencies
├── checkpoints/           # Auto-created for session recovery
├── exports/               # Auto-created for result exports
└── blockchain_cache.db    # Auto-created SQLite cache
```

## Important Notes

1. **Mempool.space (Phase 1)**: 
   - No authentication required
   - Free tier: No hard rate limits
   - Perfect for initial development

2. **Local Electrs (Phase 2)**:
   - Requires ~400GB disk space
   - Currently syncing (~1 day left)
   - 10x faster after ready
   - Just change config, no code changes

3. **Rate Limiting**:
   - Blockchair: 3 req/sec (built-in backoff)
   - Mempool: No strict limits
   - Electrs local: Unlimited

4. **Caching**:
   - Automatically caches transactions
   - Max 500MB (configurable)
   - Entries expire after 24 hours
   - Prunes oldest entries when limit reached

5. **Resumable Queries**:
   - Queries over 1000+ addresses are slow
   - System auto-checkpoints every 10 addresses traced
   - If connection drops, just re-call with same session_id

## Troubleshooting

### "Connection refused"
- Server not running: `python main.py`
- Wrong port: Check `http://localhost:8000/docs`

### "Rate limited"
- Blockchair: Wait 5 seconds between requests
- Mempool: Should be unlimited, might be other issue

### "Address not found"
- Invalid address format (not 26-35 chars)
- Address has 0 transactions in time period
- Block range doesn't overlap with address activity

### Cache growing too large?
- Reduce `CACHE_MAX_SIZE_MB` in config.py
- Cache auto-prunes oldest 10% when limit reached

### Queries taking forever?
- Reduce `max_depth` (5→3)
- Tighten `start_block`/`end_block` range
- Wait for Phase 2 (local Electrs will be 10x faster)

## Next Steps

1. ✅ Run Phase 1 skeleton now
2. ⏳ While node syncs, optimize your queries
3. 🔄 When Electrs ready, switch to Phase 2 (1-line config change)
4. 📊 Add UI/dashboard for visualization (optional)
5. 🚀 Deploy to production

## Support

See `implementation_guide.md` for:
- Detailed architecture explanation
- Design pattern rationale
- Best practices & optimizations
- Performance tuning guide
- Future enhancement ideas

Good luck with your forensic blockchain analysis! 🔗
