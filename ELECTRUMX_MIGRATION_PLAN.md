# Migration Plan: electrs → ElectrumX

## Step 1: Discovery Summary

### Application Code Using electrs

#### Core Implementation
- **File**: `api_provider.py`
  - **Class**: `ElectrsProvider` (lines 254-660)
  - **Protocol**: Electrum protocol (JSON-RPC over TCP) ✅
  - **NOT using Esplora HTTP API** ✅
  - **Methods used**:
    - `blockchain.scripthash.get_history` - Get transaction history
    - `blockchain.transaction.get` - Get full transaction details
  - **Connection**: Direct TCP socket connection to `192.168.7.218:50001`
  - **Helper methods**:
    - `_address_to_scripthash()` - Converts Bitcoin address to Electrum scripthash
    - `_send_request()` - Sends JSON-RPC requests over TCP
    - `_convert_electrum_tx_to_mempool_format()` - Converts Electrum format to internal format

#### Configuration
- **File**: `config.py`
  - `ELECTRS_HOST = "192.168.7.218"` (line 31)
  - `ELECTRS_PORT = 50001` (line 32)
  - `ELECTRS_LOCAL_URL = "tcp://192.168.7.218:50001"` (line 30)
  - `DEFAULT_API = "electrs"` (line 25)
  - `APIProvider.ELECTRS = "electrs"` enum value (line 21)

#### Factory Function
- **File**: `api_provider.py` (lines 663-692)
  - `get_provider("electrs")` returns `ElectrsProvider(host="192.168.7.218", port=50001, use_ssl=False)`
  - Hardcoded host/port values

### Infrastructure References

