# Fix: electrs Indexing State Not Persisted

## Problem Identified

Your diagnostic shows:
- **ELECTRS_DB_DIR = `/data`** ✅ (correct)
- **Database at `/data/bitcoin`** ✅ (electrs auto-creates this)
- **Database files exist** ✅ (46 files found)
- **But indexing restarts** ❌ (state not persisted)

**The issue:** electrs stores indexing progress/state separately from the RocksDB database. Even though the database is persisted, the indexing state is not, causing electrs to restart indexing on each container restart.

## Understanding electrs Data Storage

electrs stores two types of data:
1. **RocksDB Database** (`/data/bitcoin/`) - Transaction/address data ✅ Persisted
2. **Indexing State** - Progress tracking ❌ NOT Persisted

When electrs starts:
1. Recovers RocksDB database ✅
2. Checks indexing state
3. If state missing/incomplete → **restarts indexing** ❌

## Step-by-Step Diagnosis

### 1. Check for Indexing State Files

Find where indexing state might be stored:
```powershell
docker exec electrs find /data -name '*index*' -o -name '*state*' -o -name '*progress*' 2>$null
docker exec electrs find / -name '*index*' -o -name '*state*' 2>$null | Select-String -Pattern "/data"
```

### 2. Check if Indexing Ever Completed

Look for completion messages in logs:
```powershell
docker logs electrs 2>&1 | Select-String -Pattern "complete|finished|done|ready" -Context 2
```

If indexing never completed, electrs will restart each time.

### 3. Check Startup Behavior

Restart and immediately check logs:
```powershell
docker restart electrs
Start-Sleep -Seconds 5
docker logs electrs --tail 50 | Select-String -Pattern "resuming|continuing|starting|initializing|indexing" -Context 1
```

Look for:
- ✅ **"Resuming index"** or **"Continuing index"** = Good
- ❌ **"Starting index"** or **"Initializing index"** = Bad (restarting)

### 4. Monitor Block Height

Check if indexing resumes:
```powershell
# Note current height
python monitor_electrs.py

# Restart
docker restart electrs

# Wait 30 seconds, check again
python monitor_electrs.py
```

If height is **same or higher** = ✅ Resuming!
If height resets to **near 0** = ❌ Restarting

## Why This Happens

electrs automatically creates `/data/bitcoin` for the database, which is correct. However:

1. **Indexing state is separate** - Stored in memory or a separate file
2. **State not persisted** - Lost on container restart
3. **Incomplete index detection** - electrs sees incomplete index and restarts
4. **Version mismatch** - Database format changed, requires reindex

## Possible Solutions

### Solution 1: Let Indexing Complete Once

**Don't restart the container** until indexing finishes:
```powershell
# Monitor until complete
python monitor_electrs.py

# Wait for "Indexing complete!" message
# Then restart - should resume
```

### Solution 2: Check Umbrel Image Behavior

The `getumbrel/electrs` image might:
- Store indexing state in a different location
- Require specific environment variables
- Have different persistence behavior

Check Umbrel documentation for persistence requirements.

### Solution 3: Check for Indexing State in Database

Indexing state might be in the RocksDB database itself. Check if database is complete:
```powershell
# Check database size (should be several GB when complete)
docker exec electrs du -sh /data/bitcoin
```

If database is small (< 1GB), indexing hasn't progressed far.

### Solution 4: Check for Corruption

Look for corruption errors:
```powershell
docker logs electrs 2>&1 | Select-String -Pattern "corrupt|invalid|error|fail" -Context 2
```

Corruption causes electrs to restart indexing.

## Verification Commands

1. **Check database exists:**
   ```powershell
   docker exec electrs ls -la /data/bitcoin | Select-String -Pattern "MANIFEST|\.sst"
   ```
   Should show MANIFEST and .sst files.

2. **Check database size:**
   ```powershell
   docker exec electrs du -sh /data/bitcoin
   ```
   Should be several GB if indexed.

3. **Check environment:**
   ```powershell
   docker exec electrs env | Select-String -Pattern "DB_DIR"
   ```
   Should show `ELECTRS_DB_DIR=/data` (correct)

4. **Check startup logs:**
   ```powershell
   docker logs electrs 2>&1 | Select-Object -First 50 | Select-String -Pattern "database|index|resume|start|recover"
   ```

## Expected Behavior

**Current behavior (problem):**
- Container starts
- electrs recovers RocksDB database ✅
- Checks indexing state
- State missing/incomplete ❌
- Starts indexing from block 0 ❌

**Desired behavior:**
- Container starts
- electrs recovers RocksDB database ✅
- Finds indexing state ✅
- Resumes indexing from last position ✅

## Most Likely Cause

**Indexing state is stored in the RocksDB database itself**, but electrs checks if the index is **complete**. If incomplete, it restarts to ensure consistency.

This means:
- Database is persisted ✅
- But if index is incomplete → electrs restarts indexing ❌
- **Solution:** Let indexing complete once, then it should resume on restart ✅

## Recommended Solution

**Let indexing complete without restarting:**

1. **Monitor progress:**
   ```powershell
   python monitor_electrs.py
   ```

2. **Don't restart container** until you see:
   - Progress reaches 100%
   - "Indexing complete" message
   - Database size stops growing

3. **After completion, restart:**
   ```powershell
   docker restart electrs
   ```

4. **Verify it resumes:**
   ```powershell
   # Should show same or higher block height
   python monitor_electrs.py
   ```

## If It Still Doesn't Work

1. **Check MANIFEST files exist:**
   ```powershell
   docker exec electrs find /data/bitcoin -name "MANIFEST-*"
   ```

2. **Check database size:**
   ```powershell
   docker exec electrs du -sh /data/bitcoin
   ```
   Should be several GB if indexed.

3. **Check permissions:**
   ```powershell
   docker exec electrs ls -la /data/bitcoin | Select-Object -First 5
   ```
   Files should be readable/writable.

4. **Check electrs version:**
   ```powershell
   docker exec electrs electrs --version
   ```
   Version change might require reindex.

5. **Check Umbrel-specific behavior:**
   - Review Umbrel electrs documentation
   - May need different environment variables
   - Indexing state might be in a different location

