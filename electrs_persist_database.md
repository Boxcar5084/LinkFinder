# Preventing electrs Index Restart on Docker Container Restart

## Problem
Every time the electrs Docker container restarts, indexing starts from scratch. This happens because the database/index files are not persisted in a Docker volume.

## Quick Check: Is Your Data Persisted?

If you already have a volume mount in your docker-compose.yml like:
```yaml
volumes:
  - "C:\\BitcoinCore\\electrs-data:/data"
```

Your data **should** be persisted, but indexing might still restart due to:
1. Database directory doesn't exist or is empty
2. Database corruption
3. Wrong database path configuration
4. Permission issues

**Run this diagnostic on your Windows host:**
```bash
python check_electrs_persistence.py
```

This will check if the volume mount is working and if the database exists.

## Solution: Persist Database in Docker Volume

### Step 1: Create a Persistent Volume

Create a named volume or bind mount for the electrs database:

**Option A: Named Volume (Recommended)**
```bash
docker volume create electrs-data
```

**Option B: Bind Mount (More Control)**
```bash
mkdir -p ~/electrs-data
```

### Step 2: Update Docker Configuration

#### Using docker-compose.yml:

```yaml
version: '3.8'

services:
  electrs:
    image: ghcr.io/romanz/electrs:latest
    container_name: electrs
    restart: unless-stopped
    network_mode: "host"  # or bridge with port mapping
    volumes:
      # CRITICAL: Mount the database directory
      - electrs-data:/data  # Named volume
      # OR for bind mount:
      # - ~/electrs-data:/data
      
      # Mount config file (optional but recommended)
      - ./electrs.toml:/data/electrs.toml:ro
    environment:
      - ELECTRS_CONFIG=/data/electrs.toml
    # Resource limits
    deploy:
      resources:
        limits:
          cpus: '2'
          memory: 4G

volumes:
  electrs-data:  # Named volume declaration
```

#### Using docker run:

**With named volume:**
```bash
docker run -d \
  --name electrs \
  --restart unless-stopped \
  --network host \
  -v electrs-data:/data \
  -v /path/to/electrs.toml:/data/electrs.toml:ro \
  -e ELECTRS_CONFIG=/data/electrs.toml \
  ghcr.io/romanz/electrs:latest
```

**With bind mount:**
```bash
docker run -d \
  --name electrs \
  --restart unless-stopped \
  --network host \
  -v ~/electrs-data:/data \
  -v /path/to/electrs.toml:/data/electrs.toml:ro \
  -e ELECTRS_CONFIG=/data/electrs.toml \
  ghcr.io/romanz/electrs:latest
```

### Step 3: Verify Database Location in electrs.toml

Ensure your `electrs.toml` specifies the correct database directory:

```toml
# Database configuration
db_dir = "/data"  # Must match the volume mount path inside container
```

### Step 4: Check Current Setup

**Check if volume is mounted:**
```bash
docker inspect electrs | grep -A 10 Mounts
```

**Check database location:**
```bash
docker exec electrs ls -la /data
```

You should see files like:
- `mainnet/` directory (or testnet/signet)
- Database files inside that directory

### Step 5: Migrate Existing Data (If Needed)

If you already have an electrs container running without a volume:

1. **Stop the container:**
   ```bash
   docker stop electrs
   ```

2. **Copy data from container to host:**
   ```bash
   # Create destination directory
   mkdir -p ~/electrs-data
   
   # Copy data from container
   docker cp electrs:/data ~/electrs-data-backup
   ```

3. **Remove old container:**
   ```bash
   docker rm electrs
   ```

4. **Start new container with volume:**
   ```bash
   docker run -d \
     --name electrs \
     --restart unless-stopped \
     --network host \
     -v ~/electrs-data:/data \
     -v /path/to/electrs.toml:/data/electrs.toml:ro \
     -e ELECTRS_CONFIG=/data/electrs.toml \
     ghcr.io/romanz/electrs:latest
   ```

5. **Restore data (if needed):**
   ```bash
   cp -r ~/electrs-data-backup/* ~/electrs-data/
   ```

6. **Restart container:**
   ```bash
   docker restart electrs
   ```

## Verification

After setting up the volume:

1. **Check that database persists:**
   ```bash
   # Note the current block height
   python monitor_electrs.py
   
   # Restart container
   docker restart electrs
   
   # Wait a few seconds, then check again
   python monitor_electrs.py
   ```

   The block height should be the same (or higher if it continued indexing), not reset to 0.

2. **Check database files:**
   ```bash
   # For named volume
   docker volume inspect electrs-data
   
   # For bind mount
   ls -lh ~/electrs-data/mainnet/
   ```

   You should see database files that persist between restarts.

## Troubleshooting

### Issue: Database still resets after restart

**Check:**
1. Volume is actually mounted:
   ```bash
   docker inspect electrs | grep Mounts -A 20
   ```

2. Database directory exists and has files:
   ```bash
   docker exec electrs ls -la /data/mainnet/
   ```

3. Permissions are correct:
   ```bash
   docker exec electrs ls -la /data
   ```

### Issue: "Permission denied" errors

**Fix:**
```bash
# For bind mount, fix permissions
sudo chown -R 1000:1000 ~/electrs-data
# Or use the UID/GID from the container
docker exec electrs id
```

### Issue: Database location mismatch

**Check electrs.toml:**
```toml
db_dir = "/data"  # Must match volume mount
```

**Verify in container:**
```bash
docker exec electrs cat /data/electrs.toml | grep db_dir
```

## Best Practices

1. **Use named volumes** for easier management
2. **Backup the volume** periodically:
   ```bash
   docker run --rm -v electrs-data:/data -v $(pwd):/backup \
     alpine tar czf /backup/electrs-backup-$(date +%Y%m%d).tar.gz -C /data .
   ```

3. **Monitor disk space** - electrs database can grow large (50-100GB+)
4. **Set restart policy** to `unless-stopped` so it auto-restarts

## Quick Setup Script

```bash
#!/bin/bash
# Quick setup for persistent electrs database

# Create data directory
mkdir -p ~/electrs-data

# Create electrs.toml if it doesn't exist
if [ ! -f ~/electrs-data/electrs.toml ]; then
    cat > ~/electrs-data/electrs.toml << EOF
network = "mainnet"
daemon_rpc_addr = "127.0.0.1:8332"
electrum_rpc_addr = "0.0.0.0:50001"
db_dir = "/data"
max_connections = 100
log_filters = "INFO"
EOF
fi

# Stop and remove existing container
docker stop electrs 2>/dev/null
docker rm electrs 2>/dev/null

# Start with persistent volume
docker run -d \
  --name electrs \
  --restart unless-stopped \
  --network host \
  -v ~/electrs-data:/data \
  -e ELECTRS_CONFIG=/data/electrs.toml \
  ghcr.io/romanz/electrs:latest

echo "electrs started with persistent database at ~/electrs-data"
echo "Monitor with: docker logs -f electrs"
```

Save this as `setup_electrs_persistent.sh`, make it executable (`chmod +x setup_electrs_persistent.sh`), and run it.