#### Docker/Container References
- **No docker-compose.yml in repo** (user mentioned it's on Windows host at `192.168.7.218`)
- **Diagnostic scripts reference**:
  - `docker exec electrs` commands
  - `getumbrel/electrs:v0.10.10` image
  - Port `50001` (Electrum TCP protocol)

#### Diagnostic/Test Scripts (To be archived later)
- `diagnose_electrs.py` - Electrs connectivity tests
- `test_electrs.py` - Basic electrs connection test
- `monitor_electrs.py` - Monitor electrs indexing progress
- `check_electrs_indexing.py` - Check indexing status
- `check_electrs_docker.py` - Docker configuration checker
- `check_electrs_persistence.py` - Database persistence checker
- `diagnose_indexing_restart.py` - Indexing restart diagnostics
- `test_sequential_queries.py` - Sequential query tests
- `test_provider_queries.py` - Provider usage tests
- `check_electrs_db_usage.ps1` - PowerShell database checker

#### Documentation Files (To be archived later)
- `electrs_config_guide.md`
- `electrs_indexing_restart_fix.md`
- `ELECTRS_INDEXING_STATUS.md`
- `electrs_persist_database.md`
- `fix_electrs_db_path_mismatch.md`
- `fix_electrs_db_path.md`
- `electrs.toml.example`
- `setup_electrs_persistent.sh`
- `archived/ELECTRS_FIX_SUMMARY.md`

### Protocol Usage

✅ **Good News**: The codebase **already uses Electrum protocol** (not Esplora HTTP API)

- Uses JSON-RPC over TCP (port 50001)
- Methods are standard Electrum protocol:
  - `blockchain.scripthash.get_history` ✅
  - `blockchain.transaction.get` ✅
- Both electrs and ElectrumX implement the same Electrum protocol
- **No HTTP/Esplora endpoints** found (e.g., `/api/address`, `/api/tx`)

### Environment Variables Referenced

- `ELECTRS_HOST` (in `config.py`)
- `ELECTRS_PORT` (in `config.py`)
- `ELECTRS_LOCAL_URL` (in `config.py`, not actively used)
- No `.env` file found in repo

### Ports Used

- **50001** - Electrum TCP protocol (standard)
- **50002** - Mentioned in some docs but not used in code (would be SSL)

---

## Step 2: Migration Plan

### Overview

Since the codebase **already uses Electrum protocol**, migration is straightforward:
1. Rename `ElectrsProvider` → `ElectrumXProvider`
2. Update configuration variables
3. Point to ElectrumX host/port
4. Protocol methods remain the same (both implement Electrum protocol)

### Detailed Migration Steps

#### 1. Update Configuration (`config.py`)

**Changes:**
```python
# OLD
ELECTRS_HOST = "192.168.7.218"
ELECTRS_PORT = 50001
ELECTRS_LOCAL_URL = "tcp://192.168.7.218:50001"
DEFAULT_API = "electrs"
APIProvider.ELECTRS = "electrs"

# NEW
ELECTRUMX_HOST = os.getenv("ELECTRUMX_HOST", "192.168.7.218")
ELECTRUMX_PORT = int(os.getenv("ELECTRUMX_PORT", "50001"))
ELECTRUMX_USE_SSL = os.getenv("ELECTRUMX_USE_SSL", "false").lower() == "true"
DEFAULT_API = "electrumx"
APIProvider.ELECTRUMX = "electrumx"
```

**Benefits:**
- Support environment variables for configuration
- Support SSL (port 50002) via `ELECTRUMX_USE_SSL`
- Clear naming

#### 2. Rename Provider Class (`api_provider.py`)

**Changes:**
- Rename `ElectrsProvider` → `ElectrumXProvider`
- Update class docstring
- Update all `[ELECTRS]` log prefixes → `[ELECTRUMX]`
- Update error messages
- Keep all protocol methods the same (they're compatible)

**Methods to keep (no changes needed):**
- `_address_to_scripthash()` - Works with both
- `_send_request()` - Works with both (standard Electrum protocol)
- `_convert_electrum_tx_to_mempool_format()` - Works with both
- `get_address_transactions()` - Uses standard Electrum methods

**Protocol methods used (compatible with ElectrumX):**
- `blockchain.scripthash.get_history` ✅
- `blockchain.transaction.get` ✅

#### 3. Update Factory Function (`api_provider.py`)

**Changes:**
```python
# OLD
elif provider_name == "electrs":
    print("[API] Using Local Electrs Node")
    return ElectrsProvider(host="192.168.7.218", port=50001, use_ssl=False)

# NEW
elif provider_name == "electrumx":
    print("[API] Using ElectrumX Node")
    from config import ELECTRUMX_HOST, ELECTRUMX_PORT, ELECTRUMX_USE_SSL
    return ElectrumXProvider(
        host=ELECTRUMX_HOST, 
        port=ELECTRUMX_PORT, 
        use_ssl=ELECTRUMX_USE_SSL
    )
```

#### 4. Update Default API (`config.py`)

**Change:**
```python
DEFAULT_API = "electrumx"  # Changed from "electrs"
```

#### 5. Add SSL Support (if needed)

**Enhancement:**
- Update `_send_request()` to support SSL connections when `use_ssl=True`
- Use `ssl.wrap_socket()` or `ssl.create_default_context()` for SSL connections
- Default to TCP (port 50001), allow SSL (port 50002) via config

#### 6. Update Test Files (Optional, for verification)

**Files to update:**
- `test_electrs.py` → `test_electrumx.py` (rename and update)
- Update any hardcoded references

#### 7. Archive electrs-Specific Files

**Move to `archived/electrs/` directory:**
- All diagnostic scripts (see list above)
- All documentation files (see list above)
- `electrs.toml.example`
- `setup_electrs_persistent.sh`

### Protocol Compatibility

✅ **Both electrs and ElectrumX implement the same Electrum protocol:**

| Method | electrs | ElectrumX | Status |
|--------|---------|-----------|--------|
| `blockchain.scripthash.get_history` | ✅ | ✅ | Compatible |
| `blockchain.transaction.get` | ✅ | ✅ | Compatible |
| `blockchain.headers.subscribe` | ✅ | ✅ | Compatible |
| `server.ping` | ✅ | ✅ | Compatible |

**No changes needed to protocol calls** - they're already standard Electrum protocol.

### Environment Variables (New)

**Add to `.env` file (or use system env):**
```bash
ELECTRUMX_HOST=192.168.7.218
ELECTRUMX_PORT=50001
ELECTRUMX_USE_SSL=false
```

**For SSL connections:**
```bash
ELECTRUMX_HOST=192.168.7.218
ELECTRUMX_PORT=50002
ELECTRUMX_USE_SSL=true
```

### Testing Plan

1. **Unit Test**: Verify `ElectrumXProvider` can connect to ElectrumX
2. **Integration Test**: Verify `get_address_transactions()` works
3. **Protocol Test**: Verify all Electrum protocol methods work
4. **SSL Test**: If using SSL, verify SSL connection works

### Rollback Plan

If issues arise:
1. Revert `DEFAULT_API = "electrs"` in `config.py`
2. Keep both providers temporarily
3. Use feature flag to switch between them

### Files to Modify

**Core changes:**
1. `api_provider.py` - Rename class, update factory, add SSL support
2. `config.py` - Update config variables, add env var support

**Optional:**
3. `test_electrs.py` → `test_electrumx.py` (rename and update)

**Archive (later):**
4. All diagnostic scripts
5. All documentation files

### Estimated Effort

- **Core migration**: ~2-3 hours
  - Rename class and update references
  - Update configuration
  - Add SSL support (if needed)
  - Testing

- **Cleanup/archiving**: ~1 hour
  - Move diagnostic scripts
  - Move documentation
  - Update any remaining references

---

## Summary

✅ **Good news**: The codebase already uses Electrum protocol, so migration is straightforward.

**Key Points:**
1. No Esplora HTTP API usage found - already using Electrum protocol
2. Protocol methods are compatible between electrs and ElectrumX
3. Main work: Rename class, update config, point to ElectrumX host/port
4. Optional: Add SSL support for port 50002
5. Archive electrs-specific diagnostic/documentation files

**Next Steps:**
1. Confirm this plan
2. Implement core changes (provider rename + config)
3. Test with ElectrumX server
4. Archive electrs-specific files

