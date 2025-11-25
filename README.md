<p align="center">
  <img src="https://img.shields.io/badge/Python-3.8+-3776AB?style=for-the-badge&logo=python&logoColor=white" alt="Python 3.8+">
  <img src="https://img.shields.io/badge/FastAPI-009688?style=for-the-badge&logo=fastapi&logoColor=white" alt="FastAPI">
  <img src="https://img.shields.io/badge/Streamlit-FF4B4B?style=for-the-badge&logo=streamlit&logoColor=white" alt="Streamlit">
  <img src="https://img.shields.io/badge/Bitcoin-F7931A?style=for-the-badge&logo=bitcoin&logoColor=white" alt="Bitcoin">
</p>

<h1 align="center">🔗 LinkFinder</h1>

<p align="center">
  <strong>Bitcoin Address Connection Tracer</strong><br>
  Discover transaction paths between Bitcoin addresses using bidirectional graph traversal
</p>

---

## 📖 Overview

**LinkFinder** is a powerful forensic tool for tracing connections between sets of Bitcoin addresses. Given source addresses (List A) and target addresses (List B), it discovers transaction paths that link them through the blockchain.

### Key Features

- **Bidirectional BFS Algorithm** — Efficiently finds shortest paths by searching from both ends simultaneously
- **Smart Transaction Filtering** — Automatically skips mixers, CoinJoin, airdrops, and exchange wallets
- **Multiple Data Providers** — Supports Mempool.space, Blockchain.info, and self-hosted ElectrumX nodes
- **Persistent Caching** — SQLite-backed transaction cache for faster repeated queries
- **Resumable Sessions** — Checkpoint system allows pausing and resuming long-running traces
- **Real-time Exports** — Connections are exported to CSV/JSON as they're discovered
- **Modern Web UI** — Streamlit-powered interface for easy session management

---

## 🏗️ Architecture

```
┌─────────────────────────────────────────────────────────────────────┐
│                         LinkFinder System                          │
├─────────────────────────────────────────────────────────────────────┤
│                                                                     │
│   ┌─────────────────┐              ┌─────────────────────────────┐ │
│   │   Streamlit UI  │◄────────────►│      FastAPI Backend        │ │
│   │   (Port 8501)   │    HTTP      │        (Port 8000)          │ │
│   └─────────────────┘              └──────────────┬──────────────┘ │
│                                                   │                │
│                                    ┌──────────────┼──────────────┐ │
│                                    │              │              │ │
│                             ┌──────▼─────┐ ┌─────▼──────┐ ┌─────▼┐│
│                             │   Graph    │ │   Cache    │ │Check-││
│                             │   Engine   │ │  Manager   │ │points││
│                             │ (BFS Algo) │ │ (SQLite)   │ │(.pkl)││
│                             └──────┬─────┘ └────────────┘ └──────┘│
│                                    │                               │
│                         ┌──────────┴──────────┐                   │
│                         │    API Providers    │                   │
│                         ├─────────────────────┤                   │
│                         │ • Mempool.space     │                   │
│                         │ • Blockchain.info   │                   │
│                         │ • ElectrumX Node    │                   │
│                         └─────────────────────┘                   │
│                                                                     │
└─────────────────────────────────────────────────────────────────────┘
```

---

## 🚀 Quick Start

### Prerequisites

- **Python 3.8+**
- **pip** (Python package manager)

### Installation

```bash
# Clone the repository
git clone https://github.com/yourusername/linkfinder.git
cd linkfinder

# Create and activate virtual environment
python3 -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt
```

### Running the Application

You need **two terminal windows** — one for the backend API and one for the web UI.

#### Terminal 1: Start the Backend

```bash
source venv/bin/activate
python main.py
```

The API server will start on `http://localhost:8000`

#### Terminal 2: Start the Frontend

```bash
source venv/bin/activate
streamlit run streamlit_ui.py
```

The web UI will open automatically at `http://localhost:8501`

---

## 🖥️ Using the Web Interface

### 1. New Trace Tab

Enter Bitcoin addresses to trace:

| Field | Description |
|-------|-------------|
| **List A** | Source addresses (one per line) |
| **List B** | Target addresses (one per line) |
| **Max Depth** | Maximum transaction hops to search (default: 5) |
| **Start/End Block** | Optional block range filter |

Click **Start Trace** to begin searching for connections.

### 2. Active Sessions Tab

Monitor running and completed traces:

- **Running**: View progress, stop traces, see live checkpoint stats
- **Completed**: View results, download exports, delete sessions
- **Cancelled/Failed**: Resume from checkpoint or delete

### 3. Checkpoints & Recovery Tab

Manage saved checkpoints:

- **Resume Latest**: Continue the most recent trace
- **View All**: Browse all checkpoints with progress details
- **Resume Specific**: Restart from any saved checkpoint

---

## ⚙️ Configuration

