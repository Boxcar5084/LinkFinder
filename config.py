# -*- coding: utf-8 -*-

import os
from pathlib import Path
from enum import Enum

# Load .env file if it exists (for persistent settings)
try:
    from dotenv import load_dotenv
    load_dotenv(override=True)
except ImportError:
    pass  # python-dotenv not installed, use environment variables only

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
DEFAULT_API = os.getenv("DEFAULT_API", "mempool")

BLOCKCHAIR_API_URL = "https://api.blockchair.com/bitcoin"
BLOCKCHAIN_API_URL = "https://blockchain.info"
MEMPOOL_API_URL = "https://mempool.space/api"

# API Keys
MEMPOOL_API_KEY = os.getenv("MEMPOOL_API_KEY", "")

# ElectrumX Configuration (Electrum protocol over TCP/SSL)
ELECTRUMX_HOST = os.getenv("ELECTRUMX_HOST", "100.94.34.56")
ELECTRUMX_PORT = int(os.getenv("ELECTRUMX_PORT", "50001"))
ELECTRUMX_USE_SSL = os.getenv("ELECTRUMX_USE_SSL", "false").lower() == "true"
ELECTRUMX_CERT = os.getenv("ELECTRUMX_CERT", None)  # Optional: path to SSL certificate
ELECTRUMX_DEBUG = os.getenv("ELECTRUMX_DEBUG", "false").lower() == "true"  # Verbose debug logging

# SSH Configuration for ElectrumX log access
SSH_HOST = os.getenv("SSH_HOST", None)  # SSH server hostname/IP (may differ from ELECTRUMX_HOST)
SSH_USER = os.getenv("SSH_USER", None)  # SSH username
SSH_KEY_PATH = os.getenv("SSH_KEY_PATH", None)  # Optional: path to SSH private key
SSH_PORT = int(os.getenv("SSH_PORT", "22"))  # SSH port
ELECTRUMX_DOCKER_CONTAINER = os.getenv("ELECTRUMX_DOCKER_CONTAINER", "electrumx")  # Docker container name

# Legacy electrs config (deprecated - will be removed)
ELECTRS_LOCAL_URL = "tcp://100.94.34.56:50001"  # Deprecated
ELECTRS_HOST = "100.94.34.56"  # Deprecated
ELECTRS_PORT = 50001  # Deprecated


MIXER_INPUT_THRESHOLD = int(os.getenv("MIXER_INPUT_THRESHOLD", "30"))          # Min inputs to be considered "mixer-like"  100-100-50
MIXER_OUTPUT_THRESHOLD = int(os.getenv("MIXER_OUTPUT_THRESHOLD", "30"))         # Min outputs to be considered "mixer-like"  50-50-20
SUSPICIOUS_RATIO_THRESHOLD = int(os.getenv("SUSPICIOUS_RATIO_THRESHOLD", "10"))     # Input:output or output:input ratio to flag  30-30-10

# Transaction filtering thresholds
SKIP_MIXER_INPUT_THRESHOLD = int(os.getenv("SKIP_MIXER_INPUT_THRESHOLD", "50"))           # Min inputs for extreme mixer
SKIP_MIXER_OUTPUT_THRESHOLD = int(os.getenv("SKIP_MIXER_OUTPUT_THRESHOLD", "50"))          # Min outputs for extreme mixer

# Airdrop/Distribution detection (MOST IMPORTANT!)
SKIP_DISTRIBUTION_MAX_INPUTS = int(os.getenv("SKIP_DISTRIBUTION_MAX_INPUTS", "2"))          # Max inputs to trigger filter
SKIP_DISTRIBUTION_MIN_OUTPUTS = int(os.getenv("SKIP_DISTRIBUTION_MIN_OUTPUTS", "100"))       # Min outputs to trigger filter

MAX_TRANSACTIONS_PER_ADDRESS = int(os.getenv("MAX_TRANSACTIONS_PER_ADDRESS", "50"))
MAX_DEPTH = int(os.getenv("MAX_DEPTH", "10"))

# Exchange wallet detection
EXCHANGE_WALLET_THRESHOLD = int(os.getenv("EXCHANGE_WALLET_THRESHOLD", "1000"))  # Addresses with more than this many transactions are considered exchange wallets

# Input/Output address filtering
MAX_INPUT_ADDRESSES_PER_TX = int(os.getenv("MAX_INPUT_ADDRESSES_PER_TX", "50"))  # Maximum input addresses to process per transaction (prevents queue flooding)
MAX_OUTPUT_ADDRESSES_PER_TX = int(os.getenv("MAX_OUTPUT_ADDRESSES_PER_TX", "50"))  # Maximum output addresses to process per transaction (prevents queue flooding)

# Large transaction filtering
MAX_TRANSACTION_SIZE_MB = float(os.getenv("MAX_TRANSACTION_SIZE_MB", "1.0"))  # Maximum transaction size in MB before skipping (default: 1MB)

# Cache management
CACHE_MAX_SIZE_MB = 2048           # Maximum cache size in MB
CACHE_PRUNE_TARGET = 0.7           # Prune to 70% of max (leaves 30% buffer)
CACHE_SINGLE_ENTRY_LIMIT_MB = 100  # Max size for single entry (skip if larger)

# Alternative: Disable cache entirely for huge datasets
DISABLE_CACHE = False              # Set to True to disable caching
USE_CACHE = os.getenv("USE_CACHE", "true").lower() == "true"  # Enable/disable cache (default: enabled)
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