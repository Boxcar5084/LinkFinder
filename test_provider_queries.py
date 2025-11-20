#!/usr/bin/env python3
"""
Test the actual ElectrumXProvider with multiple sequential address queries
This simulates real-world usage patterns
"""
import asyncio
import sys
from api_provider import get_provider

async def test_provider_sequential():
    """Test ElectrumXProvider with multiple sequential address queries"""
    print("\n" + "="*60)
    print("ELECTRUMX PROVIDER SEQUENTIAL TEST")
    print("="*60)
    print("Testing real provider usage patterns\n")
    
    provider = get_provider("electrumx")
    
    # Test addresses - EARLY BLOCKCHAIN ONLY (server is syncing)
    # Using only addresses from the first few blocks
    test_addresses = [
        "1A1zP1eP5QGefi2DMPTfTL5SLmv7DivfNa",  # Genesis block (block 0)
        "1A1zP1eP5QGefi2DMPTfTL5SLmv7DivfNa",  # Repeat genesis (most reliable)
    ]
    
    results = []
    
    for i, address in enumerate(test_addresses, 1):
        print(f"\nQuery {i}: Address {address[:20]}...")
        print("-" * 60)
        
        try:
            txs = await provider.get_address_transactions(address)
            if txs is not None:
                print(f"  ✓ SUCCESS - Found {len(txs)} transactions")
                results.append(True)
            else:
                print(f"  ✗ FAILED - Returned None")
                results.append(False)
        except Exception as e:
            print(f"  ✗ ERROR: {e}")
            results.append(False)
        
        # Small delay between queries
        await asyncio.sleep(0.5)
    
    await provider.close()
    
    # Summary
    print("\n" + "="*60)
    print("SUMMARY")
    print("="*60)
    print(f"Total queries: {len(test_addresses)}")
    print(f"Successful: {sum(results)}")
    print(f"Failed: {len(results) - sum(results)}")
    
    if results[0] and not all(results[1:]):
        print("\n⚠️  PATTERN DETECTED: First query works, subsequent fail!")
        print("   This indicates ElectrumX connection handling issues.")
        print("\n   Solutions:")
        print("   1. Check ElectrumX server configuration")
        print("   2. Check network connectivity to ElectrumX server")
        print("   3. Verify ELECTRUMX_HOST and ELECTRUMX_PORT settings")
        print("   4. Check ElectrumX server logs")
    elif all(results):
        print("\n✓ All queries succeeded - provider is working correctly")
    else:
        print("\n✗ Some queries failed - check ElectrumX server status and configuration")

if __name__ == "__main__":
    try:
        asyncio.run(test_provider_sequential())
    except KeyboardInterrupt:
        print("\n\nTest interrupted by user")
        sys.exit(1)
    except Exception as e:
        print(f"\n\nFatal error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

