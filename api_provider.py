# -*- coding: utf-8 -*-
import requests
import asyncio
import time
import hashlib
from typing import List, Dict, Optional, Any
from abc import ABC, abstractmethod
from config import DEFAULT_API, MEMPOOL_API_KEY
import socket
import json

# For address to scripthash conversion
try:
    import base58
    HAS_BASE58 = True
except ImportError:
    HAS_BASE58 = False
    print("[ELECTRUMX] Warning: base58 library not installed. Install with: pip install base58")

# For SSL support
try:
    import ssl
    HAS_SSL = True
except ImportError:
    HAS_SSL = False
    print("[ELECTRUMX] Warning: ssl module not available")


class APIProvider(ABC):
    """Base class for blockchain data providers"""

    @abstractmethod
    async def get_address_transactions(self, address: str,
                                     start_block: Optional[int] = None,
                                     end_block: Optional[int] = None) -> List[Dict[str, Any]]:
        """Fetch transactions for an address"""
        pass

    @abstractmethod
    async def close(self):
        """Cleanup resources"""
        pass

class BlockchainInfoProvider(APIProvider):
    """Blockchain.info API provider with rate limit retry logic"""

    def __init__(self):
        self.base_url = "https://blockchain.info"
        self.timeout = 30

    async def get_address_transactions(self, address: str,
                                     start_block: Optional[int] = None,
                                     end_block: Optional[int] = None) -> List[Dict[str, Any]]:
        """Fetch transactions from blockchain.info with retry on 429"""
        url = f"{self.base_url}/address/{address}?format=json"
        max_retries = 5
        retry_delay = 10  # Start with 10 seconds

        for attempt in range(max_retries):
            try:
                await asyncio.sleep(1.0)  # Rate limiting delay
                response = requests.get(url, timeout=self.timeout, headers={
                    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'
                })

                # Check for rate limit (429)
                if response.status_code == 429:
                    wait_time = retry_delay * (2 ** attempt)  # Exponential backoff
                    print(f" [WAIT] Rate limited (429). Waiting {wait_time}s before retry...")
                    await asyncio.sleep(wait_time)
                    continue

                # Check for other errors
                response.raise_for_status()

                data = response.json()

                # Extract transactions
                txs = data.get('txs', [])

                if not txs:
                    print(f" No transactions found for {address}")
                    return []

                # Filter by block range if specified
                if start_block or end_block:
                    filtered_txs = []
                    for tx in txs:
                        block_height = tx.get('block_height')

                        # Skip if block_height is None (unconfirmed)
                        if block_height is None or block_height == 0:
                            continue

                        # Check if in range
                        if start_block and block_height < start_block:
                            continue

                        if end_block and block_height > end_block:
                            continue

                        filtered_txs.append(tx)

                    txs = filtered_txs

                print(f" [OK] Found {len(txs)} transactions")
                return txs

            except requests.exceptions.Timeout:
                print(f" [WAIT] Timeout. Attempt {attempt + 1}/{max_retries}")
                if attempt < max_retries - 1:
                    await asyncio.sleep(retry_delay)
                continue

            except requests.exceptions.HTTPError as e:
                if response.status_code == 429:
                    # Already handled above
                    continue
                print(f" [ERR] HTTP error: {e}")
                return []

            except requests.exceptions.RequestException as e:
                print(f" [ERR] API error: {str(e)[:100]}")
                return []

            except Exception as e:
                print(f" [ERR] Error: {str(e)[:100]}")
                return []

        print(f" [ERR] Max retries exceeded for {address}")
        return []

    async def close(self):
        """Cleanup"""
        pass


