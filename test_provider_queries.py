#!/usr/bin/env python3
"""
Test the actual ElectrsProvider with multiple sequential address queries
This simulates real-world usage patterns
"""
import asyncio
import sys
from api_provider import get_provider

async def test_provider_sequential():
    """Test ElectrsProvider with multiple sequential address queries"""
    print("\n" + "="*60)
    print("ELECTRS PROVIDER SEQUENTIAL TEST")
    print("="*60)
    print("Testing real provider usage patterns\n")
    
    provider = get_provider("electrs")
    
    # Test addresses (mix of known addresses)
    test_addresses = [
        "1A1zP1eP5QGefi2DMPTfTL5SLmv7DivfNa",  # Genesis block
        "1BvBMSEYstWetqTFn5Au4m4GFg7xJaNVN2",  # Another known address
        "1CounterpartyXXXXXXXXXXXXXXXUWLpVr",  # Counterparty
        "1A1zP1eP5QGefi2DMPTfTL5SLmv7DivfNa",  # Repeat first
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
        print("   This indicates electrs connection handling issues.")
        print("\n   Solutions:")
        print("   1. Check electrs.toml configuration (see electrs_config_guide.md)")
        print("   2. Increase max_connections in electrs config")
        print("   3. Check Docker resource limits")
        print("   4. Review electrs logs: docker logs electrs")
    elif all(results):
        print("\n✓ All queries succeeded - provider is working correctly")
    else:
        print("\n✗ Some queries failed - check electrs status and configuration")

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

