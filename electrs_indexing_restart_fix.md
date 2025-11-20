# Fixing electrs Indexing Restart Issue

## The Problem

Your RocksDB log shows the database **is being recovered**:
```
Recovered from manifest file:/data/bitcoin/MANIFEST-000005 succeeded
```

But indexing **still restarts** when the container restarts. This means:
- ✅ Database files are persisted (RocksDB recovery works)
- ❌ Indexing state is NOT persisted (electrs restarts indexing)

## Why This Happens

electrs stores two types of data:
1. **RocksDB Database** - Transaction/address data (persisted ✅)
2. **Indexing State** - Progress tracking (NOT persisted ❌)

When electrs starts, it:
1. Recovers the RocksDB database ✅
2. Checks if indexing is complete
3. If incomplete or state missing → **restarts indexing** ❌

## Common Causes

### 1. Indexing State Not Saved
electrs may store indexing progress in memory or a separate file that's not in the persisted volume.

### 2. Incomplete Index Detection
electrs detects the index is incomplete and restarts to ensure consistency.

### 3. Version Mismatch
electrs version changed, requiring a reindex (database format incompatible).

### 4. Corruption Detection
electrs detects corruption and restarts indexing to rebuild.

## Solutions

### Solution 1: Check for Indexing State Files

Run this to find indexing state files:
```powershell
docker exec electrs find /data -name '*index*' -o -name '*state*' -o -name '*progress*' 2>/dev/null
```

If you find files, ensure they're in the persisted volume (`/data`).

### Solution 2: Check Startup Logs

Restart electrs and immediately check logs:
```powershell
docker restart electrs
docker logs -f electrs | Select-String -Pattern "resuming|continuing|starting|indexing" -Context 2
```

Look for:
- ✅ **"Resuming index"** or **"Continuing index"** = Good (using existing state)
- ❌ **"Starting index"** or **"Initializing index"** = Bad (restarting)

### Solution 3: Check Database Completeness

The database might be incomplete. Check if indexing ever completed:

```powershell
# Check logs for completion message
docker logs electrs | Select-String -Pattern "complete|finished|done" -Context 1
```

If indexing never completed, electrs will restart each time.

### Solution 4: Verify Umbrel Image Behavior

The `getumbrel/electrs` image might handle persistence differently. Check:

1. **Umbrel Documentation** - May have specific persistence requirements
2. **Environment Variables** - May need additional variables for state persistence
3. **Data Directory Structure** - Indexing state might be in a different location

### Solution 5: Check for Corruption

Look for corruption errors in logs:
```powershell
docker logs electrs | Select-String -Pattern "corrupt|invalid|error|fail" -Context 2
```

If corruption is detected, electrs will restart indexing.

### Solution 6: Monitor Database Size

Track database size before and after restart:

**Before restart:**
```powershell
docker exec electrs du -sh /data/bitcoin
```

**After restart (wait 1 minute):**
```powershell
docker exec electrs du -sh /data/bitcoin
```

If size resets to small, indexing is restarting.

### Solution 7: Check electrs Configuration

The Umbrel image might need specific configuration. Check if there's an `electrs.toml` that needs to be mounted:

```yaml
volumes:
  - "C:\\BitcoinCore\\electrs-data:/data"
  - "C:\\BitcoinCore\\electrs-config:/config:ro"  # If config needed
```

## Diagnostic Script

Run the diagnostic script to identify the issue:

```powershell
python diagnose_indexing_restart.py
```

This will check:
- Startup behavior (resume vs restart)
- Database state
- Environment variables
- Possible solutions

## Expected Behavior

**When working correctly:**
1. Container starts
2. RocksDB recovers database ✅
3. electrs checks indexing state
4. **Resumes** from last position ✅
5. Continues indexing from where it left off ✅

**Current behavior (problem):**
1. Container starts
2. RocksDB recovers database ✅
3. electrs checks indexing state
4. **Starts fresh** (state missing/incomplete) ❌
5. Restarts indexing from block 0 ❌

## Quick Test

To verify if indexing is restarting:

1. **Note current block height:**
   ```powershell
   python monitor_electrs.py
   ```
   Example: `Current height: 500,000 blocks`

2. **Restart container:**
   ```powershell
   docker restart electrs
   ```

3. **Wait 30 seconds, check again:**
   ```powershell
   python monitor_electrs.py
   ```

4. **Compare:**
   - ✅ **Same or higher** = Indexing resumed (working!)
   - ❌ **Much lower (near 0)** = Indexing restarted (problem!)

## If Nothing Works

If indexing always restarts:

1. **Let it complete once** - Don't restart until indexing finishes
2. **Check Umbrel docs** - Image-specific persistence requirements
3. **Consider different image** - Try `ghcr.io/romanz/electrs:latest` instead
4. **Check Docker logs** - Look for specific error messages

## Next Steps

1. Run `diagnose_indexing_restart.py` to identify the issue
2. Check startup logs for "resuming" vs "starting" messages
3. Verify indexing state files are in persisted volume
4. Check if indexing ever completed (might be restarting because incomplete)

