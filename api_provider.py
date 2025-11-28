# -*- coding: utf-8 -*-
import requests
import asyncio
import time
import hashlib
from typing import List, Dict, Optional, Any
from abc import ABC, abstractmethod
from config import (
    DEFAULT_API, 
    MEMPOOL_API_KEY,
    MAX_TRANSACTION_SIZE_MB,
    SKIP_MIXER_INPUT_THRESHOLD,
    SKIP_MIXER_OUTPUT_THRESHOLD,
    SKIP_DISTRIBUTION_MAX_INPUTS,
    SKIP_DISTRIBUTION_MIN_OUTPUTS,
    MAX_TRANSACTIONS_PER_ADDRESS,
    EXCHANGE_WALLET_THRESHOLD
)
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
        self._persistent_sock = None  # Persistent connection for reuse
        self._server_version = None  # Cached server version
        self._last_logged_mb = 0  # For progress logging
    
    def _connect(self) -> bool:
        """Establish a persistent connection to ElectrumX server"""
        if self._persistent_sock is not None:
            return True  # Already connected
        
        try:
            # Use same simple socket setup as test_connectivity.py (which works)
            # Note: Don't use persistent connections with ElectrumX - create fresh for each request
            if self.use_ssl and HAS_SSL:
                print(f"[ELECTRUMX] Establishing connection to {self.host}:{self.port} (SSL)...")
                context = ssl.create_default_context()
                if self.cert:
                    context.load_verify_locations(self.cert)
                else:
                    context.check_hostname = False
                    context.verify_mode = ssl.CERT_NONE
                
                sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                sock.settimeout(self.timeout)
                sock.connect((self.host, self.port))
                self._persistent_sock = context.wrap_socket(sock, server_hostname=self.host)
            else:
                print(f"[ELECTRUMX] Establishing connection to {self.host}:{self.port} (TCP)...")
                self._persistent_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                self._persistent_sock.settimeout(self.timeout)
                self._persistent_sock.connect((self.host, self.port))
            
            return True
        except Exception as e:
            print(f"[ELECTRUMX] Failed to establish persistent connection: {e}")
            self._persistent_sock = None
            return False
    
    async def open(self):
        """Initialize provider (connections are created per-request for reliability)"""
        print(f"[ELECTRUMX] Provider ready for {self.host}:{self.port}")
        return True
    
    async def close(self):
        """Cleanup provider (connections are closed per-request automatically)"""
        print(f"[ELECTRUMX] Provider closed")
    
    def _disconnect(self):
        """Close the persistent connection (legacy, kept for compatibility)"""
        pass
    
    def _address_to_scripthash(self, address: str) -> Optional[str]:
        """
        Convert Bitcoin address to Electrum scripthash.
        Scripthash = SHA256(script) reversed, hex-encoded
        
        Supports:
        - P2PKH addresses (starting with 1): version byte 0x00
        - P2SH addresses (starting with 3): version byte 0x05
        - Bech32 addresses (starting with bc1): native SegWit
        """
        if not HAS_BASE58:
            return None
        
        try:
            # Handle Bech32 addresses (bc1...)
            if address.startswith('bc1') or address.startswith('BC1'):
                return self._bech32_to_scripthash(address)
            
            # Decode base58 address (P2PKH or P2SH)
            decoded = base58.b58decode(address)
            
            # Address format: version (1 byte) + hash160 (20 bytes) + checksum (4 bytes)
            if len(decoded) < 21:
                print(f"[ELECTRUMX] Invalid address length: {len(decoded)}")
                return None
            
            version_byte = decoded[0]
            hash160 = decoded[1:21]  # Skip version byte, take 20 bytes
            
            # Create script based on address type
            if version_byte == 0x00:
                # P2PKH (addresses starting with "1")
                # Script: OP_DUP OP_HASH160 <hash160> OP_EQUALVERIFY OP_CHECKSIG
                # Hex: 76a914<hash160>88ac
                script_bytes = bytes([0x76, 0xa9, 0x14]) + hash160 + bytes([0x88, 0xac])
            elif version_byte == 0x05:
                # P2SH (addresses starting with "3")
                # Script: OP_HASH160 <hash160> OP_EQUAL
                # Hex: a914<hash160>87
                script_bytes = bytes([0xa9, 0x14]) + hash160 + bytes([0x87])
            else:
                print(f"[ELECTRUMX] Unknown address version byte: {version_byte:#x}")
                return None
            
            # SHA256 of script
            sha256_hash = hashlib.sha256(script_bytes).digest()
            
            # Reverse bytes and hex encode (Electrum format)
            scripthash = sha256_hash[::-1].hex()
            
            return scripthash
            
        except Exception as e:
            print(f"[ELECTRUMX] Error converting address to scripthash: {e}")
            return None
    
    def _bech32_to_scripthash(self, address: str) -> Optional[str]:
        """
        Convert Bech32 (SegWit) address to Electrum scripthash.
        
        Supports:
        - P2WPKH (bc1q...): 20-byte witness program
        - P2WSH (bc1q... with 32-byte program): 32-byte witness program
        """
        try:
            # Bech32 decoding
            hrp = "bc"  # Bitcoin mainnet
            address_lower = address.lower()
            
            if not address_lower.startswith(hrp + "1"):
                print(f"[ELECTRUMX] Invalid bech32 prefix")
                return None
            
            # Simple bech32 decode - extract the data part
            CHARSET = "qpzry9x8gf2tvdw0s3jn54khce6mua7l"
            data_part = address_lower[len(hrp) + 1:]  # Skip "bc1"
            
            # Convert from bech32 charset to 5-bit values
            values = []
            for char in data_part:
                if char not in CHARSET:
                    print(f"[ELECTRUMX] Invalid bech32 character: {char}")
                    return None
                values.append(CHARSET.index(char))
            
            # Remove checksum (last 6 characters)
            values = values[:-6]
            
            if len(values) < 1:
                return None
            
            # First value is witness version
            witness_version = values[0]
            
            # Convert remaining 5-bit values to 8-bit bytes
            acc = 0
            bits = 0
            witness_program = []
            for value in values[1:]:
                acc = (acc << 5) | value
                bits += 5
                while bits >= 8:
                    bits -= 8
                    witness_program.append((acc >> bits) & 0xff)
            
            witness_program = bytes(witness_program)
            
            # Create script based on witness program length
            if len(witness_program) == 20:
                # P2WPKH: OP_0 <20-byte-key-hash>
                script_bytes = bytes([0x00, 0x14]) + witness_program
            elif len(witness_program) == 32:
                # P2WSH: OP_0 <32-byte-script-hash>
                script_bytes = bytes([0x00, 0x20]) + witness_program
            else:
                print(f"[ELECTRUMX] Unexpected witness program length: {len(witness_program)}")
                return None
            
            # SHA256 of script, reversed
            sha256_hash = hashlib.sha256(script_bytes).digest()
            scripthash = sha256_hash[::-1].hex()
            
            return scripthash
            
        except Exception as e:
            print(f"[ELECTRUMX] Error converting bech32 address: {e}")
            return None
    
    def _validate_jsonrpc_response(self, response: Dict[str, Any], expected_id: Optional[int] = None) -> Tuple[bool, Optional[str]]:
        """
        Validate JSON-RPC response structure (lenient validation for ElectrumX compatibility)
        
        Args:
            response: Parsed JSON response
            expected_id: Expected request ID (optional, not enforced since we use separate connections)
        
        Returns:
            Tuple of (is_valid: bool, error_message: Optional[str])
        """
        if not isinstance(response, dict):
            return False, "Response is not a dictionary"
        
        # Check for either result or error (main requirement)
        has_result = "result" in response
        has_error = "error" in response
        
        if not has_result and not has_error:
            return False, "Response must contain either 'result' or 'error' field"
        
        # Validate error structure if present (lenient - just check it exists)
        if has_error and response["error"] is not None:
            error = response["error"]
            if isinstance(error, dict):
                # Standard error format - log if code/message missing but don't fail
                if "message" not in error:
                    error_msg = str(error)
                    return True, None  # Still valid, just unusual format
            # If error is a string or other type, that's okay too
        
        return True, None
    
    def _validate_transaction_format(self, tx: Dict[str, Any]) -> Tuple[bool, Optional[str]]:
        """
        Validate transaction has required fields for Mempool format
        
        Args:
            tx: Transaction dictionary
        
        Returns:
            Tuple of (is_valid: bool, error_message: Optional[str])
        """
        if not isinstance(tx, dict):
            return False, "Transaction is not a dictionary"
        
        # Required fields
        required_fields = ["txid", "hash", "status"]
        for field in required_fields:
            if field not in tx:
                return False, f"Missing required field: {field}"
        
        # Validate status structure
        status = tx.get("status")
        if not isinstance(status, dict):
            return False, "Status field must be a dictionary"
        
        # Validate vin/vout structure (should be lists)
        if "vin" not in tx:
            return False, "Missing 'vin' field"
        if "vout" not in tx:
            return False, "Missing 'vout' field"
        
        if not isinstance(tx["vin"], list):
            return False, "vin must be a list"
        if not isinstance(tx["vout"], list):
            return False, "vout must be a list"
        
        # Validate vout entries have scriptpubkey_address
        for idx, vout in enumerate(tx["vout"]):
            if not isinstance(vout, dict):
                return False, f"vout[{idx}] is not a dictionary"
            # scriptpubkey_address is optional but preferred
        
        # Validate vin entries
        for idx, vin in enumerate(tx["vin"]):
            if not isinstance(vin, dict):
                return False, f"vin[{idx}] is not a dictionary"
            # prevout is optional but preferred
        
        return True, None
    
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
        """Send a JSON-RPC request to ElectrumX over persistent connection"""
        self.request_id += 1
        # Reset progress logging for this request
        self._last_logged_mb = 0
        
        request = {
            "jsonrpc": "2.0",
            "method": method,
            "params": params,
            "id": self.request_id
        }
        
        request_timeout = timeout if timeout is not None else self.timeout
        retry_delay = 2  # Start with 2 seconds
        
        for attempt in range(max_retries):
            try:
                if attempt > 0:
                    print(f"[ELECTRUMX] Retry attempt {attempt + 1}/{max_retries}...")
                    await asyncio.sleep(retry_delay * attempt)  # Exponential backoff
                # Create a fresh socket for each request (ElectrumX closes idle connections quickly)
                # This matches how test_connectivity.py works - create socket, send, receive, close
                sock = None
                try:
                    if self.use_ssl and HAS_SSL:
                        context = ssl.create_default_context()
                        if self.cert:
                            context.load_verify_locations(self.cert)
                        else:
                            context.check_hostname = False
                            context.verify_mode = ssl.CERT_NONE
                        
                        raw_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                        raw_sock.settimeout(self.timeout)
                        raw_sock.connect((self.host, self.port))
                        sock = context.wrap_socket(raw_sock, server_hostname=self.host)
                    else:
                        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                        sock.settimeout(self.timeout)
                        sock.connect((self.host, self.port))
                except Exception as e:
                    if attempt == 0:
                        print(f"[ELECTRUMX] Connection failed: {e}")
                    if sock:
                        try:
                            sock.close()
                        except:
                            pass
                    continue  # Retry
                
                # Send JSON-RPC request - use exact same format as working test_connectivity.py
                message = json.dumps(request) + "\n"
                
                # Debug: Log what we're sending
                if attempt == 0:  # Only log on first attempt to reduce noise
                    print(f"[ELECTRUMX] Sending request: {method} (id={self.request_id})")
                
                try:
                    # Send immediately (like test_connectivity.py)
                    sock.sendall(message.encode('utf-8'))
                except (BrokenPipeError, OSError) as e:
                    if attempt == 0:
                        print(f"[ELECTRUMX] Error sending request: {e}")
                    try:
                        sock.close()
                    except:
                        pass
                    continue  # Retry
                
                # Read response - Electrum protocol uses newline-delimited JSON
                # Read until we get a complete line (JSON object ending with newline)
                # Use EXACT same approach as test_connectivity.py which works
                response_data = b""
                buffer = b""
                start_time = time.time()
                max_response_size = 50 * 1024 * 1024  # 50MB safety limit
                chunk_size = 4096  # Same as test_connectivity.py
                read_timeout = 10  # Same as test_connectivity.py
                
                while (time.time() - start_time) < read_timeout:
                    try:
                        sock.settimeout(2)  # Same 2s timeout as test_connectivity.py
                        chunk = sock.recv(chunk_size)
                        if not chunk:
                            # Connection closed by server
                            if attempt == 0:
                                print(f"[ELECTRUMX] Server closed connection during read for {method}")
                            break
                        
                        buffer += chunk
                        
                        # Debug: Log first chunk received
                        if attempt == 0 and len(buffer) == len(chunk):
                            print(f"[ELECTRUMX] Received first chunk: {len(chunk)} bytes for {method}")
                        
                        # Check if we have a complete line (newline-delimited JSON)
                        if b'\n' in buffer:
                            # Split by newline and take the first complete message
                            parts = buffer.split(b'\n', 1)
                            response_data = parts[0]
                            buffer = parts[1] if len(parts) > 1 else b""
                            if attempt == 0:
                                print(f"[ELECTRUMX] Received complete response: {len(response_data)} bytes for {method}")
                            break
                        
                        # Safety check: prevent excessive memory usage
                        if len(buffer) > max_response_size:
                            print(f"[ELECTRUMX] Response exceeds maximum size ({max_response_size} bytes)")
                            # Still try to find newline in what we have
                            if b'\n' in buffer:
                                parts = buffer.split(b'\n', 1)
                                response_data = parts[0]
                                buffer = parts[1] if len(parts) > 1 else b""
                            break
                            
                    except socket.timeout:
                        # If we have some data, try to use it (like test_connectivity.py)
                        if buffer:
                            # Check if we have a newline now
                            if b'\n' in buffer:
                                parts = buffer.split(b'\n', 1)
                                response_data = parts[0]
                                buffer = parts[1] if len(parts) > 1 else b""
                                if attempt == 0:
                                    print(f"[ELECTRUMX] Received response on timeout: {len(response_data)} bytes for {method}")
                                break
                            # If we have data but no newline, use it anyway (like test_connectivity.py)
                            response_data = buffer
                            buffer = b""
                            if attempt == 0:
                                print(f"[ELECTRUMX] Using incomplete response: {len(response_data)} bytes for {method}")
                            break
                        # No data yet, continue waiting
                        elapsed = time.time() - start_time
                        if attempt == 0 and elapsed > 2.0:
                            print(f"[ELECTRUMX] Still waiting for response for {method} (elapsed: {elapsed:.1f}s)")
                        continue
                    except (BrokenPipeError, ConnectionResetError, OSError) as e:
                        if attempt == 0:
                            print(f"[ELECTRUMX] Connection error during read for {method}: {e}")
                        break
                
                # If we exited the loop without finding newline but have data, use it
                if not response_data and buffer:
                    response_data = buffer
                    if attempt == 0:
                        print(f"[ELECTRUMX] Using buffer data after loop: {len(response_data)} bytes for {method}")
                
                # Close socket after request (like test_connectivity.py)
                try:
                    sock.close()
                except:
                    pass
                
                # Parse response
                if not response_data:
                    if attempt < max_retries - 1:
                        print(f"[ELECTRUMX] Empty response for {method}, will retry...")
                        continue
                    print(f"[ELECTRUMX] Empty response from server after retries for {method}")
                    return {}
                
                try:
                    response_text = response_data.decode('utf-8').strip()
                    
                    # Debug: Check if response looks valid
                    if not response_text.startswith('{'):
                        print(f"[ELECTRUMX] WARNING: Response doesn't start with '{{': {response_text[:200]}")
                    
                    # Debug: Log first bad response to understand the issue
                    if len(response_text) < 100 and '"error"' not in response_text and '"result"' not in response_text:
                        print(f"[ELECTRUMX] DEBUG: Short/unusual response for {method}: {response_text[:500]}")
                    
                    response = json.loads(response_text)
                    
                    # Validate JSON-RPC response structure
                    is_valid, validation_error = self._validate_jsonrpc_response(response, self.request_id)
                    if not is_valid:
                        if attempt < max_retries - 1:
                            print(f"[ELECTRUMX] Invalid JSON-RPC response, will retry: {validation_error}")
                            continue
                        print(f"[ELECTRUMX] Invalid JSON-RPC response: {validation_error}")
                        print(f"[ELECTRUMX] Response was: {response_text[:200]}")
                        return {}
                    
                    # Check for error response
                    if "error" in response and response["error"]:
                        error_data = response["error"]
                        error_code = error_data.get("code", "unknown")
                        error_msg = error_data.get("message", str(error_data))
                        # Don't retry on RPC errors (they're not transient)
                        print(f"[ELECTRUMX] RPC error [{error_code}]: {error_msg}")
                        return {}
                    
                    # Return result
                    result = response.get("result", {})
                    return result
                    
                except json.JSONDecodeError as e:
                    if attempt < max_retries - 1:
                        print(f"[ELECTRUMX] JSON decode error, will retry: {e}")
                        continue
                    print(f"[ELECTRUMX] JSON decode error: {e}")
                    print(f"[ELECTRUMX] Response was: {response_data[:200]}")
                    return {}
            
            except socket.timeout:
                # Ensure socket is closed
                if sock:
                    try:
                        sock.close()
                    except:
                        pass
                if attempt < max_retries - 1:
                    print(f"[ELECTRUMX] Socket timeout, will retry...")
                    continue
                print(f"[ELECTRUMX] Socket timeout after {request_timeout}s (all retries exhausted)")
                return {}
            except ConnectionRefusedError:
                if sock:
                    try:
                        sock.close()
                    except:
                        pass
                if attempt < max_retries - 1:
                    print(f"[ELECTRUMX] Connection refused, will retry...")
                    continue
                print(f"[ELECTRUMX] Connection refused to {self.host}:{self.port}")
                return {}
            except (BrokenPipeError, ConnectionResetError, OSError) as e:
                if sock:
                    try:
                        sock.close()
                    except:
                        pass
                if attempt < max_retries - 1:
                    print(f"[ELECTRUMX] Connection lost, will retry: {str(e)[:50]}")
                    continue
                print(f"[ELECTRUMX] Connection error: {str(e)[:100]}")
                return {}
            except Exception as e:
                if sock:
                    try:
                        sock.close()
                    except:
                        pass
                if attempt < max_retries - 1:
                    print(f"[ELECTRUMX] Error (will retry): {str(e)[:100]}")
                    continue
                print(f"[ELECTRUMX] Socket error: {str(e)[:100]}")
                return {}
        
        # All retries exhausted
        return {}
    
    def _should_skip_large_transaction(self, tx_data: Any, response_size_bytes: int = 0) -> bool:
        """
        Check if a transaction should be skipped based on size or input/output counts.
        This prevents wasting resources on large transactions that would be filtered anyway.
        
        Args:
            tx_data: Raw transaction data from ElectrumX (dict or str)
            response_size_bytes: Size of the response in bytes (if available)
        
        Returns:
            True if transaction should be skipped, False otherwise
        """
        # Check response size if available
        if response_size_bytes > 0:
            size_mb = response_size_bytes / (1024 * 1024)
            if size_mb > MAX_TRANSACTION_SIZE_MB:
                print(f"[ELECTRUMX] Skipping large transaction: {size_mb:.2f} MB (threshold: {MAX_TRANSACTION_SIZE_MB} MB)")
                return True
        
        # Check input/output counts if tx_data is a dict
        if isinstance(tx_data, dict):
            # Try to get input/output counts from various possible formats
            inputs_count = 0
            outputs_count = 0
            
            # Check for vin/vout (Mempool format)
            if "vin" in tx_data:
                inputs_count = len(tx_data["vin"])
            elif "inputs" in tx_data:
                inputs_count = len(tx_data["inputs"])
            
            if "vout" in tx_data:
                outputs_count = len(tx_data["vout"])
            elif "outputs" in tx_data:
                outputs_count = len(tx_data["outputs"])
            
            # FILTER 1: Extreme mixers (both sides massive)
            if inputs_count >= SKIP_MIXER_INPUT_THRESHOLD and outputs_count >= SKIP_MIXER_OUTPUT_THRESHOLD:
                print(f"[ELECTRUMX] Skipping extreme mixer: {inputs_count} in → {outputs_count} out")
                return True
            
            # FILTER 2: Distribution/Airdrop transactions (CRITICAL!)
            if inputs_count <= SKIP_DISTRIBUTION_MAX_INPUTS and outputs_count >= SKIP_DISTRIBUTION_MIN_OUTPUTS:
                print(f"[ELECTRUMX] Skipping airdrop/distribution: {inputs_count} in → {outputs_count} out")
                return True
        
        return False
    
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
            # Note: Version negotiation is optional for ElectrumX - removed to avoid connection issues
            
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
            
            total_tx_count = len(history)
            print(f"[ELECTRUMX] Found {total_tx_count} transaction entries")
            
            # EARLY FILTERING: Skip addresses with too many transactions (likely exchanges)
            if total_tx_count > EXCHANGE_WALLET_THRESHOLD:
                print(f"[ELECTRUMX] SKIPPING address {address}: {total_tx_count} txs exceeds exchange threshold ({EXCHANGE_WALLET_THRESHOLD})")
                return []
            
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
            
            # LIMIT transactions to fetch (avoid wasting resources on high-activity addresses)
            if len(tx_hashes_to_fetch) > MAX_TRANSACTIONS_PER_ADDRESS:
                print(f"[ELECTRUMX] Limiting fetch to {MAX_TRANSACTIONS_PER_ADDRESS} of {len(tx_hashes_to_fetch)} transactions (MAX_TRANSACTIONS_PER_ADDRESS)")
                # Take most recent transactions (usually at end of history, but sort by height to be safe)
                tx_hashes_to_fetch = sorted(tx_hashes_to_fetch, key=lambda x: x[1] if x[1] > 0 else float('inf'), reverse=True)[:MAX_TRANSACTIONS_PER_ADDRESS]
            
            print(f"[ELECTRUMX] Fetching full details for {len(tx_hashes_to_fetch)} transactions")
            
            # Step 3: Fetch full transaction details for each
            transactions = []
            debug_logged = False  # Log first transaction for debugging
            for idx, (tx_hash, height) in enumerate(tx_hashes_to_fetch):
                try:
                    # Fetch full transaction using blockchain.transaction.get
                    # verbose=True returns parsed JSON, verbose=False returns raw hex
                    tx_data = await self._send_request("blockchain.transaction.get", [tx_hash, True])
                    
                    # Debug: Log first transaction response to verify format
                    if not debug_logged and tx_data:
                        print(f"[ELECTRUMX] DEBUG: First tx response type: {type(tx_data).__name__}")
                        if isinstance(tx_data, dict):
                            print(f"[ELECTRUMX] DEBUG: First tx keys: {list(tx_data.keys())[:10]}")
                        elif isinstance(tx_data, str):
                            print(f"[ELECTRUMX] DEBUG: First tx (hex): {tx_data[:100]}...")
                        debug_logged = True
                    
                    # If verbose mode returned hex string or empty, we can't parse addresses
                    # ElectrumX with verbose=True should return a dict with transaction details
                    if not tx_data:
                        # Try without verbose flag (returns hex)
                        tx_data = await self._send_request("blockchain.transaction.get", [tx_hash])
                        if tx_data and isinstance(tx_data, str):
                            # Got hex string - check size before processing
                            hex_size = len(tx_data.encode('utf-8')) if isinstance(tx_data, str) else 0
                            if self._should_skip_large_transaction(tx_data, hex_size):
                                continue  # Skip this transaction
                            # Got hex string - we can't extract addresses from this
                            tx_data = None  # Will use fallback
                    
                    if tx_data:
                        # Check if transaction should be skipped before converting (saves resources)
                        if self._should_skip_large_transaction(tx_data):
                            continue  # Skip this transaction
                        
                        # Convert to Mempool format
                        tx_obj = self._convert_electrum_tx_to_mempool_format(tx_data, tx_hash, height)
                        
                        # Validate transaction format
                        is_valid, validation_error = self._validate_transaction_format(tx_obj)
                        if not is_valid:
                            print(f"[ELECTRUMX] Warning: Transaction format validation failed for {tx_hash[:16]}...: {validation_error}")
                            # Still add it, but log the warning
                        
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
                    
                    # Progress logging and small delay to avoid overwhelming ElectrumX
                    if (idx + 1) % 100 == 0:
                        print(f"[ELECTRUMX] Progress: {idx + 1}/{len(tx_hashes_to_fetch)} transactions fetched")
                    if (idx + 1) % 10 == 0:
                        await asyncio.sleep(0.05)  # Small delay every 10 transactions
                    
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
        """Cleanup - close the persistent connection"""
        self._disconnect()


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