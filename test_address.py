import requests
import json

address = "1J6NL5rPnQMdt8hqoV6gmefsYgcXjVxdrr"

# Test Mempool directly
url = f"https://mempool.space/api/address/{address}/txs"

print(f"Testing Mempool for: {address}\n")

try:
    response = requests.get(url, timeout=30)
    print(f"Status: {response.status_code}")
    
    if response.status_code == 200:
        txs = response.json()
        print(f"Transactions found: {len(txs)}\n")
        
        if txs:
            print("Sample transaction:")
            print(json.dumps(txs[0], indent=2)[:500])
            
            # Check if outputs contain 1J6NL5rPnQMdt8hqoV6gmefsYgcXjVxdrr
            for tx in txs[:10]:
                outputs = tx.get('vout', [])  # ← Note: might be 'vout' not 'outputs'
                for output in outputs:
                    if 'scriptpubkey_address' in output:
                        addr = output['scriptpubkey_address']
                        if 'bc1qvyel6c8tp34na7fw446evjugxl5zz66cm9ukku' in str(addr):
                            print(f"\n✅ Found target in transaction!")
                            print(json.dumps(tx, indent=2))
    else:
        print(f"Error: {response.text}")
        
except Exception as e:
    print(f"Error: {e}")
