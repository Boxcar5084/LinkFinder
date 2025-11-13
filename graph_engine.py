# -*- coding: utf-8 -*-

"""
CLASSIC BIDIRECTIONAL BFS WITH IMMEDIATE MEETING DETECTION
Checks for meeting point the MOMENT a neighbor is discovered.
If the opposite direction has already visited this address, return immediately.
This guarantees no meeting point is missed.
"""

import asyncio
from typing import Set, Dict, List, Tuple, Optional, Any
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

    async def find_connection(self, list_a: List[str], list_b: List[str],
                            max_depth: int = 5,
                            start_block: Optional[int] = None,
                            end_block: Optional[int] = None,
                            progress_callback=None) -> Dict[str, Any]:
        """
        CLASSIC BIDIRECTIONAL BFS WITH IMMEDIATE MEETING DETECTION
        
        Key improvement: After each neighbor discovery in EITHER direction,
        immediately check if it was already visited by the OPPOSITE direction.
        If so, return immediately with the combined path.
        
        This guarantees no meeting point is missed.
        """
        
        results = {
            'connections_found': [],
            'search_depth': max_depth,
            'total_addresses_examined': 0,
            'block_range': (start_block, end_block),
            'status': 'searching'
        }

        print(f"\n[LINK] Linking {len(list_a)} addresses with {len(list_b)} addresses")
        print(f" Max Depth: {max_depth}, Blocks: {start_block} - {end_block}")
        print(f" Strategy: Classic Bidirectional BFS with Immediate Meeting Detection\n")

        # Quick check for immediate matches
        immediate_matches = set(list_a) & set(list_b)
        if immediate_matches:
            matching_addr = immediate_matches.pop()
            print(f"\n[âœ“] IMMEDIATE MATCH FOUND: {matching_addr}")
            print(f" Path: {matching_addr}")
            
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
            return results

        # Initialize separate queues for forward and backward
        forward_queue = deque([(addr, [addr]) for addr in list_a])  # (address, path)
        backward_queue = deque([(addr, [addr]) for addr in list_b])  # (address, path)

        # Visited sets and path tracking
        forward_visited = {addr: [addr] for addr in list_a}  # address -> path to it
        backward_visited = {addr: [addr] for addr in list_b}  # address -> path to it

        # Target sets
        list_a_set = set(list_a)
        list_b_set = set(list_b)

        # ALTERNATING BFS: One step forward, one step backward, repeat
        for current_depth in range(max_depth):
            print(f"\n{'='*70}")
            print(f"[DEPTH {current_depth}]")
            print(f"{'='*70}")

            # ===== FORWARD STEP =====
            print(f"\n[>>] Forward BFS (queue size: {len(forward_queue)}):")
            
            forward_queue_size = len(forward_queue)
            addresses_explored_this_level = 0

            for _ in range(forward_queue_size):
                if not forward_queue:
                    break

                current, path = forward_queue.popleft()

                print(f"  Exploring: {current}")

                try:
                    txs = await self.get_address_txs(current, start_block, end_block)
                    print(f"    Found {len(txs)} transactions")

                    neighbor_count = 0
                    for tx in txs:
                        outputs = self._extract_addresses(tx, 'output')
                        inputs = self._extract_addresses(tx, 'input')
                        neighbors = outputs | inputs

                        for neighbor in neighbors:
                            # Skip if already visited in forward
                            if neighbor in forward_visited:
                                continue

                            new_path = path + [neighbor]

                            # *** CRITICAL: CHECK IF OPPOSITE DIRECTION VISITED THIS ***
                            if neighbor in backward_visited:
                                # MEETING POINT FOUND!
                                backward_path = backward_visited[neighbor]
                                # Combine: forward_path + reversed(backward_path[1:])
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

                                print(f" Total addresses examined: {results['total_addresses_examined']}")
                                return results

                            # Add to visited and queue
                            forward_visited[neighbor] = new_path
                            forward_queue.append((neighbor, new_path))
                            neighbor_count += 1

                    print(f"    Added {neighbor_count} new neighbors")
                    addresses_explored_this_level += 1

                except Exception as e:
                    print(f"    Error: {e}")

            print(f"  Forward explored {addresses_explored_this_level} addresses, queue now: {len(forward_queue)}")

            # ===== BACKWARD STEP =====
            print(f"\n[<<] Backward BFS (queue size: {len(backward_queue)}):")
            
            backward_queue_size = len(backward_queue)
            addresses_explored_this_level = 0

            for _ in range(backward_queue_size):
                if not backward_queue:
                    break

                current, path = backward_queue.popleft()

                print(f"  Exploring: {current}")

                try:
                    txs = await self.get_address_txs(current, start_block, end_block)
                    print(f"    Found {len(txs)} transactions")

                    neighbor_count = 0
                    for tx in txs:
                        inputs = self._extract_addresses(tx, 'input')
                        outputs = self._extract_addresses(tx, 'output')
                        neighbors = inputs | outputs

                        for neighbor in neighbors:
                            # Skip if already visited in backward
                            if neighbor in backward_visited:
                                continue

                            new_path = path + [neighbor]

                            # *** CRITICAL: CHECK IF OPPOSITE DIRECTION VISITED THIS ***
                            if neighbor in forward_visited:
                                # MEETING POINT FOUND!
                                forward_path = forward_visited[neighbor]
                                # Combine: forward_path + reversed(backward_path[1:])
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

                                print(f" Total addresses examined: {results['total_addresses_examined']}")
                                return results

                            # Add to visited and queue
                            backward_visited[neighbor] = new_path
                            backward_queue.append((neighbor, new_path))
                            neighbor_count += 1

                    print(f"    Added {neighbor_count} new neighbors")
                    addresses_explored_this_level += 1

                except Exception as e:
                    print(f"    Error: {e}")

            print(f"  Backward explored {addresses_explored_this_level} addresses, queue now: {len(backward_queue)}")

            # Status
            print(f"\n[STATUS] Depth {current_depth} complete:")
            print(f" Forward visited: {len(forward_visited)}, queue: {len(forward_queue)}")
            print(f" Backward visited: {len(backward_visited)}, queue: {len(backward_queue)}")

            # If both queues empty, stop
            if not forward_queue and not backward_queue:
                print(f"\n[!] Both queues exhausted at depth {current_depth}")
                break

        # No connection found
        results['status'] = 'no_connection'
        results['total_addresses_examined'] = len(forward_visited) + len(backward_visited)

        print(f"\n[âœ—] No connection found within {max_depth} depth levels")
        print(f" Total addresses examined: {results['total_addresses_examined']}")

        return results

    async def find_connection_with_visited_state(self, list_a: List[str], list_b: List[str],
                                                max_depth: int = 5,
                                                start_block: Optional[int] = None,
                                                end_block: Optional[int] = None,
                                                visited_forward: Dict[str, List[str]] = None,
                                                visited_backward: Dict[str, List[str]] = None,
                                                progress_callback=None) -> Dict[str, Any]:
        """Find connections with checkpoint state, using classic bidirectional BFS."""

        if visited_forward is None:
            visited_forward = {addr: [addr] for addr in list_a}
        if visited_backward is None:
            visited_backward = {addr: [addr] for addr in list_b}

        results = {
            'connections_found': [],
            'search_depth': max_depth,
            'total_addresses_examined': len(visited_forward) + len(visited_backward),
            'block_range': (start_block, end_block),
            'status': 'searching'
        }

        print(f"\n[LINK] Linking {len(list_a)} addresses with {len(list_b)} addresses")
        print(f" Max Depth: {max_depth}")
        print(f" Resuming with {len(visited_forward)} + {len(visited_backward)} visited\n")

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
            return results

        # Build initial queues from unvisited addresses
        forward_queue = deque()
        for addr, path in visited_forward.items():
            forward_queue.append((addr, path))

        backward_queue = deque()
        for addr, path in visited_backward.items():
            backward_queue.append((addr, path))

        list_a_set = set(list_a)
        list_b_set = set(list_b)

        # ALTERNATING BFS
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

                print(f"  Exploring: {current}")

                try:
                    txs = await self.get_address_txs(current, start_block, end_block)
                    print(f"    Found {len(txs)} transactions")

                    neighbor_count = 0
                    for tx in txs:
                        outputs = self._extract_addresses(tx, 'output')
                        inputs = self._extract_addresses(tx, 'input')
                        neighbors = outputs | inputs

                        for neighbor in neighbors:
                            if neighbor in visited_forward:
                                continue

                            new_path = path + [neighbor]

                            if neighbor in visited_backward:
                                backward_path = visited_backward[neighbor]
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
                                results['total_addresses_examined'] = len(visited_forward) + len(visited_backward)
                                print(f" Total addresses examined: {results['total_addresses_examined']}")
                                return results

                            visited_forward[neighbor] = new_path
                            forward_queue.append((neighbor, new_path))
                            neighbor_count += 1

                    print(f"    Added {neighbor_count} new neighbors")
                    addresses_explored += 1

                except Exception as e:
                    print(f"    Error: {e}")

            print(f"  Forward explored {addresses_explored}, queue now: {len(forward_queue)}")

            # Backward step
            print(f"\n[<<] Backward BFS (queue: {len(backward_queue)}):")
            backward_queue_size = len(backward_queue)
            addresses_explored = 0

            for _ in range(backward_queue_size):
                if not backward_queue:
                    break

                current, path = backward_queue.popleft()

                print(f"  Exploring: {current}")

                try:
                    txs = await self.get_address_txs(current, start_block, end_block)
                    print(f"    Found {len(txs)} transactions")

                    neighbor_count = 0
                    for tx in txs:
                        inputs = self._extract_addresses(tx, 'input')
                        outputs = self._extract_addresses(tx, 'output')
                        neighbors = inputs | outputs

                        for neighbor in neighbors:
                            if neighbor in visited_backward:
                                continue

                            new_path = path + [neighbor]

                            if neighbor in visited_forward:
                                forward_path = visited_forward[neighbor]
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
                                results['total_addresses_examined'] = len(visited_forward) + len(visited_backward)
                                print(f" Total addresses examined: {results['total_addresses_examined']}")
                                return results

                            visited_backward[neighbor] = new_path
                            backward_queue.append((neighbor, new_path))
                            neighbor_count += 1

                    print(f"    Added {neighbor_count} new neighbors")
                    addresses_explored += 1

                except Exception as e:
                    print(f"    Error: {e}")

            print(f"  Backward explored {addresses_explored}, queue now: {len(backward_queue)}")

            print(f"\n[STATUS] Depth {current_depth} complete:")
            print(f" Forward visited: {len(visited_forward)}, queue: {len(forward_queue)}")
            print(f" Backward visited: {len(visited_backward)}, queue: {len(backward_queue)}")

            if not forward_queue and not backward_queue:
                print(f"\n[!] Both queues exhausted")
                break

        results['status'] = 'no_connection'
        results['total_addresses_examined'] = len(visited_forward) + len(visited_backward)

        print(f"\n[âœ—] No connection found")
        return results

    # Legacy methods for backward compatibility
    async def trace_forward_with_path(self, address: str, max_depth: int = 5,
                                     start_block: Optional[int] = None,
                                     end_block: Optional[int] = None,
                                     target_set: Optional[Set[str]] = None,
                                     visited: Optional[Set[str]] = None,
                                     progress_callback=None) -> Tuple[Set[str], bool, List[str]]:
        """Legacy forward trace"""
        if visited is None:
            visited = set()

        local_visited = set()
        queue = deque([(address, 0, [address])])

        while queue:
            current, depth, path = queue.popleft()

            if target_set and current in target_set:
                visited.add(current)
                local_visited.add(current)
                return local_visited, True, path

            if current in visited or current in local_visited or depth >= max_depth:
                continue

            local_visited.add(current)
            visited.add(current)

            try:
                txs = await self.get_address_txs(current, start_block, end_block)
                for tx in txs:
                    outputs = self._extract_addresses(tx, 'output')
                    inputs = self._extract_addresses(tx, 'input')
                    for addr in outputs | inputs:
                        if addr not in visited and addr not in local_visited:
                            if target_set and addr in target_set:
                                local_visited.add(addr)
                                visited.add(addr)
                                return local_visited, True, path + [addr]
                            queue.append((addr, depth + 1, path + [addr]))
            except:
                pass

        return local_visited, False, []

    async def trace_backward_with_path(self, address: str, max_depth: int = 5,
                                      start_block: Optional[int] = None,
                                      end_block: Optional[int] = None,
                                      target_set: Optional[Set[str]] = None,
                                      visited: Optional[Set[str]] = None,
                                      progress_callback=None) -> Tuple[Set[str], bool, List[str]]:
        """Legacy backward trace"""
        if visited is None:
            visited = set()

        local_visited = set()
        queue = deque([(address, 0, [address])])

        while queue:
            current, depth, path = queue.popleft()

            if target_set and current in target_set:
                visited.add(current)
                local_visited.add(current)
                return local_visited, True, path

            if current in visited or current in local_visited or depth >= max_depth:
                continue

            local_visited.add(current)
            visited.add(current)

            try:
                txs = await self.get_address_txs(current, start_block, end_block)
                for tx in txs:
                    inputs = self._extract_addresses(tx, 'input')
                    outputs = self._extract_addresses(tx, 'output')
                    for addr in inputs | outputs:
                        if addr not in visited and addr not in local_visited:
                            if target_set and addr in target_set:
                                local_visited.add(addr)
                                visited.add(addr)
                                return local_visited, True, path + [addr]
                            queue.append((addr, depth + 1, path + [addr]))
            except:
                pass

        return local_visited, False, []