class MempoolProvider(APIProvider):
    """Mempool.space API provider with rate limit retry logic"""

    def __init__(self, api_key: str = None):
        self.base_url = "https://mempool.space/api"
        self.timeout = 30
        self.api_key = api_key if api_key else MEMPOOL_API_KEY

    async def get_address_transactions(self, address: str,
                                     start_block: Optional[int] = None,
                                     end_block: Optional[int] = None) -> List[Dict[str, Any]]:
        """Fetch transactions from Mempool.space with retry logic"""
        url = f"{self.base_url}/address/{address}/txs"
        
        # Retry configuration for Mempool
        max_retries = 5
        retry_delay = 5  # Start with 5 seconds (Mempool is more generous than blockchain.info)

        for attempt in range(max_retries):
            try:
                await asyncio.sleep(0.5)  # Rate limiting delay

                headers = {
                    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'
                }
                if self.api_key:
                    headers['X-Mempool-Key'] = self.api_key

                response = requests.get(url, timeout=self.timeout, headers=headers)

                # Check for rate limit (429)
                if response.status_code == 429:
                    wait_time = retry_delay * (2 ** attempt)  # Exponential backoff
                    print(f" [WAIT] Rate limited (429). Waiting {wait_time}s before retry...")
                    await asyncio.sleep(wait_time)
                    continue

                # Check for other HTTP errors
                if response.status_code == 404:
                    print(f" [WARN] Address not found: {address}")
                    return []

                # Better error handling for server errors
                if response.status_code >= 500:
                    if attempt < max_retries - 1:
                        wait_time = retry_delay * (2 ** attempt)
                        print(f" [WAIT] Server error ({response.status_code}). Waiting {wait_time}s before retry...")
                        await asyncio.sleep(wait_time)
                        continue
                    else:
                        print(f" [ERR] Server error: {response.status_code}")
                        return []

                response.raise_for_status()

                txs = response.json()

                if not isinstance(txs, list):
                    print(f" Invalid response format from Mempool")
                    return []

                if not txs:
                    print(f" No transactions found for {address}")
                    return []

                # Filter by block range if specified
                if start_block or end_block:
                    filtered_txs = []
                    for tx in txs:
                        block_height = tx.get('status', {}).get('block_height')

                        if block_height is None:
                            continue

                        if start_block and block_height < start_block:
                            continue

                        if end_block and block_height > end_block:
                            continue

                        filtered_txs.append(tx)

                    txs = filtered_txs

                print(f" [OK] Found {len(txs)} transactions")
                return txs

            except requests.exceptions.Timeout:
                # Retry on timeout
                print(f" [WAIT] Timeout. Attempt {attempt + 1}/{max_retries}")
                if attempt < max_retries - 1:
                    await asyncio.sleep(retry_delay)
                continue

            except requests.exceptions.ConnectionError as e:
                # Retry on connection errors
                print(f" [WAIT] Connection error. Attempt {attempt + 1}/{max_retries}: {str(e)[:50]}")
                if attempt < max_retries - 1:
                    wait_time = retry_delay * (2 ** attempt)
                    await asyncio.sleep(wait_time)
                continue

            except requests.exceptions.HTTPError as e:
                if response.status_code == 429:
                    # Already handled above
                    continue
                print(f" [ERR] HTTP error: {e}")
                return []

            except requests.exceptions.RequestException as e:
                print(f" [ERR] Mempool error: {str(e)[:100]}")
                # Retry on generic request exceptions
                if attempt < max_retries - 1:
                    print(f" Retrying... Attempt {attempt + 2}/{max_retries}")
                    await asyncio.sleep(retry_delay)
                    continue
                return []

            except Exception as e:
                print(f" [ERR] Error: {str(e)[:100]}")
                return []

        print(f" [ERR] Max retries exceeded for {address}")
        return []

    async def close(self):
        """Cleanup"""
        pass

