# Electrs Connection Fix Summary

## Problem
After restarting electrs, the first query works but subsequent queries fail. This is a common issue with electrs in Docker containers.

## Solutions Implemented

### 1. Code Improvements (`api_provider.py`)
- ✅ Added proper socket shutdown before close (prevents connection leaks)
- ✅ Added TCP_NODELAY option (faster response times)
- ✅ Added SO_REUSEADDR option (better connection handling)
- ✅ Improved error handling and retry logic
- ✅ Better connection cleanup

### 2. Diagnostic Tools Created

#### `test_sequential_queries.py`
Tests multiple sequential queries to reproduce the issue:
```bash
python test_sequential_queries.py
```

#### `test_provider_queries.py`
Tests the actual ElectrsProvider with real address queries:
```bash
python test_provider_queries.py
```

#### `check_electrs_docker.py`
Checks Docker configuration and provides recommendations:
```bash
python check_electrs_docker.py
```

### 3. Configuration Files

#### `electrs.toml.example`
Template configuration file with recommended settings.

#### `electrs_config_guide.md`
Complete guide for configuring electrs in Docker.

## Quick Fix Steps

### Step 1: Create/Update electrs.toml

On your server (192.168.7.218), create or update the electrs configuration:

```bash
# Find where electrs data is stored (usually in Docker volume)
# Then create/edit electrs.toml
```

Use the template from `electrs.toml.example` with these critical settings:

```toml
# CRITICAL: Must be 0.0.0.0 (not 127.0.0.1) to allow external connections
electrum_rpc_addr = "0.0.0.0:50001"

# IMPORTANT: Increase connection limit
max_connections = 100  # or higher (200-500)

# Bitcoin Core connection (adjust for your setup)
daemon_rpc_addr = "host.docker.internal:8332"  # For Docker bridge network
# OR
daemon_rpc_addr = "127.0.0.1:8332"  # For Docker host network
```

### Step 2: Update Docker Configuration

If using docker-compose.yml, ensure:

```yaml
services:
  electrs:
    # ... other config ...
    volumes:
      - ./electrs-data:/data
      - ./electrs.toml:/data/electrs.toml:ro  # Mount config file
    environment:
      - ELECTRS_CONFIG=/data/electrs.toml
```

Or if using docker run:

```bash
docker run -d \
  --name electrs \
  --network host \  # OR use bridge with port mapping
  -v /path/to/electrs-data:/data \
  -v /path/to/electrs.toml:/data/electrs.toml:ro \
  -e ELECTRS_CONFIG=/data/electrs.toml \
  ghcr.io/romanz/electrs:latest
```

### Step 3: Restart electrs

```bash
docker restart electrs
```

### Step 4: Test the Fix

Run the diagnostic tools:

```bash
# Test sequential queries
python test_sequential_queries.py

# Test actual provider
python test_provider_queries.py

# Check Docker setup
python check_electrs_docker.py
```

## Common Issues and Solutions

### Issue: "Connection refused" after first query
**Solution**: Increase `max_connections` in electrs.toml (try 100, 200, or 500)

### Issue: "Connection timeout"
**Solution**: 
- Check Bitcoin Core is running: `bitcoin-cli getblockchaininfo`
- Verify network configuration
- Check firewall rules

### Issue: "Too many connections"
**Solution**:
- Increase `max_connections` in electrs.toml
- Check Docker resource limits
- Review electrs logs: `docker logs electrs`

### Issue: Can't connect from outside container
**Solution**: 
- Ensure `electrum_rpc_addr = "0.0.0.0:50001"` (not `127.0.0.1`)
- Check Docker port mapping or use `--network host`
- Verify firewall allows port 50001

## Monitoring

### Check electrs logs:
```bash
docker logs electrs -f
```

### Check connection count:
```bash
netstat -an | grep 50001 | wc -l
```

### Check Docker resources:
```bash
docker stats electrs
```

## Files Created/Modified

1. **api_provider.py** - Improved connection handling
2. **diagnose_electrs.py** - Enhanced diagnostics
3. **test_sequential_queries.py** - Sequential query tester
4. **test_provider_queries.py** - Provider usage tester
5. **check_electrs_docker.py** - Docker configuration checker
6. **electrs_config_guide.md** - Complete configuration guide
7. **electrs.toml.example** - Configuration template
8. **config.py** - Updated with correct host

## Next Steps

1. Copy `electrs.toml.example` to your server and customize it
2. Update your Docker configuration to use the new config file
3. Restart electrs
4. Run the test scripts to verify the fix
5. Monitor electrs logs for any issues

If problems persist, check:
- Bitcoin Core sync status
- Docker resource limits
- Network connectivity
- electrs logs for specific errors

