import requests
import json
from datetime import datetime
import time

class AddressExplorer:
    def __init__(self, address, provider='mempool'):
        self.address = address
        self.provider = provider
        self.timeout = 30
        self.max_retries = 3
        self.retry_delay = 2
        
        # Proper headers to avoid API rejection
        self.headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
            'Accept': 'application/json',
            'Accept-Language': 'en-US,en;q=0.9'
        }
    
    def explore_mempool(self):
        """Query Mempool.space API with retry logic"""
        url = f"https://mempool.space/api/address/{self.address}/txs"
        
        for attempt in range(self.max_retries):
            try:
                print(f"🔍 Fetching from Mempool (attempt {attempt + 1}/{self.max_retries})...")
                
                # Use session for better connection handling
                session = requests.Session()
                response = session.get(url, timeout=self.timeout, headers=self.headers)
                
                # Handle specific status codes
                if response.status_code == 400:
                    print(f"⚠️  Mempool returned 400 (Bad Request)")
                    print(f"   URL: {url}")
                    print(f"   This might be a rate limit or address validation issue")
                    return None
                
                if response.status_code == 429:
                    print(f"⏱️  Rate limited (429). Waiting {self.retry_delay * 2}s...")
                    time.sleep(self.retry_delay * 2)
                    continue
                
                response.raise_for_status()
                
                txs = response.json()
                
                if not isinstance(txs, list):
                    print("❌ Invalid response format from Mempool")
                    return None
                
                if len(txs) == 0:
                    print(f"ℹ️  Address has no transactions in Mempool")
                    return []
                
                print(f"✅ Got {len(txs)} transactions from Mempool")
                return txs
            
            except requests.exceptions.Timeout:
                print(f"⏱️  Timeout on attempt {attempt + 1}. Waiting {self.retry_delay}s...")
                if attempt < self.max_retries - 1:
                    time.sleep(self.retry_delay)
            
            except requests.exceptions.ConnectionError as e:
                print(f"❌ Connection error: {str(e)[:100]}")
                if attempt < self.max_retries - 1:
                    print(f"   Retrying in {self.retry_delay}s...")
                    time.sleep(self.retry_delay)
            
            except requests.exceptions.HTTPError as e:
                print(f"❌ HTTP Error: {e}")
                return None
            
            except Exception as e:
                print(f"❌ Error: {str(e)[:150]}")
                return None
        
        return None
    
    def explore_blockchain_com(self):
        """Query blockchain.com API (alternative to Blockchair)"""
        url = f"https://blockchain.info/address/{self.address}?format=json"
        
        try:
            print(f"🔍 Fetching from blockchain.com...")
            
            session = requests.Session()
            response = session.get(url, timeout=self.timeout, headers=self.headers)
            
            if response.status_code == 429:
                print(f"⏱️  Rate limited by blockchain.com")
                return None
            
            response.raise_for_status()
            
            data = response.json()
            
            if 'tx' not in data:
                print(f"ℹ️  Address has no transactions on blockchain.com")
                return []
            
            print(f"✅ Got {len(data['tx'])} transactions from blockchain.com")
            return data['tx']
        
        except Exception as e:
            print(f"❌ blockchain.com error: {str(e)[:100]}")
            return None
    
    def analyze_transactions(self, txs, source='mempool'):
        """Analyze transaction list"""
        if not txs or len(txs) == 0:
            print("⚠️  No transactions to analyze")
            return None
        
        try:
            # Mempool format
            if source == 'mempool' and 'status' in txs:
                first_tx = txs[-1]  # Oldest
                last_tx = txs     # Newest
                
                first_block = first_tx.get('status', {}).get('block_height')
                last_block = last_tx.get('status', {}).get('block_height')
                
                first_time = datetime.fromtimestamp(
                    first_tx.get('status', {}).get('block_time', 0)
                ) if first_tx.get('status', {}).get('block_time') else 'Unknown'
                
                last_time = datetime.fromtimestamp(
                    last_tx.get('status', {}).get('block_time', 0)
                ) if last_tx.get('status', {}).get('block_time') else 'Unknown'
            
            # blockchain.com format
            else:
                first_tx = txs
                last_tx = txs[-1]
                first_block = first_tx.get('block_height', 'Unknown')
                last_block = last_tx.get('block_height', 'Unknown')
                first_time = datetime.fromtimestamp(first_tx['time']) if 'time' in first_tx else 'Unknown'
                last_time = datetime.fromtimestamp(last_tx['time']) if 'time' in last_tx else 'Unknown'
        
            return {
                'address': self.address,
                'total_transactions': len(txs),
                'first_transaction': {
                    'block_height': first_block,
                    'timestamp': str(first_time)
                },
                'last_transaction': {
                    'block_height': last_block,
                    'timestamp': str(last_time)
                },
                'block_range': (first_block, last_block)
            }
        
        except Exception as e:
            print(f"❌ Error analyzing transactions: {str(e)[:100]}")
            return None
    
    def explore(self):
        """Main exploration function with fallbacks"""
        print(f"\n{'='*60}")
        print(f"📍 Exploring Address: {self.address}")
        print(f"{'='*60}\n")
        
        providers = [
            ('mempool', self.explore_mempool),
            ('blockchain.com', self.explore_blockchain_com)
        ]
        
        txs = None
        source = None
        
        for provider_name, provider_func in providers:
            print(f"\n🔄 Trying {provider_name}...\n")
            txs = provider_func()
            
            if txs is not None:
                source = provider_name
                break
            
            print(f"⏩ Moving to next provider...\n")
        
        if txs is None:
            print("\n❌ Could not fetch transactions from any provider")
            print("💡 Possible reasons:")
            print("   1. Address doesn't exist or has no transactions")
            print("   2. All APIs are rate-limited or temporarily unavailable")
            print("   3. Network connectivity issue")
            return None
        
        # Analyze
        analysis = self.analyze_transactions(txs, source)
        
        if analysis:
            print(f"\n✅ Address Analysis:")
            print(f"   Total transactions: {analysis['total_transactions']}")
            print(f"   First tx: Block {analysis['first_transaction']['block_height']} ({analysis['first_transaction']['timestamp']})")
            print(f"   Last tx:  Block {analysis['last_transaction']['block_height']} ({analysis['last_transaction']['timestamp']})")
            
            if isinstance(analysis['first_transaction']['block_height'], int) and isinstance(analysis['last_transaction']['block_height'], int):
                print(f"\n📊 Recommended Block Range:")
                print(f"   start_block: {analysis['first_transaction']['block_height']}")
                print(f"   end_block: {analysis['last_transaction']['block_height']}")
                
                buffer = max(100, (analysis['last_transaction']['block_height'] - analysis['first_transaction']['block_height']) // 2)
                print(f"\n💡 Or use for tracing with buffer:")
                print(f"   start_block: {max(0, analysis['first_transaction']['block_height'] - buffer)}")
                print(f"   end_block: {analysis['last_transaction']['block_height'] + buffer}")
            
            return analysis
        
        return None


def main():
    import sys
    
    if len(sys.argv) < 2:
        # Default test addresses
        addresses = [
            "1A1z7agoat4FqCnf4Xy7jJn1eJd7azHXzA",  # Satoshi's address (likely no txs now)
            "3J98t1WpEZ73CNmYviecrnyiWrnqRhWNLy"   # Try a P2SH address instead
        ]
        print("Usage: python explore_address.py ADDRESS1 [ADDRESS2] [ADDRESS3] ...\n")
        print("No addresses provided. Testing with sample addresses...\n")
    else:
        addresses = sys.argv[1:]
    
    print(f"🚀 Exploring {len(addresses)} address(es)...\n")
    
    results = {}
    for i, address in enumerate(addresses, 1):
        print(f"\n[{i}/{len(addresses)}]")
        explorer = AddressExplorer(address, provider='mempool')
        analysis = explorer.explore()
        
        if analysis:
            results[address] = analysis
        
        time.sleep(1)  # Delay between requests
    
    # Summary
    if results:
        print(f"\n\n{'='*60}")
        print("📋 Summary")
        print(f"{'='*60}\n")
        
        for address, analysis in results.items():
            print(f"Address: {address}")
            print(f"  Txs: {analysis['total_transactions']}")
            if isinstance(analysis['first_transaction']['block_height'], int):
                print(f"  Blocks: {analysis['first_transaction']['block_height']} - {analysis['last_transaction']['block_height']}")
            print()
        
        # Export to JSON for easy reference
        with open('address_analysis.json', 'w') as f:
            json.dump(results, f, indent=2, default=str)
        
        print("✅ Results saved to: address_analysis.json")
    else:
        print("\n❌ No addresses could be analyzed")
        print("\n💡 Troubleshooting:")
        print("   1. Check your internet connection")
        print("   2. Try again in a few minutes (might be rate limited)")
        print("   3. Use your own addresses instead of test addresses")
        print("   4. If behind a firewall/VPN, try disabling it")


if __name__ == "__main__":
    main()
