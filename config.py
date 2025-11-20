# -*- coding: utf-8 -*-

import os
from pathlib import Path
from enum import Enum

# Create directories immediately
Path("checkpoints").mkdir(parents=True, exist_ok=True)
Path("exports").mkdir(parents=True, exist_ok=True)

CHECKPOINT_DIR = os.path.join(os.getcwd(), "checkpoints")
EXPORT_DIR = os.path.join(os.getcwd(), "exports")

# Create again to be sure
Path(CHECKPOINT_DIR).mkdir(parents=True, exist_ok=True)
Path(EXPORT_DIR).mkdir(parents=True, exist_ok=True)

class APIProvider(Enum):
    BLOCKCHAIR = "blockchair"
    MEMPOOL = "mempool"
    ELECTRUMX = "electrumx"
    BLOCKCHAIN = "blockchain"
    # Legacy - kept for backwards compatibility during migration
    ELECTRS = "electrs"

# Configuration
DEFAULT_API = "electrumx"  # Default to ElectrumX

BLOCKCHAIR_API_URL = "https://api.blockchair.com/bitcoin"
BLOCKCHAIN_API_URL = "https://blockchain.info"
MEMPOOL_API_URL = "https://mempool.space/api"

# ElectrumX Configuration (Electrum protocol over TCP/SSL)
ELECTRUMX_HOST = os.getenv("ELECTRUMX_HOST", "192.168.7.218")
ELECTRUMX_PORT = int(os.getenv("ELECTRUMX_PORT", "50001"))
ELECTRUMX_USE_SSL = os.getenv("ELECTRUMX_USE_SSL", "false").lower() == "true"
ELECTRUMX_CERT = os.getenv("ELECTRUMX_CERT", None)  # Optional: path to SSL certificate

# Legacy electrs config (deprecated - will be removed)
ELECTRS_LOCAL_URL = "tcp://192.168.7.218:50001"  # Deprecated
ELECTRS_HOST = "192.168.7.218"  # Deprecated
ELECTRS_PORT = 50001  # Deprecated


MIXER_INPUT_THRESHOLD = 30          # Min inputs to be considered "mixer-like"  100-100-50
MIXER_OUTPUT_THRESHOLD = 30         # Min outputs to be considered "mixer-like"  50-50-20
SUSPICIOUS_RATIO_THRESHOLD = 10     # Input:output or output:input ratio to flag  30-30-10

# Transaction filtering thresholds
SKIP_MIXER_INPUT_THRESHOLD = 50           # Min inputs for extreme mixer
SKIP_MIXER_OUTPUT_THRESHOLD = 50          # Min outputs for extreme mixer

# Airdrop/Distribution detection (MOST IMPORTANT!)
SKIP_DISTRIBUTION_MAX_INPUTS = 2          # Max inputs to trigger filter
SKIP_DISTRIBUTION_MIN_OUTPUTS = 100       # Min outputs to trigger filter

MAX_TRANSACTIONS_PER_ADDRESS = 50
MAX_DEPTH = 10

# Cache management
CACHE_MAX_SIZE_MB = 2048           # Maximum cache size in MB
CACHE_PRUNE_TARGET = 0.7           # Prune to 70% of max (leaves 30% buffer)
CACHE_SINGLE_ENTRY_LIMIT_MB = 100  # Max size for single entry (skip if larger)

# Alternative: Disable cache entirely for huge datasets
DISABLE_CACHE = False              # Set to True to disable caching
CACHE_ONLY_ESSENTIAL = False       # Only cache addresses with <5 transactions


# Checkpoint and export directories
CHECKPOINT_DIR = os.path.join(os.getcwd(), "checkpoints")
EXPORT_DIR = os.path.join(os.getcwd(), "exports")

# Create directories if they don't exist
Path(CHECKPOINT_DIR).mkdir(parents=True, exist_ok=True)
Path(EXPORT_DIR).mkdir(parents=True, exist_ok=True)

# Rate limiting (requests per second)
BLOCKCHAIR_RATE_LIMIT = 3
MEMPOOL_RATE_LIMIT = 10