### Environment Variables

Copy `env.example` to `.env` and configure:

```bash
# ElectrumX Configuration (for self-hosted node)
ELECTRUMX_HOST=100.94.34.56
ELECTRUMX_PORT=50001
ELECTRUMX_USE_SSL=false

# Default API provider: "mempool", "blockchain", or "electrumx"
DEFAULT_API=mempool
```

### Key Settings in `config.py`

| Setting | Default | Description |
|---------|---------|-------------|
| `DEFAULT_API` | `"mempool"` | Default blockchain data provider |
| `MAX_DEPTH` | `10` | Maximum search depth allowed |
| `MAX_TRANSACTIONS_PER_ADDRESS` | `50` | Limit transactions per address |
| `EXCHANGE_WALLET_THRESHOLD` | `1000` | Skip addresses with more transactions |
| `CACHE_MAX_SIZE_MB` | `2048` | Maximum cache size in MB |

### Transaction Filtering Thresholds

```python
SKIP_MIXER_INPUT_THRESHOLD = 50      # Skip if inputs >= this
SKIP_MIXER_OUTPUT_THRESHOLD = 50     # Skip if outputs >= this
SKIP_DISTRIBUTION_MAX_INPUTS = 2     # Airdrop detection: max inputs
SKIP_DISTRIBUTION_MIN_OUTPUTS = 100  # Airdrop detection: min outputs
```

---

## 📡 API Reference

### Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| `POST` | `/trace` | Start new trace session |
| `GET` | `/status/{session_id}` | Get session status |
| `GET` | `/results/{session_id}` | Get completed results |
| `POST` | `/cancel/{session_id}` | Cancel running trace |
| `POST` | `/resume/auto` | Resume most recent checkpoint |
| `POST` | `/resume/{session_id}/{checkpoint_id}` | Resume specific checkpoint |
| `GET` | `/sessions` | List all sessions |
| `GET` | `/checkpoints/all` | List all checkpoints |
| `GET` | `/cache/stats` | Get cache statistics |

### Example: Start a Trace

```bash
curl -X POST http://localhost:8000/trace \
  -H "Content-Type: application/json" \
  -d '{
    "list_a": ["1A1zP1eP5QGefi2DMPTfTL5SLmv7DivfNa"],
    "list_b": ["bc1qxy2kgdygjrsqtzq2n0yrf2493p83kkfjhx0wlh"],
    "max_depth": 5
  }'
```

### Example: Check Status

```bash
curl http://localhost:8000/status/{session_id}
```

---

## 📁 Project Structure

```
linkfinder/
├── main.py              # FastAPI backend server
├── streamlit_ui.py      # Streamlit web interface
├── graph_engine.py      # Bidirectional BFS algorithm
├── api_provider.py      # Blockchain data providers
├── cache_manager.py     # SQLite transaction cache
├── checkpoint_manager.py # Session checkpoint system
├── export_manager.py    # CSV/JSON export handling
├── config.py            # Configuration settings
├── requirements.txt     # Python dependencies
├── env.example          # Environment template
├── checkpoints/         # Saved session checkpoints
├── exports/             # CSV/JSON export files
└── blockchain_cache.db  # SQLite cache database
```

---

## 🔧 Troubleshooting

### "Server timeout" in UI

**Cause**: Backend is not running or unreachable.

**Solution**: Ensure `python main.py` is running in another terminal.

### "Connection Refused" errors

**Cause**: ElectrumX server unavailable or wrong configuration.

**Solution**: 
1. Check `config.py` for correct `ELECTRUMX_HOST` and `ELECTRUMX_PORT`
2. Run `python test_connectivity.py` to diagnose
3. Try switching to `mempool` provider in `config.py`

### No transactions found

**Cause**: The blockchain data provider may be rate-limiting or the server is syncing.

**Solution**:
1. Wait and retry — rate limits typically reset after a few minutes
2. Check if using ElectrumX: ensure the node is fully synced
3. Run `python test_connectivity.py` to verify provider connectivity

### Cache growing too large

**Cause**: Extended usage accumulates cached transactions.

**Solution**:
1. Delete `blockchain_cache.db` to reset the cache
2. Adjust `CACHE_MAX_SIZE_MB` in `config.py`
3. Run `python clear_cache.py` if available

---

## 🧪 Testing

```bash
# Test API connectivity
python test_connectivity.py

# Test a specific provider
python test_api.py

# Test with a known address
python test_address.py
```

---

## 📄 License

This project is provided as-is for educational and research purposes.

---

## 🤝 Contributing

Contributions are welcome! Please:

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/amazing-feature`)
3. Commit your changes (`git commit -m 'Add amazing feature'`)
4. Push to the branch (`git push origin feature/amazing-feature`)
5. Open a Pull Request

---

<p align="center">
  <strong>LinkFinder</strong> — Trace the untraceable
</p>