class ElectrumXProvider(APIProvider):
    """ElectrumX server provider using Electrum protocol (JSON-RPC over TCP/SSL)"""
    
    def __init__(self, host: str = None, port: int = None, use_ssl: bool = None, cert: str = None):
        from config import ELECTRUMX_HOST, ELECTRUMX_PORT, ELECTRUMX_USE_SSL, ELECTRUMX_CERT
        self.host = host if host is not None else ELECTRUMX_HOST
        self.port = port if port is not None else ELECTRUMX_PORT
        self.use_ssl = use_ssl if use_ssl is not None else ELECTRUMX_USE_SSL
        self.cert = cert if cert is not None else ELECTRUMX_CERT
        self.timeout = 30
        self.request_id = 0
        self._connection_pool = None  # For future connection pooling
        self._server_version = None  # Cached server version
    
    def _address_to_scripthash(self, address: str) -> Optional[str]:
        """
        Convert Bitcoin address to Electrum scripthash.
        Scripthash = SHA256(script) reversed, hex-encoded
        
        For P2PKH addresses (starting with 1):
        - Decode base58 to get hash160
        - Create script: OP_DUP OP_HASH160 <hash160> OP_EQUALVERIFY OP_CHECKSIG
        - SHA256 the script, reverse bytes, hex encode
        """
        if not HAS_BASE58:
            return None
            
        try:
            # Decode base58 address
            decoded = base58.b58decode(address)
            
            # Extract the hash160 (20 bytes) from decoded address
            # Address format: version (1 byte) + hash160 (20 bytes) + checksum (4 bytes)
            if len(decoded) >= 21:
                hash160 = decoded[1:21]  # Skip version byte, take 20 bytes
                
                # Create script: OP_DUP OP_HASH160 <hash160> OP_EQUALVERIFY OP_CHECKSIG
                # For P2PKH: 76a914<hash160>88ac
                script_bytes = bytes([0x76, 0xa9, 0x14]) + hash160 + bytes([0x88, 0xac])
                
                # SHA256 of script
                sha256_hash = hashlib.sha256(script_bytes).digest()
                
                # Reverse bytes and hex encode (Electrum format)
                scripthash = sha256_hash[::-1].hex()
                
                return scripthash
            else:
                return None
        except Exception as e:
            print(f"[ELECTRUMX] Error converting address to scripthash: {e}")
            return None
    
    async def _negotiate_version(self) -> bool:
        """Negotiate server version with ElectrumX server"""
        if self._server_version is not None:
            return True  # Already negotiated
        
        try:
            # Electrum protocol version negotiation
            # Send server.version request
            result = await self._send_request("server.version", ["linkfinder", "1.0"], timeout=10, max_retries=1)
            if result:
                self._server_version = result
                print(f"[ELECTRUMX] Server version: {result}")
                return True
            return False
        except Exception as e:
            print(f"[ELECTRUMX] Version negotiation failed: {e}")
            return False
    
    async def _send_request(self, method: str, params: list, timeout: Optional[int] = None, max_retries: int = 3) -> Dict[str, Any]:
        """Send a JSON-RPC request to ElectrumX over TCP/SSL with improved response handling and retry logic"""
        self.request_id += 1
        
        request = {
            "jsonrpc": "2.0",
            "method": method,
            "params": params,
            "id": self.request_id
        }
        
        request_timeout = timeout if timeout is not None else self.timeout
        retry_delay = 2  # Start with 2 seconds
        
        for attempt in range(max_retries):
            sock = None
            sock = None
            try:
                if attempt > 0:
                    print(f"[ELECTRUMX] Retry attempt {attempt + 1}/{max_retries}...")
                    await asyncio.sleep(retry_delay * attempt)  # Exponential backoff
                
                # Create socket with SSL support
                if self.use_ssl and HAS_SSL:
                    print(f"[ELECTRUMX] Connecting to {self.host}:{self.port} (SSL)...")
                    # Create SSL context
                    context = ssl.create_default_context()
                    if self.cert:
                        context.load_verify_locations(self.cert)
                    else:
                        context.check_hostname = False
                        context.verify_mode = ssl.CERT_NONE
                    
                    # Create TCP socket first
                    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
                    sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
                    sock.settimeout(request_timeout)
                    sock.connect((self.host, self.port))
                    # Wrap with SSL
                    sock = context.wrap_socket(sock, server_hostname=self.host)
                else:
                    print(f"[ELECTRUMX] Connecting to {self.host}:{self.port} (TCP)...")
                    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
                    sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
                    sock.settimeout(request_timeout)
                    sock.connect((self.host, self.port))
                
                # Send JSON-RPC request
                message = json.dumps(request) + "\n"
                sock.sendall(message.encode('utf-8'))
                
                # Read response - Electrum protocol uses newline-delimited JSON
                # Read until we get a complete line (JSON object)
                response_data = b""
                buffer = b""
                start_time = time.time()
                
                while (time.time() - start_time) < request_timeout:
                    try:
                        sock.settimeout(2)  # Short timeout for each recv
                        chunk = sock.recv(4096)
                        if not chunk:
                            # Connection closed
                            break
                        
                        buffer += chunk
                        
                        # Check if we have a complete line (newline-delimited JSON)
                        if b'\n' in buffer:
                            # Split by newline and take the first complete message
                            parts = buffer.split(b'\n', 1)
                            response_data = parts[0]
                            buffer = parts[1] if len(parts) > 1 else b""
                            break
                        
                        # If buffer gets too large, something's wrong
                        if len(buffer) > 100000:  # 100KB limit
                            print("[ELECTRUMX] Response buffer too large, possible malformed response")
                            break
                            
                    except socket.timeout:
                        # If we have some data, try to use it
                        if buffer:
                            response_data = buffer
                            buffer = b""
                            break
                        # Continue waiting if no data yet
                        continue
                
                # Properly close the connection
                if sock:
                    try:
                        # Shutdown before close for clean connection termination
                        if hasattr(sock, 'shutdown'):
                            sock.shutdown(socket.SHUT_RDWR)
                    except (OSError, socket.error):
                        # Ignore errors if already closed
                        pass
                    finally:
                        sock.close()
                        sock = None
                
                # Parse response
                if not response_data:
                    if attempt < max_retries - 1:
                        print(f"[ELECTRUMX] Empty response, will retry...")
                        continue
                    print("[ELECTRUMX] Empty response from server after retries")
                    return {}
                
                try:
                    response_text = response_data.decode('utf-8').strip()
                    response = json.loads(response_text)
                    
                    if "error" in response and response["error"]:
                        error_msg = response["error"].get("message", str(response["error"]))
                        # Don't retry on RPC errors (they're not transient)
                        print(f"[ELECTRUMX] RPC error: {error_msg}")
                        return {}
                    
                    return response.get("result", {})
                except json.JSONDecodeError as e:
                    if attempt < max_retries - 1:
                        print(f"[ELECTRUMX] JSON decode error, will retry: {e}")
                        continue
                    print(f"[ELECTRUMX] JSON decode error: {e}")
                    print(f"[ELECTRUMX] Response was: {response_data[:200]}")
                    return {}
            
            except socket.timeout:
                if sock:
                    try:
                        if hasattr(sock, 'shutdown'):
                            sock.shutdown(socket.SHUT_RDWR)
                    except:
                        pass
                    sock.close()
                if attempt < max_retries - 1:
                    print(f"[ELECTRUMX] Socket timeout, will retry...")
                    continue
                print(f"[ELECTRUMX] Socket timeout after {request_timeout}s (all retries exhausted)")
                return {}
            except ConnectionRefusedError:
                if sock:
                    try:
                        if hasattr(sock, 'shutdown'):
                            sock.shutdown(socket.SHUT_RDWR)
                    except:
                        pass
                    sock.close()
                if attempt < max_retries - 1:
                    print(f"[ELECTRUMX] Connection refused, will retry...")
                    continue
                print(f"[ELECTRUMX] Connection refused to {self.host}:{self.port}")
                return {}
            except Exception as e:
                if sock:
                    try:
                        if hasattr(sock, 'shutdown'):
                            sock.shutdown(socket.SHUT_RDWR)
                    except:
                        pass
                    sock.close()
                if attempt < max_retries - 1:
                    print(f"[ELECTRUMX] Error (will retry): {str(e)[:100]}")
                    continue
                print(f"[ELECTRUMX] Socket error: {str(e)[:100]}")
                return {}
        
        # All retries exhausted
        return {}
    
    def _convert_electrum_tx_to_mempool_format(self, tx_data: Any, tx_hash: str, height: int) -> Dict[str, Any]:
        """
        Convert Electrum protocol transaction format to Mempool format (vout/vin with scriptpubkey_address)
        
        Electrum protocol's blockchain.transaction.get can return:
        - Hex string (if verbose=False) - we can't parse this without a Bitcoin library
        - Parsed dict (if verbose=True) - format varies by ElectrumX version
        
        We convert to Mempool format which BitcoinAddressLinker expects:
        - vout[].scriptpubkey_address
        - vin[].prevout.scriptpubkey_address
        """
        try:
            # Initialize the transaction object
            tx_obj = {
                "txid": tx_hash,
                "hash": tx_hash,
                "status": {
                    "block_height": height if height > 0 else None,
                    "confirmed": height > 0
                },
                "vin": [],
                "vout": []
            }
            
            # If tx_data is a string (hex), we can't parse it easily
            if isinstance(tx_data, str):
                print(f"[ELECTRUMX] Warning: Received hex transaction for {tx_hash[:16]}..., cannot extract addresses")
                return tx_obj
            
            # If tx_data is a dict (parsed transaction)
            if isinstance(tx_data, dict):
                # Check if it's already in Mempool-compatible format
                if "vout" in tx_data and "vin" in tx_data:
                    # Already has vout/vin, ensure format matches
                    tx_obj["vin"] = tx_data.get("vin", [])
                    tx_obj["vout"] = tx_data.get("vout", [])
                    
                    # Ensure vout has scriptpubkey_address
                    for vout in tx_obj["vout"]:
                        if "scriptpubkey_address" not in vout:
                            # Try to get from alternative fields
                            vout["scriptpubkey_address"] = (
                                vout.get("address") or
                                vout.get("scriptPubKey", {}).get("address") if isinstance(vout.get("scriptPubKey"), dict) else None or
                                None
                            )
                    
                    # Ensure vin has prevout.scriptpubkey_address
                    for vin in tx_obj["vin"]:
                        if "prevout" not in vin:
                            vin["prevout"] = {}
                        if "scriptpubkey_address" not in vin.get("prevout", {}):
                            # Try to get from alternative fields
                            vin["prevout"]["scriptpubkey_address"] = (
                                vin.get("address") or
                                vin.get("prevout", {}).get("address") or
                                vin.get("scriptPubKey", {}).get("address") if isinstance(vin.get("scriptPubKey"), dict) else None or
                                None
                            )
                    
                    return tx_obj
                
                # Electrum might return in different format - try to convert
                if "inputs" in tx_data or "outputs" in tx_data:
                    # Convert from Electrum format
                    if "inputs" in tx_data:
                        for inp in tx_data["inputs"]:
                            vin_entry = {
                                "txid": inp.get("prevout_hash", ""),
                                "vout": inp.get("prevout_n", 0),
                                "prevout": {}
                            }
                            # Try to get address from various possible fields
                            address = (inp.get("address") or 
                                      inp.get("prevout", {}).get("address") if isinstance(inp.get("prevout"), dict) else None or
                                      inp.get("scriptpubkey_address"))
                            if address:
                                vin_entry["prevout"]["scriptpubkey_address"] = address
                            if "value" in inp:
                                vin_entry["prevout"]["value"] = inp["value"]
                            tx_obj["vin"].append(vin_entry)
                    
                    if "outputs" in tx_data:
                        for idx, out in enumerate(tx_data["outputs"]):
                            vout_entry = {
                                "value": out.get("value", 0),
                                "n": idx
                            }
                            # Try to get address from various possible fields
                            address = (out.get("address") or 
                                      out.get("scriptpubkey_address") or
                                      (out.get("script_pubkey", {}).get("address") if isinstance(out.get("script_pubkey"), dict) else None))
                            if address:
                                vout_entry["scriptpubkey_address"] = address
                            tx_obj["vout"].append(vout_entry)
                    
                    return tx_obj
            
            # If we get here, we couldn't parse the format
            print(f"[ELECTRUMX] Warning: Unknown transaction format for {tx_hash[:16]}...")
            return tx_obj
            
        except Exception as e:
            print(f"[ELECTRUMX] Error converting transaction format: {e}")
            # Return minimal format as fallback
            return {
                "txid": tx_hash,
                "hash": tx_hash,
                "status": {"block_height": height if height > 0 else None},
                "vin": [],
                "vout": []
            }
    
    async def get_address_transactions(self, address: str,
                                      start_block: Optional[int] = None,
                                      end_block: Optional[int] = None) -> List[Dict[str, Any]]:
        """Fetch transactions from ElectrumX using Electrum protocol with full transaction details"""
        
        try:
            # Negotiate version on first connection
            if self._server_version is None:
                await self._negotiate_version()
            
            # Convert address to scripthash
            scripthash = self._address_to_scripthash(address)
            
            if not scripthash:
                print(f"[ELECTRUMX] Could not convert address {address} to scripthash")
                print(f"[ELECTRUMX] Install base58 library: pip install base58")
                return []
            
            # Step 1: Get transaction history (list of tx hashes)
            history = await self._send_request("blockchain.scripthash.get_history", [scripthash])
            
            if not history or not isinstance(history, list):
                print(f"[ELECTRUMX] No transactions found for {address}")
                return []
            
            print(f"[ELECTRUMX] Found {len(history)} transaction entries")
            
            # Step 2: Filter by block range and collect tx hashes
            tx_hashes_to_fetch = []
            for entry in history:
                tx_hash = entry.get("tx_hash")
                height = entry.get("height", 0)
                
                # Filter by block range if specified
                if start_block and height > 0 and height < start_block:
                    continue
                if end_block and height > 0 and height > end_block:
                    continue
                
                tx_hashes_to_fetch.append((tx_hash, height))
            
            print(f"[ELECTRUMX] Fetching full details for {len(tx_hashes_to_fetch)} transactions")
            
            # Step 3: Fetch full transaction details for each
            transactions = []
            for idx, (tx_hash, height) in enumerate(tx_hashes_to_fetch):
                try:
                    # Fetch full transaction using blockchain.transaction.get
                    # Try with verbose parameter first (ElectrumX supports this)
                    # If that fails, try without verbose (returns hex, which we can't parse)
                    tx_data = await self._send_request("blockchain.transaction.get", [tx_hash, True])
                    
                    # If that returns empty or error, try without verbose flag
                    if not tx_data or (isinstance(tx_data, str) and len(tx_data) < 100):
                        tx_data = await self._send_request("blockchain.transaction.get", [tx_hash])
                    
                    if tx_data:
                        # Convert to Mempool format
                        tx_obj = self._convert_electrum_tx_to_mempool_format(tx_data, tx_hash, height)
                        transactions.append(tx_obj)
                    else:
                        # Fallback: create minimal transaction object
                        print(f"[ELECTRUMX] Warning: Could not fetch full details for {tx_hash[:16]}...")
                        transactions.append({
                            "txid": tx_hash,
                            "hash": tx_hash,
                            "status": {"block_height": height if height > 0 else None},
                            "vin": [],
                            "vout": []
                        })
                    
                    # Small delay to avoid overwhelming ElectrumX (every 10th transaction)
                    if (idx + 1) % 10 == 0:
                        await asyncio.sleep(0.1)
                    
                except Exception as e:
                    print(f"[ELECTRUMX] Error fetching transaction {tx_hash[:16]}...: {str(e)[:50]}")
                    # Add minimal transaction object as fallback
                    transactions.append({
                        "txid": tx_hash,
                        "hash": tx_hash,
                        "status": {"block_height": height if height > 0 else None},
                        "vin": [],
                        "vout": []
                    })
            
            print(f"[ELECTRUMX] Retrieved {len(transactions)} full transaction details")
            return transactions
        
        except Exception as e:
            print(f"[ELECTRUMX] Error fetching transactions: {str(e)[:100]}")
            return []
    
    async def get_balance(self, address: str) -> Dict[str, Any]:
        """Get balance for an address"""
        try:
            scripthash = self._address_to_scripthash(address)
            if not scripthash:
                return {"confirmed": 0, "unconfirmed": 0}
            
            balance = await self._send_request("blockchain.scripthash.get_balance", [scripthash])
            if balance and isinstance(balance, dict):
                return {
                    "confirmed": balance.get("confirmed", 0),
                    "unconfirmed": balance.get("unconfirmed", 0)
                }
            return {"confirmed": 0, "unconfirmed": 0}
        except Exception as e:
            print(f"[ELECTRUMX] Error getting balance: {e}")
            return {"confirmed": 0, "unconfirmed": 0}
    
    async def get_utxos(self, address: str) -> List[Dict[str, Any]]:
        """Get UTXOs for an address"""
        try:
            scripthash = self._address_to_scripthash(address)
            if not scripthash:
                return []
            
            utxos = await self._send_request("blockchain.scripthash.listunspent", [scripthash])
            if utxos and isinstance(utxos, list):
                return utxos
            return []
        except Exception as e:
            print(f"[ELECTRUMX] Error getting UTXOs: {e}")
            return []
    
    async def broadcast(self, raw_tx: str) -> str:
        """Broadcast a raw transaction to the network"""
        try:
            result = await self._send_request("blockchain.transaction.broadcast", [raw_tx])
            if result and isinstance(result, str):
                return result
            raise Exception(f"Broadcast failed: {result}")
        except Exception as e:
            print(f"[ELECTRUMX] Error broadcasting transaction: {e}")
            raise
    
    async def close(self):
        """Cleanup"""
        pass


