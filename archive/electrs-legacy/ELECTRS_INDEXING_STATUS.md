# Electrs Indexing Status

## Current Status

**electrs is still indexing the blockchain.**

- **Current height**: ~170,000 blocks
- **Target height**: 924,358 blocks  
- **Progress**: ~18.4%
- **Remaining**: ~754,358 blocks

## Why You're Getting "Unavailable Index" Errors

The error `unavailable index` means:
- electrs is still building its transaction index
- It can only serve queries for blocks it has already indexed
- Address history queries require the full index to be available
- This is **normal** during initial sync

## Estimated Time to Complete

Based on typical indexing speeds:
- **Fast (500 blocks/sec)**: ~0.4 hours (24 minutes)
- **Medium (250 blocks/sec)**: ~0.8 hours (48 minutes)  
- **Slow (100 blocks/sec)**: ~2.1 hours

**Note**: These are rough estimates. Actual time depends on:
- Disk I/O speed (SSD vs HDD)
- CPU performance
- Network speed (if using remote Bitcoin Core)
- System load

## Solutions

### Option 1: Wait for Indexing (Recommended for Long-term)

1. Monitor progress:
   ```bash
   python check_electrs_indexing.py
   ```

2. Check electrs logs:
   ```bash
   docker logs electrs -f
   ```

3. Wait for indexing to complete (usually 1-3 hours)

### Option 2: Use Alternative API Temporarily

While electrs finishes indexing, you can use other APIs:

**Switch to Mempool.space API:**
```python
# In config.py, change:
DEFAULT_API = "mempool"  # Instead of "electrs"
```

**Or use Blockchain.info API:**
```python
DEFAULT_API = "blockchain"  # Instead of "electrs"
```

Then restart your application. The system will use the alternative API until electrs is ready.

### Option 3: Check Indexing Speed

If indexing seems slow, check:

1. **Disk I/O**: Is the database on a fast SSD?
2. **Resource limits**: Check Docker resource allocation
3. **Bitcoin Core sync**: Ensure Bitcoin Core is fully synced
4. **electrs config**: Review `electrs.toml` for performance settings

## Monitoring Progress

Run this periodically to check progress:
```bash
python check_electrs_indexing.py
```

You'll see:
- Current block height
- Progress percentage
- Estimated time remaining

## Once Indexing Completes

When electrs reaches block 924,358:
- ✅ Address queries will work
- ✅ Transaction history will be available
- ✅ You can switch back to `DEFAULT_API = "electrs"` in config.py

## Quick Switch Commands

**Switch to Mempool API:**
```bash
# Edit config.py
sed -i '' 's/DEFAULT_API = "electrs"/DEFAULT_API = "mempool"/' config.py
```

**Switch back to electrs (after indexing):**
```bash
# Edit config.py  
sed -i '' 's/DEFAULT_API = "mempool"/DEFAULT_API = "electrs"/' config.py
```

Or manually edit `config.py` and change line 25.

