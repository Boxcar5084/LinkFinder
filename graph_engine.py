# -*- coding: utf-8 -*-
"""
Bitcoin Address Linker - Graph Engine with Bidirectional BFS
Connects two sets of Bitcoin addresses through transaction chains.
"""

import asyncio
from typing import Set, Dict, List, Tuple, Optional, Any, Union
from collections import deque
from api_provider import APIProvider
from cache_manager import TransactionCache
from config import (
    MAX_TRANSACTIONS_PER_ADDRESS,
    SKIP_MIXER_INPUT_THRESHOLD,
    SKIP_MIXER_OUTPUT_THRESHOLD,
    SKIP_DISTRIBUTION_MAX_INPUTS,
    SKIP_DISTRIBUTION_MIN_OUTPUTS
)


class BitcoinAddressLinker:
    """Graph traversal engine for Bitcoin address linking with path tracking"""

    def __init__(self, api_provider: APIProvider, cache_manager: TransactionCache,
                 max_tx_per_address: int = MAX_TRANSACTIONS_PER_ADDRESS):
        self.api = api_provider
        self.cache = cache_manager
        self.max_tx_per_address = max_tx_per_address
        print(f"[GRAPH_ENGINE] Initialized with cache_manager: {cache_manager}")

    def _extract_addresses(self, tx: Dict[str, Any], direction: str = 'output') -> Set[str]:
        """Extract addresses from transaction"""
        addresses = set()

        if not isinstance(tx, dict):
            return addresses

        # Try Mempool format first (vout/vin with scriptpubkey_address)
        if direction == 'output':
            items = tx.get('vout', [])
        else:
            items = tx.get('vin', [])

        if isinstance(items, list) and len(items) > 0:
            for item in items:
                if not isinstance(item, dict):
                    continue

                if direction == 'output':
                    addr = item.get('scriptpubkey_address')
                    if addr and addr != 'None' and addr.strip():
                        addresses.add(addr)
                else:
                    prevout = item.get('prevout')
                    if isinstance(prevout, dict):
                        addr = prevout.get('scriptpubkey_address')
                        if addr and addr != 'None' and addr.strip():
                            addresses.add(addr)

            if addresses:
                return addresses

        # Fallback: blockchain.info format (out/inputs)
        if direction == 'output':
            items = tx.get('out', [])
        else:
            items = tx.get('inputs', [])

        if isinstance(items, list) and len(items) > 0:
            for item in items:
                if not isinstance(item, dict):
                    continue

                addr = item.get('addr')
                if addr and addr != 'None' and addr.strip():
                    addresses.add(addr)

            if addresses:
                return addresses

        return addresses

    def _is_coinjoin(self, tx: Dict[str, Any]) -> bool:
        """Check if transaction is a CoinJoin pattern (Wasabi/Samourai)"""
        try:
            inputs_count = len(tx.get('vin', []))
            outputs_count = len(tx.get('vout', []))
            
            if inputs_count == 0:
                inputs_count = len(tx.get('inputs', []))
            if outputs_count == 0:
                outputs_count = len(tx.get('out', []))
            
            # CoinJoin: many inputs and many outputs with similar counts
            if inputs_count >= 10 and outputs_count >= 10:
                ratio = max(inputs_count, outputs_count) / min(inputs_count, outputs_count)
                if ratio < 1.2:  # Counts are similar
                    return True
            
            return False
        except:
            return False

    def _should_skip_transaction(self, tx: Dict[str, Any]) -> bool:
        """
        Skip transactions that break analysis chains.
        Uses thresholds from config.py for flexibility.
        """
        try:
            # Validate input
            if not isinstance(tx, dict):
                return False
            
            # Get input/output counts
            inputs_count = len(tx.get('vin', []))
            outputs_count = len(tx.get('vout', []))
            
            if inputs_count == 0:
                inputs_count = len(tx.get('inputs', []))
            if outputs_count == 0:
                outputs_count = len(tx.get('out', []))
            
            # FILTER 1: Extreme mixers (both sides massive)
            if inputs_count >= SKIP_MIXER_INPUT_THRESHOLD and outputs_count >= SKIP_MIXER_OUTPUT_THRESHOLD:
                print(f"    [SKIP] Extreme mixer: {inputs_count} in â†’ {outputs_count} out")
                return True
            
            # FILTER 2: Distribution/Airdrop transactions (CRITICAL!)
            if inputs_count <= SKIP_DISTRIBUTION_MAX_INPUTS and outputs_count >= SKIP_DISTRIBUTION_MIN_OUTPUTS:
                print(f"    [SKIP] Airdrop/Distribution: {inputs_count} in â†’ {outputs_count} out")
                return True
            
            # FILTER 3: CoinJoin patterns
            if self._is_coinjoin(tx):
                print(f"    [SKIP] CoinJoin detected")
                return True
            
            return False
        
        except Exception as e:
            print(f"    [ERROR] Exception in _should_skip_transaction: {e}")
            return False

    async def get_address_txs(self, address: str,
                             start_block: Optional[int] = None,
                             end_block: Optional[int] = None) -> List[Dict[str, Any]]:
        """Fetch transactions with smart filtering"""
        block_range = (start_block, end_block) if (start_block or end_block) else None

        # Try to get from cache FIRST
        cached = self.cache.get_cached(address, block_range)
        if cached:
            return cached

        print(f"[*] Fetching: {address}")
        txs = await self.api.get_address_transactions(address, start_block, end_block)

        # Validate txs is a list
        if not isinstance(txs, list):
            print(f"  [WARN] API returned non-list: {type(txs)}")
            return []

        filtered_txs = []
        
        # Apply all smart filters
        for tx in txs:
            # Skip if not a dict
            if not isinstance(tx, dict):
                continue
            
            # Skip if should be filtered
            try:
                if self._should_skip_transaction(tx):
                    continue
            except Exception as e:
                print(f"    [ERROR] Error checking transaction: {e}")
                # On error, include the transaction (safe default)
                pass
            
            filtered_txs.append(tx)
        
        # Limit to MAX_TRANSACTIONS_PER_ADDRESS
        if hasattr(self, 'max_tx_per_address'):
            filtered_txs = filtered_txs[:self.max_tx_per_address]

        # Cache the filtered results using .store() method
        if filtered_txs:
            try:
                print(f"  [DEBUG] Attempting to cache {len(filtered_txs)} transactions for {address}")
                self.cache.store(address, filtered_txs, block_range)
                print(f"  [DEBUG] Cache store completed for {address}")
            except Exception as e:
                print(f"  [WARN] Error caching: {e}")
                import traceback
                traceback.print_exc()
        else:
            print(f"  [DEBUG] No transactions to cache for {address} (filtered_txs is empty)")

        return filtered_txs

    async def find_connection(self, list_a: List[str], list_b: List[str],
                            max_depth: int = 5,
                            start_block: Optional[int] = None,
                            end_block: Optional[int] = None,
                            progress_callback=None) -> Dict[str, Any]:
        """Fresh trace - calls find_connection_with_visited_state with empty state"""
        return await self.find_connection_with_visited_state(
            list_a, list_b, max_depth, start_block, end_block,
            visited_forward=None,
            visited_backward=None,
            queued_forward=None,
            queued_backward=None,
            progress_callback=progress_callback
        )


    async def find_connection_with_visited_state(self, list_a: List[str], list_b: List[str],
                                                max_depth: int = 5,
                                                start_block: Optional[int] = None,
                                                end_block: Optional[int] = None,
                                                visited_forward: Union[Dict, Set, List] = None,
                                                visited_backward: Union[Dict, Set, List] = None,
                                                queued_forward: Union[List] = None,
                                                queued_backward: Union[List] = None,
                                                progress_callback=None) -> Dict[str, Any]:
        """Resume from checkpoint with proper queue reconstruction"""

        # Convert visited types to proper format
        if visited_forward is None:
            visited_forward_dict = {addr: [addr] for addr in list_a}
        elif isinstance(visited_forward, dict):
            visited_forward_dict = visited_forward
        elif isinstance(visited_forward, (set, list)):
            visited_forward_dict = {addr: [addr] for addr in visited_forward}
        else:
            visited_forward_dict = {addr: [addr] for addr in list_a}

        if visited_backward is None:
            visited_backward_dict = {addr: [addr] for addr in list_b}
        elif isinstance(visited_backward, dict):
            visited_backward_dict = visited_backward
        elif isinstance(visited_backward, (set, list)):
            visited_backward_dict = {addr: [addr] for addr in visited_backward}
        else:
            visited_backward_dict = {addr: [addr] for addr in list_b}

        results = {
            'connections_found': [],
            'search_depth': max_depth,
            'total_addresses_examined': 0,
            'block_range': (start_block, end_block),
            'status': 'searching'
        }

        print(f"\n[LINK] Linking {len(list_a)} addresses with {len(list_b)} addresses")
        print(f" Max Depth: {max_depth}")
        print(f" Resuming with {len(visited_forward_dict)} + {len(visited_backward_dict)} discovered")
        
        # Normalize queued addresses - handle None, empty list, etc.
        queued_forward = queued_forward if queued_forward is not None else []
        queued_backward = queued_backward if queued_backward is not None else []
        
        print(f" Queued to process: {len(queued_forward)} forward, {len(queued_backward)} backward\n")

        # Initialize visited - addresses that were discovered AND explored (not in queue)
        # Queued addresses were discovered but NOT yet explored, so exclude them from visited
        queued_forward_set = set(queued_forward)
        forward_visited = set(addr for addr in visited_forward_dict.keys() if addr not in queued_forward_set)
        forward_discovered = dict(visited_forward_dict)
        
        # Initialize queues - if queued addresses provided, use those (they were discovered but not explored)
        # Otherwise, continue from the most recently discovered addresses (they may have unexplored neighbors)
        forward_queue = deque()
        if len(queued_forward) > 0:
            print(f"[DEBUG] Loading {len(queued_forward)} queued forward addresses (discovered but not yet explored)")
            for addr in queued_forward:
                if addr in visited_forward_dict:
                    path = visited_forward_dict[addr]
                else:
                    # Address in queue but not in discovered - use address as path
                    path = [addr]
                forward_queue.append((addr, path))
                print(f"[DEBUG]   Queued: {addr} (path length: {len(path)})")
        else:
            # No queued addresses saved - try to continue from recently discovered addresses
            # Take the last N discovered addresses and re-queue them to explore their neighbors
            print(f"[DEBUG] No queued addresses saved - continuing from recently discovered addresses")
            print(f"[DEBUG] Total discovered: {len(visited_forward_dict)} addresses")
            
            # Get all discovered addresses (they were explored, but their neighbors might not be)
            # Re-queue them to check for new neighbors
            discovered_list = list(visited_forward_dict.items())
            # Start with the most recently discovered (last in dict, though order isn't guaranteed)
            # Actually, better: start from initial addresses and work outward
            for addr in list_a:
                if addr in visited_forward_dict:
                    # Re-queue initial addresses to explore their neighbors again
                    path = visited_forward_dict[addr]
                    forward_queue.append((addr, path))
                    forward_visited.discard(addr)  # Allow re-exploration
                    print(f"[DEBUG]   Re-queuing initial address: {addr}")
            
            # If still no queue, take some discovered addresses
            if len(forward_queue) == 0 and len(visited_forward_dict) > 0:
                # Take up to 10 most recently discovered addresses
                items = list(visited_forward_dict.items())[-10:]
                for addr, path in items:
                    forward_queue.append((addr, path))
                    forward_visited.discard(addr)
                    print(f"[DEBUG]   Re-queuing discovered address: {addr}")

        # Same for backward
        queued_backward_set = set(queued_backward) if queued_backward else set()
        backward_visited = set(addr for addr in visited_backward_dict.keys() if addr not in queued_backward_set)
        backward_discovered = dict(visited_backward_dict)
        
        backward_queue = deque()
        if queued_backward:
            print(f"[DEBUG] Loading {len(queued_backward)} queued backward addresses (discovered but not yet explored)")
            for addr in queued_backward:
                path = visited_backward_dict.get(addr, [addr])
                backward_queue.append((addr, path))
        else:
            # No queued addresses saved - all discovered addresses were fully explored
            # Start fresh from initial addresses to find new connections
            print(f"[DEBUG] No queued addresses - all {len(visited_backward_dict)} discovered addresses were explored")
            print(f"[DEBUG] Starting fresh from initial addresses to find new connections")
            # Start from initial addresses - they may have new neighbors we haven't seen
            for addr in list_b:
                if addr not in backward_visited:
                    backward_queue.append((addr, [addr]))

        # Alternating BFS
        for current_depth in range(max_depth):
            print(f"\n{'='*70}")
            print(f"[DEPTH {current_depth}]")
            print(f"{'='*70}")

            # Forward step - ONLY FOLLOW OUTPUTS
            print(f"\n[>>] Forward BFS (queue: {len(forward_queue)}):")
            forward_queue_size = len(forward_queue)
            addresses_explored = 0

            for _ in range(forward_queue_size):
                if not forward_queue:
                    break

                current, path = forward_queue.popleft()

                # Skip if already visited in THIS SEARCH SESSION
                if current in forward_visited:
                    continue

                forward_visited.add(current)
                print(f"  Exploring: {current}")

                if progress_callback:
                    progress_callback({
                        'visited': len(forward_visited) + len(backward_visited),
                        'current': current,
                        'direction': 'forward'   
                    })

                try:
                    txs = await self.get_address_txs(current, start_block, end_block)

                    for tx in txs:
                        # FORWARD direction: Only follow OUTPUTS
                        # Who did this address send money TO?
                        outputs = self._extract_addresses(tx, 'output')
                        
                        for neighbor in outputs:
                            if neighbor in forward_discovered:
                                continue

                            new_path = path + [neighbor]

                            # Check if meeting point
                            if neighbor in backward_discovered:
                                backward_path = backward_discovered[neighbor]
                                full_path = new_path + list(reversed(backward_path[1:]))
                                
                                print(f"\n[âœ“] MEETING POINT FOUND: {neighbor}")
                                print(f" Path: {' -> '.join(full_path)}")
                                
                                results['connections_found'].append({
                                    'source': full_path[0],
                                    'target': full_path[-1],
                                    'path': full_path,
                                    'path_length': len(full_path),
                                    'path_count': len(full_path),
                                    'meeting_points': full_path,
                                    'found_at_depth': current_depth,
                                    'direction': 'forward_meets_backward'
                                })
                                results['status'] = 'connected'
                                results['total_addresses_examined'] = len(forward_visited) + len(backward_visited)
                                results['visited_forward'] = forward_discovered
                                results['visited_backward'] = backward_discovered
                                results['queued_forward'] = [item[0] for item in list(forward_queue)]
                                results['queued_backward'] = [item[0] for item in list(backward_queue)]
                                return results

                            forward_discovered[neighbor] = new_path
                            forward_queue.append((neighbor, new_path))

                    addresses_explored += 1

                except Exception as e:
                    print(f"    Error: {e}")

            print(f"  Forward explored {addresses_explored}, queue: {len(forward_queue)}")

            # Backward step - ONLY FOLLOW INPUTS
            print(f"\n[<<] Backward BFS (queue: {len(backward_queue)}):")
            backward_queue_size = len(backward_queue)
            addresses_explored = 0

            for _ in range(backward_queue_size):
                if not backward_queue:
                    break

                current, path = backward_queue.popleft()

                # Skip if already visited in THIS SEARCH SESSION
                if current in backward_visited:
                    continue

                backward_visited.add(current)
                print(f"  Exploring: {current}")

                if progress_callback:
                    progress_callback({
                        'visited': len(forward_visited) + len(backward_visited),
                        'current': current,
                        'direction': 'backward'   
                    })

                try:
                    txs = await self.get_address_txs(current, start_block, end_block)

                    for tx in txs:
                        # BACKWARD direction: Only follow INPUTS
                        # Who SENT money TO this address?
                        inputs = self._extract_addresses(tx, 'input')
                        
                        for neighbor in inputs:
                            if neighbor in backward_discovered:
                                continue

                            new_path = path + [neighbor]

                            # Check if meeting point
                            if neighbor in forward_discovered:
                                forward_path = forward_discovered[neighbor]
                                full_path = forward_path + list(reversed(new_path[1:]))
                                
                                print(f"\n[âœ“] MEETING POINT FOUND: {neighbor}")
                                print(f" Path: {' -> '.join(full_path)}")
                                
                                results['connections_found'].append({
                                    'source': full_path[0],
                                    'target': full_path[-1],
                                    'path': full_path,
                                    'path_length': len(full_path),
                                    'path_count': len(full_path),
                                    'meeting_points': full_path,
                                    'found_at_depth': current_depth,
                                    'direction': 'backward_meets_forward'
                                })
                                results['status'] = 'connected'
                                results['total_addresses_examined'] = len(forward_visited) + len(backward_visited)
                                results['visited_forward'] = forward_discovered
                                results['visited_backward'] = backward_discovered
                                results['queued_forward'] = [item[0] for item in list(forward_queue)]
                                results['queued_backward'] = [item[0] for item in list(backward_queue)]
                                return results

                            backward_discovered[neighbor] = new_path
                            backward_queue.append((neighbor, new_path))

                    addresses_explored += 1

                except Exception as e:
                    print(f"    Error: {e}")

            print(f"  Backward explored {addresses_explored}, queue: {len(backward_queue)}")

            print(f"\n[STATUS] Depth {current_depth}:")
            print(f" Forward: visited={len(forward_visited)}, discovered={len(forward_discovered)}, queue={len(forward_queue)}")
            print(f" Backward: visited={len(backward_visited)}, discovered={len(backward_discovered)}, queue={len(backward_queue)}")

            if not forward_queue and not backward_queue:
                print(f"\n[!] Both queues exhausted at depth {current_depth}")
                break

        results['status'] = 'no_connection'
        results['total_addresses_examined'] = len(forward_visited) + len(backward_visited)
        results['visited_forward'] = forward_discovered
        results['visited_backward'] = backward_discovered
        results['queued_forward'] = [item[0] for item in list(forward_queue)]
        results['queued_backward'] = [item[0] for item in list(backward_queue)]

        print(f"\n[âœ—] No connection found")
        print(f" Total addresses examined: {results['total_addresses_examined']}")
        
        return results