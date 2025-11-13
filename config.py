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
    ELECTRS = "electrs"
    BLOCKCHAIN = "blockchain"

# Configuration
DEFAULT_API = "mempool"  # Start with Mempool (public, no auth)

BLOCKCHAIR_API_URL = "https://api.blockchair.com/bitcoin"
BLOCKCHAIN_API_URL = "https://blockchain.info"
MEMPOOL_API_URL = "https://mempool.space/api"
ELECTRS_LOCAL_URL = "http://localhost:50002"

MAX_TRANSACTIONS_PER_ADDRESS = 50
MAX_DEPTH = 10
CACHE_MAX_SIZE_MB = 2048

# Checkpoint and export directories
CHECKPOINT_DIR = os.path.join(os.getcwd(), "checkpoints")
EXPORT_DIR = os.path.join(os.getcwd(), "exports")

# Create directories if they don't exist
Path(CHECKPOINT_DIR).mkdir(parents=True, exist_ok=True)
Path(EXPORT_DIR).mkdir(parents=True, exist_ok=True)

# Rate limiting (requests per second)
BLOCKCHAIR_RATE_LIMIT = 3
MEMPOOL_RATE_LIMIT = 10