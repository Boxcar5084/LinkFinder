# -*- coding: utf-8 -*-
import requests
import asyncio
from typing import List, Dict, Optional, Any
from abc import ABC, abstractmethod
from config import DEFAULT_API

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
    """Local Electrs node provider"""

    def __init__(self, host: str = "localhost", port: int = 50002):
        self.base_url = f"http://{host}:{port}"
        self.timeout = 30

    async def get_address_transactions(self, address: str,
                                     start_block: Optional[int] = None,
                                     end_block: Optional[int] = None) -> List[Dict[str, Any]]:
        """Fetch transactions from local Electrs node"""
        url = f"{self.base_url}/address/{address}/txs"

        # Add retry logic for Electrs as well
        max_retries = 3
        retry_delay = 1  # Local node, shorter delays

        for attempt in range(max_retries):
            try:
                await asyncio.sleep(0.1)  # Minimal delay for local

                response = requests.get(url, timeout=self.timeout)
                response.raise_for_status()

                txs = response.json()

                if not isinstance(txs, list):
                    return []

                # Filter by block range
                if start_block or end_block:
                    filtered_txs = []
                    for tx in txs:
                        block_height = tx.get('block_height')

                        if block_height is None or block_height == 0:
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
                print(f" [WAIT] Connection error. Attempt {attempt + 1}/{max_retries}")
                if attempt < max_retries - 1:
                    await asyncio.sleep(retry_delay * 2)  # Longer wait for connection issues
                    continue
                print(f" [ERR] Electrs error: {str(e)[:100]}")
                return []

            except requests.exceptions.RequestException as e:
                print(f" [ERR] Electrs request error: {str(e)[:100]}")
                if attempt < max_retries - 1:
                    await asyncio.sleep(retry_delay)
                    continue
                return []

            except Exception as e:
                print(f" [ERR] Electrs error: {str(e)[:100]}")
                return []

        print(f" [ERR] Max retries exceeded for {address} on Electrs")
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
        return ElectrsProvider()

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