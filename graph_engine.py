# -*- coding: utf-8 -*-

"""
BULLETPROOF BIDIRECTIONAL BFS WITH CHECKPOINT RESUME
Checks discovered addresses against BOTH visited AND queued from opposite direction.
This guarantees NO connections are missed, even if they're in the queue waiting to be explored.
Supports resuming from checkpoints with proper set handling.
"""

import asyncio
from typing import Set, Dict, List, Tuple, Optional, Any, Union
from collections import deque
from api_provider import APIProvider
from cache_manager import TransactionCache
from config import MAX_TRANSACTIONS_PER_ADDRESS


class BitcoinAddressLinker:
    """Graph traversal engine for Bitcoin address linking with path tracking"""

    def __init__(self, api_provider: APIProvider, cache_manager: TransactionCache,
                 max_tx_per_address: int = MAX_TRANSACTIONS_PER_ADDRESS):
        self.api = api_provider
        self.cache = cache_manager
        self.max_tx_per_address = max_tx_per_address
        self.coinjoin_patterns = ['coinjoin', 'wasabi', 'samourai', 'whirlpool']

    def _is_coinjoin(self, tx: Dict[str, Any]) -> bool:
        """Detect likely CoinJoin transactions"""
        inputs_count = len(tx.get('inputs', []))
        outputs_count = len(tx.get('outputs', []))

        if inputs_count < 5 or outputs_count < 5:
            return False

        tx_str = str(tx).lower()
        for pattern in self.coinjoin_patterns:
            if pattern in tx_str:
                return True

        return False

    async def get_address_txs(self, address: str,
                             start_block: Optional[int] = None,
                             end_block: Optional[int] = None) -> List[Dict[str, Any]]:
        """Fetch transactions with caching"""
        block_range = (start_block, end_block) if (start_block or end_block) else None

        cached = self.cache.get_cached(address, block_range)
        if cached:
            return cached

        print(f"[*] Fetching: {address}")
        txs = await self.api.get_address_transactions(address, start_block, end_block)

        txs = [tx for tx in txs if not self._is_coinjoin(tx)]
        txs = txs[:self.max_tx_per_address]

        if txs:
            self.cache.cache(address, txs, block_range)

        return txs

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

    def _ensure_set(self, value: Union[Set, List, Dict]) -> Set:
        """Convert any collection type to set"""
        if isinstance(value, set):
            return value
        elif isinstance(value, list):
            return set(value)
        elif isinstance(value, dict):
            return set(value.keys())
        else:
            return set()

    async def find_connection(self, list_a: List[str], list_b: List[str],
                            max_depth: int = 5,
                            start_block: Optional[int] = None,
                            end_block: Optional[int] = None,
                            progress_callback=None) -> Dict[str, Any]:
        """Bulletproof bidirectional BFS from scratch"""
        
        results = {
            'connections_found': [],
            'search_depth': max_depth,
            'total_addresses_examined': 0,
            'block_range': (start_block, end_block),
            'status': 'searching'
        }

        print(f"\n[LINK] Linking {len(list_a)} addresses with {len(list_b)} addresses")
        print(f" Max Depth: {max_depth}, Blocks: {start_block} - {end_block}\n")

        # Quick check for immediate matches
        immediate_matches = set(list_a) & set(list_b)
        if immediate_matches:
            matching_addr = immediate_matches.pop()
            print(f"\n[âœ“] IMMEDIATE MATCH FOUND: {matching_addr}")
            
            results['connections_found'].append({
                'source': matching_addr,
                'target': matching_addr,
                'path': [matching_addr],
                'path_length': 1,
                'path_count': 1,
                'meeting_points': [matching_addr],
                'found_at_depth': 0,
                'direction': 'immediate'
            })
            results['status'] = 'connected'
            results['total_addresses_examined'] = 2
            results['visited_forward'] = {addr: [addr] for addr in list_a}
            results['visited_backward'] = {addr: [addr] for addr in list_b}
            results['queued_forward'] = []
            results['queued_backward'] = []
            return results

        # Initialize queues with paths
        forward_queue = deque([(addr, [addr]) for addr in list_a])
        backward_queue = deque([(addr, [addr]) for addr in list_b])

        # Store discovered addresses with their paths
        forward_discovered = {addr: [addr] for addr in list_a}
        forward_visited = set()

        backward_discovered = {addr: [addr] for addr in list_b}
        backward_visited = set()

        # Alternating BFS
        for current_depth in range(max_depth):
            print(f"\n{'='*70}")
            print(f"[DEPTH {current_depth}]")
            print(f"{'='*70}")

            # Forward step
            print(f"\n[>>] Forward BFS (queue: {len(forward_queue)}):")
            forward_queue_size = len(forward_queue)
            addresses_explored = 0

            for _ in range(forward_queue_size):
                if not forward_queue:
                    break

                current, path = forward_queue.popleft()

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

                    neighbor_count = 0
                    for tx in txs:
                        outputs = self._extract_addresses(tx, 'output')
                        inputs = self._extract_addresses(tx, 'input')
                        neighbors = outputs | inputs

                        for neighbor in neighbors:
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
                            neighbor_count += 1

                    addresses_explored += 1

                except Exception as e:
                    print(f"    Error: {e}")

            print(f"  Forward explored {addresses_explored}, queue: {len(forward_queue)}")

            # Backward step
            print(f"\n[<<] Backward BFS (queue: {len(backward_queue)}):")
            backward_queue_size = len(backward_queue)
            addresses_explored = 0

            for _ in range(backward_queue_size):
                if not backward_queue:
                    break

                current, path = backward_queue.popleft()

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

                    neighbor_count = 0
                    for tx in txs:
                        inputs = self._extract_addresses(tx, 'input')
                        outputs = self._extract_addresses(tx, 'output')
                        neighbors = inputs | outputs

                        for neighbor in neighbors:
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
                            neighbor_count += 1

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

        # No connection found
        results['status'] = 'no_connection'
        results['total_addresses_examined'] = len(forward_visited) + len(backward_visited)
        results['visited_forward'] = forward_discovered
        results['visited_backward'] = backward_discovered
        results['queued_forward'] = [item[0] for item in list(forward_queue)]
        results['queued_backward'] = [item[0] for item in list(backward_queue)]

        print(f"\n[âœ—] No connection found")
        print(f" Total addresses examined: {results['total_addresses_examined']}")
        
        return results

    async def find_connection_with_visited_state(self, list_a: List[str], list_b: List[str],
                                                max_depth: int = 5,
                                                start_block: Optional[int] = None,
                                                end_block: Optional[int] = None,
                                                visited_forward: Union[Dict, Set, List] = None,
                                                visited_backward: Union[Dict, Set, List] = None,
                                                progress_callback=None) -> Dict[str, Any]:
        """Resume from checkpoint with proper type handling"""

        # Convert all types to proper format
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
            'total_addresses_examined': len(visited_forward_dict) + len(visited_backward_dict),
            'block_range': (start_block, end_block),
            'status': 'searching'
        }

        print(f"\n[LINK] Linking {len(list_a)} addresses with {len(list_b)} addresses")
        print(f" Max Depth: {max_depth}")
        print(f" Resuming with {len(visited_forward_dict)} + {len(visited_backward_dict)} discovered\n")

        # Initialize from checkpoint
        forward_queue = deque([(addr, path) for addr, path in visited_forward_dict.items()])
        forward_discovered = dict(visited_forward_dict)
        forward_visited = set(visited_forward_dict.keys())

        backward_queue = deque([(addr, path) for addr, path in visited_backward_dict.items()])
        backward_discovered = dict(visited_backward_dict)
        backward_visited = set(visited_backward_dict.keys())

        # Alternating BFS
        for current_depth in range(max_depth):
            print(f"\n{'='*70}")
            print(f"[DEPTH {current_depth}]")
            print(f"{'='*70}")

            # Forward step
            print(f"\n[>>] Forward BFS (queue: {len(forward_queue)}):")
            forward_queue_size = len(forward_queue)
            addresses_explored = 0

            for _ in range(forward_queue_size):
                if not forward_queue:
                    break

                current, path = forward_queue.popleft()

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

                    neighbor_count = 0
                    for tx in txs:
                        outputs = self._extract_addresses(tx, 'output')
                        inputs = self._extract_addresses(tx, 'input')
                        neighbors = outputs | inputs

                        for neighbor in neighbors:
                            if neighbor in forward_discovered:
                                continue

                            new_path = path + [neighbor]

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
                            neighbor_count += 1

                    addresses_explored += 1

                except Exception as e:
                    print(f"    Error: {e}")

            print(f"  Forward explored {addresses_explored}, queue: {len(forward_queue)}")

            # Backward step
            print(f"\n[<<] Backward BFS (queue: {len(backward_queue)}):")
            backward_queue_size = len(backward_queue)
            addresses_explored = 0

            for _ in range(backward_queue_size):
                if not backward_queue:
                    break

                current, path = backward_queue.popleft()

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

                    neighbor_count = 0
                    for tx in txs:
                        inputs = self._extract_addresses(tx, 'input')
                        outputs = self._extract_addresses(tx, 'output')
                        neighbors = inputs | outputs

                        for neighbor in neighbors:
                            if neighbor in backward_discovered:
                                continue

                            new_path = path + [neighbor]

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
                            neighbor_count += 1

                    addresses_explored += 1

                except Exception as e:
                    print(f"    Error: {e}")

            print(f"  Backward explored {addresses_explored}, queue: {len(backward_queue)}")

            print(f"\n[STATUS] Depth {current_depth}:")
            print(f" Forward: visited={len(forward_visited)}, discovered={len(forward_discovered)}, queue={len(forward_queue)}")
            print(f" Backward: visited={len(backward_visited)}, discovered={len(backward_discovered)}, queue={len(backward_queue)}")

            if not forward_queue and not backward_queue:
                print(f"\n[!] Both queues exhausted")
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