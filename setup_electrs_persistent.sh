#!/bin/bash
# Quick setup script for persistent electrs database
# This prevents indexing from restarting on container restart

set -e

echo "=========================================="
echo "electrs Persistent Database Setup"
echo "=========================================="
echo ""

# Configuration
DATA_DIR="${HOME}/electrs-data"
CONFIG_FILE="${DATA_DIR}/electrs.toml"

# Create data directory
echo "1. Creating data directory: ${DATA_DIR}"
mkdir -p "${DATA_DIR}"

# Create electrs.toml if it doesn't exist
if [ ! -f "${CONFIG_FILE}" ]; then
    echo "2. Creating default electrs.toml"
    cat > "${CONFIG_FILE}" << 'EOF'
network = "mainnet"
daemon_rpc_addr = "127.0.0.1:8332"
electrum_rpc_addr = "0.0.0.0:50001"
db_dir = "/data"
max_connections = 100
max_subscriptions = 100
daemon_timeout = 30
daemon_poll_interval = 10
index_batch_size = 10000
index_lookup_limit = 100000
log_filters = "INFO"
EOF
    echo "   Created ${CONFIG_FILE}"
    echo "   ⚠️  Please edit this file to match your setup!"
else
    echo "2. Using existing electrs.toml: ${CONFIG_FILE}"
fi

# Check if container exists
if docker ps -a --format '{{.Names}}' | grep -q "^electrs$"; then
    echo ""
    echo "3. Stopping existing electrs container..."
    docker stop electrs 2>/dev/null || true
    
    # Ask about data migration
    echo ""
    read -p "   Do you want to copy existing data to persistent volume? (y/n) " -n 1 -r
    echo
    if [[ $REPLY =~ ^[Yy]$ ]]; then
        echo "   Copying data from container..."
        docker cp electrs:/data "${DATA_DIR}-backup" 2>/dev/null || echo "   No existing data to copy"
    fi
    
    echo "   Removing old container..."
    docker rm electrs 2>/dev/null || true
else
    echo "3. No existing container found"
fi

# Start new container with persistent volume
echo ""
echo "4. Starting electrs with persistent volume..."
docker run -d \
  --name electrs \
  --restart unless-stopped \
  --network host \
  -v "${DATA_DIR}:/data" \
  -e ELECTRS_CONFIG=/data/electrs.toml \
  ghcr.io/romanz/electrs:latest

if [ $? -eq 0 ]; then
    echo ""
    echo "=========================================="
    echo "✓ electrs started successfully!"
    echo "=========================================="
    echo ""
    echo "Database location: ${DATA_DIR}"
    echo ""
    echo "Useful commands:"
    echo "  Monitor logs:    docker logs -f electrs"
    echo "  Check status:    docker ps | grep electrs"
    echo "  Check progress:  python monitor_electrs.py"
    echo "  View database:   ls -lh ${DATA_DIR}/mainnet/"
    echo ""
    echo "The database will now persist between container restarts!"
else
    echo ""
    echo "=========================================="
    echo "✗ Failed to start electrs"
    echo "=========================================="
    echo ""
    echo "Check the error above and try again."
    exit 1
fi

