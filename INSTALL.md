# LinkFinder - Bitcoin Address Linker

LinkFinder is a tool for tracing connections between sets of Bitcoin addresses. It uses a local ElectrumX server (or other providers) to explore the blockchain transaction graph.

## Prerequisites

1. **Python 3.8+** installed.
2. **Virtual Environment** (recommended):
   ```bash
   python3 -m venv venv
   source venv/bin/activate  # On Windows: venv\Scripts\activate
   ```
3. **Dependencies**:
   ```bash
   pip install -r requirements.txt
   ```
4. **ElectrumX Server**: You need access to an ElectrumX server (default: `100.94.34.56`). Update `config.py` or `.env` if needed.

## Quick Start

You need to run two separate components: the **API Backend** and the **Streamlit UI**. Open two terminal windows.

### 1. Start the API Backend (Terminal 1)

This runs the core logic and API server.

```bash
# Make sure your virtual environment is activated
source venv/bin/activate

# Run the backend
python main.py
```

You should see output indicating the server is running on `http://0.0.0.0:8000`.

### 2. Start the Streamlit UI (Terminal 2)

This runs the web interface.

```bash
# Make sure your virtual environment is activated
source venv/bin/activate

# Run the UI
streamlit run streamlit_ui.py
```

This will automatically open your default web browser to `http://localhost:8501`.

## Using the GUI

The interface is divided into three main tabs:

### 1. New Trace (Start Here)
- **List A**: Enter the starting Bitcoin addresses (one per line).
- **List B**: Enter the target Bitcoin addresses (one per line).
- **Max Depth**: How many "hops" (transactions) to search (default: 5).
- **Start/End Block**: (Optional) Limit search to a specific block range.
- Click **Start Trace** to begin.

### 2. Active Sessions
- View the status of all running and completed traces.
- **Running**: Shows progress. You can click "Stop" to cancel.
- **Completed**: Click "Results" to view the found connections (JSON format) or download exports.
- **Latest Checkpoint Progress**: Shows real-time stats of the active trace (addresses examined, etc.).

### 3. Checkpoints & Recovery
- If a trace stops or is cancelled, it saves a checkpoint.
- View all available checkpoints.
- Click **Resume Latest** to continue the most recent trace from where it left off.
- Click **Resume** on a specific checkpoint to restart that session.

## Configuration

Key settings in `config.py` or `.env`:

- `ELECTRUMX_HOST`: IP address of your ElectrumX server (default: `100.94.34.56`).
- `ELECTRUMX_PORT`: Port (default: `50001`).
- `ELECTRUMX_USE_SSL`: Set to `true` if using SSL (port 50002).

## Troubleshooting

- **"Server timeout" in UI**: Ensure `main.py` is running in the other terminal.
- **Connection Refused**: Check if your ElectrumX server IP is correct in `config.py`. Run `python test_connectivity.py` to verify.
- **No transactions found**: The server might be syncing. Run `python test_connectivity.py` to check status.

