# Fixing electrs Database Path Issue

## Current Situation

Your database files **are being persisted** (I can see them in `C:\BitcoinCore\electrs-data\bitcoin`), but there's a nested directory structure:
- `C:\BitcoinCore\electrs-data\bitcoin\bitcoin\` (nested)

This suggests a path configuration issue.

## The Problem

Your docker-compose.yml has:
```yaml
environment:
  - ELECTRS_DB_DIR=/data/bitcoin
volumes:
  - "C:\\BitcoinCore\\electrs-data:/data"
```

This means:
- Container path: `/data/bitcoin`
- Host path: `C:\BitcoinCore\electrs-data\bitcoin`

But electrs might be creating an additional `bitcoin` subdirectory inside that, resulting in `bitcoin/bitcoin`.

## Solution Options

### Option 1: Change DB_DIR to `/data` (Recommended)

Update your docker-compose.yml:

```yaml
services:
  electrs:
    image: getumbrel/electrs:v0.10.10
    container_name: electrs
    environment:
      - ELECTRS_DAEMON_RPC_ADDR=192.168.7.218:8332
      - ELECTRS_DAEMON_P2P_ADDR=192.168.7.218:8333
      - ELECTRS_ELECTRUM_RPC_ADDR=0.0.0.0:50001
      - ELECTRS_DB_DIR=/data  # Changed from /data/bitcoin
      - ELECTRS_DB_PARALLELISM=4
      - ELECTRS_INDEX_BATCH_SIZE=100
    volumes:
      - "C:\\BitcoinCore\\electrs-data:/data"
      - "C:\\Users\\nicka\\AppData\\Roaming\\Bitcoin:/bitcoin:ro"
    ports:
      - "50001:50001"
    restart: unless-stopped
```

Then electrs will create its database structure directly in `/data` (which maps to `C:\BitcoinCore\electrs-data`).

### Option 2: Move Existing Database

If you want to keep `ELECTRS_DB_DIR=/data/bitcoin`, you need to move the nested database:

**On Windows (PowerShell):**
```powershell
# Stop electrs first
docker stop electrs

# Move the nested database up one level
Move-Item -Path "C:\BitcoinCore\electrs-data\bitcoin\bitcoin\*" -Destination "C:\BitcoinCore\electrs-data\bitcoin\" -Force

# Remove the now-empty nested directory
Remove-Item -Path "C:\BitcoinCore\electrs-data\bitcoin\bitcoin" -Recurse -Force

# Restart electrs
docker start electrs
```

### Option 3: Check What electrs Actually Expects

The Umbrel image might have a default database location. Check the logs:

```powershell
docker logs electrs | Select-String -Pattern "database\|db_dir\|index"
```

This will show where electrs is actually looking for/writing the database.

## Verification Steps

After making changes:

1. **Check the database location:**
   ```powershell
   dir C:\BitcoinCore\electrs-data
   ```

2. **Check electrs logs for database path:**
   ```powershell
   docker logs electrs | Select-String -Pattern "Opening\|database\|index"
   ```

3. **Verify indexing resumes (not restarts):**
   ```powershell
   # Note current block height
   python monitor_electrs.py
   
   # Restart container
   docker restart electrs
   
   # Wait 30 seconds, check again
   python monitor_electrs.py
   ```

   The height should be the same or higher, not reset to 0.

## Why Indexing Might Still Restart

Even with persistence, indexing can restart if:

1. **Database corruption** - Check logs for corruption errors
2. **Version mismatch** - Umbrel image version changed, database format incompatible
3. **Wrong path** - electrs can't find the database, creates new one
4. **Permission issues** - Can't read/write to database files

## Quick Diagnostic

Run this to see what's happening:

```powershell
# Check if database is being used
docker logs electrs | Select-String -Pattern "resuming\|continuing\|starting\|indexing" | Select-Object -Last 10

# Check database file sizes (should be growing if indexing)
Get-ChildItem C:\BitcoinCore\electrs-data\bitcoin -Recurse -File | Measure-Object -Property Length -Sum | Select-Object @{Name="TotalSizeGB";Expression={[math]::Round($_.Sum / 1GB, 2)}}
```

If the total size is several GB and growing, the database is being used. If it's small or not changing, electrs might be creating a new database.