def get_provider(provider_name: str = None, api_key: str = None) -> APIProvider:
    """
    Factory function to get the appropriate API provider
    
    Args:
        provider_name: "blockchain", "mempool", "electrumx", or None (uses DEFAULT_API from config)
        api_key: Optional API key (currently only used for Mempool.space)
    
    Returns:
        APIProvider instance
    """
    if provider_name is None:
        provider_name = DEFAULT_API

    provider_name = provider_name.lower().strip()

    if provider_name == "blockchain":
        print("[API] Using Blockchain.info API")
        return BlockchainInfoProvider()

    elif provider_name == "mempool":
        print("[API] Using Mempool.space API")
        return MempoolProvider(api_key=api_key)

    elif provider_name == "electrumx":
        print("[API] Using ElectrumX Node")
        from config import ELECTRUMX_HOST, ELECTRUMX_PORT, ELECTRUMX_USE_SSL, ELECTRUMX_CERT
        return ElectrumXProvider(
            host=ELECTRUMX_HOST,
            port=ELECTRUMX_PORT,
            use_ssl=ELECTRUMX_USE_SSL,
            cert=ELECTRUMX_CERT
        )
    
    elif provider_name == "electrs":
        # Legacy support - map to ElectrumXProvider
        print("[API] WARNING: 'electrs' provider is deprecated, using ElectrumX instead")
        from config import ELECTRUMX_HOST, ELECTRUMX_PORT, ELECTRUMX_USE_SSL, ELECTRUMX_CERT
        return ElectrumXProvider(
            host=ELECTRUMX_HOST,
            port=ELECTRUMX_PORT,
            use_ssl=ELECTRUMX_USE_SSL,
            cert=ELECTRUMX_CERT
        )

    else:
        raise ValueError(f"Unknown provider: {provider_name}. Use 'blockchain', 'mempool', or 'electrumx'")


async def test_provider(provider_name: str = None, test_address: str = "1A1z7agoat4FqCnf4Xy7jJn1eJd7azHXzA"):
    """Quick test of an API provider"""
    provider = get_provider(provider_name)

    print(f"\n[TEST] Testing {provider.__class__.__name__}")
    print(f" Address: {test_address}")

    try:
        txs = await provider.get_address_transactions(test_address)
        print(f" [OK] Success: {len(txs)} transactions")
        if txs:
            print(f" Sample TX: {txs[0].get('hash', txs[0])}")

    except Exception as e:
        print(f" [ERR] Error: {e}")

    finally:
        await provider.close()


# Main test
if __name__ == "__main__":
    import asyncio

    async def main():
        print("Testing all API providers...\n")

        # Test each provider
        for provider in ["blockchain", "mempool", "electrumx"]:
            try:
                await test_provider(provider)
            except Exception as e:
                print(f" [WARN] {provider.upper()} provider error: {e}\n")

    asyncio.run(main())