# -*- coding: utf-8 -*-
import requests
import asyncio
from typing import List, Dict, Optional, Any
from abc import ABC, abstractmethod
from config import DEFAULT_API
import socket
import json


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

    def __init__(self):
        self.base_url = "https://mempool.space/api"
        self.timeout = 30

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

                response = requests.get(url, timeout=self.timeout, headers={
                    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'
                })

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

class ElectrsProvider(APIProvider):
    """Local Electrs node provider using Electrum protocol (JSON-RPC over TCP)"""
    
    def __init__(self, host: str = "100.94.34.56", port: int = 50001, use_ssl: bool = False):
        self.host = host
        self.port = port
        self.use_ssl = use_ssl
        self.timeout = 30
        self.request_id = 0
    
    async def _send_request(self, method: str, params: list) -> Dict[str, Any]:
        """Send a JSON-RPC request to Electrs over TCP"""
        self.request_id += 1
        
        request = {
            "jsonrpc": "2.0",
            "method": method,
            "params": params,
            "id": self.request_id
        }
        
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(self.timeout)
            
            print(f"[ELECTRS] Connecting to {self.host}:{self.port}...")
            sock.connect((self.host, self.port))
            
            # Send JSON-RPC request
            message = json.dumps(request) + "\n"
            sock.sendall(message.encode())
            
            # Receive response
            response_data = b""
            while True:
                try:
                    chunk = sock.recv(4096)
                    if not chunk:
                        break
                    response_data += chunk
                except socket.timeout:
                    break
            
            sock.close()
            
            # Parse response
            response_text = response_data.decode().strip()
            if not response_text:
                print("[ELECTRS] Empty response from server")
                return {}
            
            response = json.loads(response_text)
            
            if "error" in response and response["error"]:
                print(f"[ELECTRS] RPC error: {response['error']}")
                return {}
            
            return response.get("result", {})
        
        except socket.timeout:
            print("[ELECTRS] Socket timeout")
            return {}
        except ConnectionRefusedError:
            print(f"[ELECTRS] Connection refused to {self.host}:{self.port}")
            return {}
        except Exception as e:
            print(f"[ELECTRS] Socket error: {str(e)[:100]}")
            return {}
    
    async def get_address_transactions(self, address: str,
                                      start_block: Optional[int] = None,
                                      end_block: Optional[int] = None) -> List[Dict[str, Any]]:
        """Fetch transactions from Electrs using Electrum protocol"""
        
        try:
            # Request address history using Electrum protocol
            history = await self._send_request("blockchain.address.get_history", [address])
            
            if not history or not isinstance(history, list):
                print(f"[ELECTRS] No transactions found for {address}")
                return []
            
            print(f"[ELECTRS] Found {len(history)} transaction entries")
            
            # Convert history entries to transaction objects
            transactions = []
            for entry in history:
                tx_hash = entry.get("tx_hash")
                height = entry.get("height", 0)
                
                # Filter by block range if specified
                if start_block and height > 0 and height < start_block:
                    continue
                if end_block and height > 0 and height > end_block:
                    continue
                
                transactions.append({
                    "hash": tx_hash,
                    "block_height": height if height > 0 else None,
                    "tx_hash": tx_hash,
                    "height": height
                })
            
            print(f"[ELECTRS] Filtered to {len(transactions)} transactions")
            return transactions
        
        except Exception as e:
            print(f"[ELECTRS] Error fetching transactions: {str(e)[:100]}")
            return []
    
    async def close(self):
        """Cleanup"""
        pass


def get_provider(provider_name: str = None) -> APIProvider:
    """
    Factory function to get the appropriate API provider
    
    Args:
        provider_name: "blockchain", "mempool", "electrs", or None (uses DEFAULT_API from config)
    
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
        return MempoolProvider()

    elif provider_name == "electrs":
        print("[API] Using Local Electrs Node")
        return ElectrsProvider(host="100.94.34.56", port=50001, use_ssl=False)


    else:
        raise ValueError(f"Unknown provider: {provider_name}. Use 'blockchain', 'mempool', or 'electrs'")


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
        for provider in ["blockchain", "mempool", "electrs"]:
            try:
                await test_provider(provider)
            except Exception as e:
                print(f" [WARN] {provider.upper()} provider error: {e}\n")

    asyncio.run(main())