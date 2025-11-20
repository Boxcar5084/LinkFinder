# Electrs Configuration Guide

## Problem: First Query Works, Subsequent Queries Fail

This is a common issue with electrs in Docker when:
- Connection limits are too low
- Resource limits are restrictive
- Connection handling isn't properly configured

## Electrs Configuration File (electrs.toml)

Create or modify `electrs.toml` in your electrs data directory. Here's a recommended configuration:

```toml
# Network configuration
network = "mainnet"  # or "testnet", "signet", "regtest"

# Server configuration
daemon_rpc_addr = "host.docker.internal:8332"  # For Docker to access host Bitcoin Core
# OR if using host network mode:
# daemon_rpc_addr = "127.0.0.1:8332"

# Electrum RPC server
electrum_rpc_addr = "0.0.0.0:50001"  # Listen on all interfaces (important for Docker!)

# Connection limits (IMPORTANT!)
max_connections = 100  # Increase from default if needed
max_subscriptions = 100

# Timeouts
daemon_timeout = 30
daemon_poll_interval = 10

# Indexing
index_batch_size = 10000
index_lookup_limit = 100000

# Logging
log_filters = "INFO"
```

## Docker Configuration

### docker-compose.yml Example

```yaml
version: '3.8'

services:
  electrs:
    image: ghcr.io/romanz/electrs:latest
    container_name: electrs
    restart: unless-stopped
    network_mode: "host"  # Simplest for accessing host Bitcoin Core
    # OR use bridge network:
    # ports:
    #   - "50001:50001"
    # extra_hosts:
    #   - "host.docker.internal:host-gateway"
    volumes:
      - ./electrs-data:/data
      - ./electrs.toml:/data/electrs.toml:ro
    environment:
      - ELECTRS_CONFIG=/data/electrs.toml
    # Resource limits (adjust as needed)
    deploy:
      resources:
        limits:
          cpus: '2'
          memory: 4G
        reservations:
          cpus: '1'
          memory: 2G
```

### Docker Run Command

```bash
docker run -d \
  --name electrs \
  --network host \
  -v /path/to/electrs-data:/data \
  -v /path/to/electrs.toml:/data/electrs.toml:ro \
  -e ELECTRS_CONFIG=/data/electrs.toml \
  ghcr.io/romanz/electrs:latest
```

## Key Configuration Points

### 1. Network Binding
- **CRITICAL**: Set `electrum_rpc_addr = "0.0.0.0:50001"` (not `127.0.0.1`)
- This allows connections from outside the container

### 2. Connection Limits
- Increase `max_connections` if you see connection refused errors
- Default is often 50, try 100-200

### 3. Bitcoin Core Connection
- If Bitcoin Core is on host: use `host.docker.internal:8332` (bridge network)
- Or use `--network host` in Docker (simpler)

### 4. Resource Limits
- Ensure Docker has enough memory (4GB+ recommended)
- Check with: `docker stats electrs`

## Troubleshooting

### Check electrs logs:
```bash
docker logs electrs -f
```

### Check connection count:
```bash
# On the host
netstat -an | grep 50001 | wc -l
```

### Test from inside container:
```bash
docker exec -it electrs sh
# Then test connection
```

### Verify Bitcoin Core connection:
```bash
# From inside electrs container
nc -zv host.docker.internal 8332
# OR if using host network
nc -zv 127.0.0.1 8332
```

## Common Issues

1. **"Connection refused" after first query**
   - Increase `max_connections` in electrs.toml
   - Check Docker resource limits
   - Verify `electrum_rpc_addr = "0.0.0.0:50001"`

2. **"Connection timeout"**
   - Check Bitcoin Core is running and synced
   - Verify network configuration
   - Check firewall rules

3. **"Too many connections"**
   - Increase `max_connections`
   - Implement connection pooling in client
   - Reduce concurrent requests

## Testing Your Configuration

After updating config, restart electrs:
```bash
docker restart electrs
```

Then test with:
```bash
python test_sequential_queries.py
```

This will show if the connection handling is working properly.

