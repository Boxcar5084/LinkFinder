# -*- coding: utf-8 -*-
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

        # CoinJoin characteristics: many inputs and outputs
        if inputs_count < 5 or outputs_count < 5:
            return False

        # Check for known patterns
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

        # Check cache
        cached = self.cache.get_cached(address, block_range)
        if cached:
            return cached

        # Fetch from API
        print(f"[*] Fetching: {address}")
        txs = await self.api.get_address_transactions(address, start_block, end_block)

        # Filter and limit
        txs = [tx for tx in txs if not self._is_coinjoin(tx)]
        txs = txs[:self.max_tx_per_address]

        # Cache result
        if txs:
            self.cache.cache(address, txs, block_range)

        return txs

    def _extract_addresses(self, tx: Dict[str, Any], direction: str = 'output') -> Set[str]:
        """Extract addresses - handles both blockchain.info and Mempool formats"""
        addresses = set()

        if not isinstance(tx, dict):
            return addresses

        # blockchain.info format first
        if direction == 'output':
            items = tx.get('out')
        else:
            items = tx.get('inputs')

        # If blockchain.info format exists, use it
        if items and isinstance(items, list):
            for item in items:
                if isinstance(item, dict):
                    addr = item.get('addr')
                    if addr and addr != 'None':
                        addresses.add(addr)
            return addresses  # Return here if we found items

        # Fall back to Mempool format
        if direction == 'output':
            items = tx.get('vout', [])
        else:
            items = tx.get('vin', [])

        if not isinstance(items, list):
            return addresses

        for item in items:
            if not isinstance(item, dict):
                continue

            # Mempool format (outputs)
            if direction == 'output':
                addr = item.get('scriptpubkey_address')
                if addr and addr != 'None':
                    addresses.add(addr)
            # Mempool format (inputs)
            else:
                prevout = item.get('prevout')
                if isinstance(prevout, dict):
                    addr = prevout.get('scriptpubkey_address')
                    if addr and addr != 'None':
                        addresses.add(addr)

        return addresses

    async def trace_forward_with_path(
        self, 
        address: str, 
        max_depth: int = 5,
        start_block: Optional[int] = None,
        end_block: Optional[int] = None,
        target_set: Optional[Set[str]] = None,
        visited: Optional[Set[str]] = None,
        progress_callback=None  #  ADD THIS LINE
    ) -> Tuple[Set[str], bool, List[str]]:

        """Trace forward AND track the path to target, respecting checkpoint state"""
        if visited is None:
            visited = set()

        local_visited = set()
        # Queue stores (address, depth, path_to_address)
        queue = deque([(address, 0, [address])])
        found_target = False
        found_path = []

        while queue:
            current, depth, path = queue.popleft()

            # Skip if already visited globally (from checkpoint)
            if current in visited:
                continue

            if current in local_visited or depth >= max_depth:
                continue

            local_visited.add(current)
            visited.add(current)  # Update global visited set
            print(f" [->] Depth {depth}: {current}")
            # NEW: Report progress back to main.py
            if progress_callback:
                progress_callback({
                    'visited': len(visited),
                    'current': current,
                    'direction': 'forward' 
                })
        # Check if target found
            if target_set and current in target_set:
                print(f"\n[*] TARGET FOUND at Depth {depth}!")
                found_target = True
                found_path = path
                return local_visited, found_target, found_path

            try:
                txs = await self.get_address_txs(current, start_block, end_block)
                for tx in txs:
                    outputs = self._extract_addresses(tx, 'output')
                    inputs = self._extract_addresses(tx, 'input')

                    for addr in outputs | inputs:
                        # Skip if already visited globally
                        if addr in visited:
                            continue

                        if addr not in local_visited:
                            # Check if target
                            if target_set and addr in target_set:
                                local_visited.add(addr)
                                visited.add(addr)
                                new_path = path + [addr]
                                print(f" [->] Depth {depth + 1}: {addr}")
                                print(f"\n[*] TARGET FOUND at Depth {depth + 1}!")
                                return local_visited, True, new_path

                            new_path = path + [addr]
                            queue.append((addr, depth + 1, new_path))

            except Exception as e:
                print(f" [ERR] Error tracing {current}: {e}")

        return local_visited, found_target, found_path

    async def trace_backward_with_path(
        self, 
        address: str, 
        max_depth: int = 5,
        start_block: Optional[int] = None,
        end_block: Optional[int] = None,
        target_set: Optional[Set[str]] = None,
        visited: Optional[Set[str]] = None,
        progress_callback=None  # â† ADD THIS LINE
    ) -> Tuple[Set[str], bool, List[str]]:
        """Trace backward AND track the path to target, respecting checkpoint state"""
        if visited is None:
            visited = set()

        local_visited = set()
        # Queue stores (address, depth, path_to_address)
        queue = deque([(address, 0, [address])])
        found_target = False
        found_path = []

        while queue:
            current, depth, path = queue.popleft()

            # Skip if already visited globally (from checkpoint)
            if current in visited:
                continue

            if current in local_visited or depth >= max_depth:
                continue

            local_visited.add(current)
            visited.add(current)  # Update global visited set
            print(f" [<-] Depth {depth}: {current}")

            # Check if target found
            if target_set and current in target_set:
                print(f"\n[*] TARGET FOUND at Depth {depth}!")
                found_target = True
                found_path = path
                return local_visited, found_target, found_path

            try:
                txs = await self.get_address_txs(current, start_block, end_block)
                for tx in txs:
                    inputs = self._extract_addresses(tx, 'input')
                    outputs = self._extract_addresses(tx, 'output')

                    for addr in inputs | outputs:
                        # Skip if already visited globally
                        if addr in visited:
                            continue

                        if addr not in local_visited:
                            # Check if target
                            if target_set and addr in target_set:
                                local_visited.add(addr)
                                visited.add(addr)
                                new_path = path + [addr]
                                print(f" [<-] Depth {depth + 1}: {addr}")
                                print(f"\n[*] TARGET FOUND at Depth {depth + 1}!")
                                return local_visited, True, new_path

                            new_path = path + [addr]
                            queue.append((addr, depth + 1, new_path))

            except Exception as e:
                print(f" [ERR] Error tracing {current}: {e}")

        return local_visited, found_target, found_path

    async def find_connection_with_visited_state(self, list_a: List[str], list_b: List[str],
        max_depth: int = 5,
        start_block: Optional[int] = None,
        end_block: Optional[int] = None,
        visited_forward: Set[str] = None,
        visited_backward: Set[str] = None,
        visited: Set[str] = None,
        progress_callback=None) -> Dict[str, Any]:  # ADD THIS
        """
        Find connections while respecting already-visited addresses from checkpoint.
        This allows resuming from a checkpoint without re-tracing addresses.
        """
        
        # Initialize visited sets from checkpoint, or create fresh ones
        if visited_forward is None:
            visited_forward = set()
        if visited_backward is None:
            visited_backward = set()
        if visited is None:
            visited = set()
        
        results = {
            'connections_found': [],
            'search_depth': max_depth,
            'total_addresses_examined': len(visited),
            'block_range': (start_block, end_block),
            'status': 'searching'
        }

        print(f"\n[LINK] Linking {len(list_a)} addresses with {len(list_b)} addresses")
        print(f" Depth: {max_depth}, Blocks: {start_block} - {end_block}")
        if visited:
            print(f" Resuming with {len(visited)} previously visited addresses\n")
        else:
            print()

        list_b_set = set(list_b)

        # FORWARD TRACE (with checkpoint state)
        print("[>>] Forward tracing (List A):")
        for idx, addr in enumerate(list_a, 1):
            print(f"[{idx}/{len(list_a)}] {addr}")
            
            forward_set, found_in_forward, path = await self.trace_forward_with_path(
                addr, max_depth, start_block, end_block, list_b_set,
                visited=visited_forward  # Pass visited set
            )

            if found_in_forward:
                overlap = forward_set & list_b_set
                for target_addr in overlap:
                    results['connections_found'].append({
                        'source': addr,
                        'target': target_addr,
                        'path': path,
                        'path_length': len(path),
                        'path_count': len(path),
                        'meeting_points': path
                    })
                results['status'] = 'connected'
                results['total_addresses_examined'] = len(visited_forward)
                print(f"\n[OK] Connection established!")
                print(f" From: {addr}")
                print(f" To: {list(overlap)}")
                print(f" Path: {' -> '.join(path)}")
                return results

            # Update visited set
            visited_forward.update(forward_set)
            visited.update(forward_set)

        # BACKWARD TRACE (with checkpoint state)
        print("\n[<<] Backward tracing (List B):")
        list_a_set = set(list_a)
        for idx, addr in enumerate(list_b, 1):
            print(f"[{idx}/{len(list_b)}] {addr}")
            
            backward_set, found_in_backward, path = await self.trace_backward_with_path(
                addr, max_depth, start_block, end_block, list_a_set,
                visited=visited_backward  # Pass visited set
            )

            if found_in_backward:
                overlap = backward_set & list_a_set
                for source_addr in overlap:
                    reversed_path = list(reversed(path))
                    results['connections_found'].append({
                        'source': source_addr,
                        'target': addr,
                        'path': path,
                        'path_length': len(path),
                        'path_count': len(path),
                        'meeting_points': path
                    })
                results['status'] = 'connected'
                results['total_addresses_examined'] = len(visited_backward)
                print(f"\n[OK] Connection established!")
                print(f" From: {list(overlap)}")
                print(f" To: {addr}")
                print(f" Path: {' -> '.join(reversed_path)}")
                return results

            # Update visited set
            visited_backward.update(backward_set)
            visited.update(backward_set)

        # No connection found
        results['status'] = 'no_connection'
        results['total_addresses_examined'] = len(visited)
        print(f"\n[ERR] No connection found between lists")
        print(f" Total addresses examined: {len(visited)}")
        return results


    async def find_connection(self, list_a: List[str], list_b: List[str],
        max_depth: int = 5,
        start_block: Optional[int] = None,
        end_block: Optional[int] = None,
        progress_callback=None) -> Dict[str, Any]:  # ADD THIS
        """Find connections between two address lists with full path tracking"""
        results = {
            'connections_found': [],
            'search_depth': max_depth,
            'total_addresses_examined': 0,
            'block_range': (start_block, end_block),
            'status': 'searching'
        }

        print(f"\n[LINK] Linking {len(list_a)} addresses with {len(list_b)} addresses")
        print(f" Depth: {max_depth}, Blocks: {start_block} - {end_block}\n")

        # Convert list_b to set for O(1) lookup
        list_b_set = set(list_b)

        # Trace forward from list_a with path tracking
        print("[>>] Forward tracing (List A):")
        visited_forward = set()
        for idx, addr in enumerate(list_a, 1):
            print(f"[{idx}/{len(list_a)}] {addr}")
            forward_set, found_in_forward, path = await self.trace_forward_with_path(
            addr, max_depth, start_block, end_block, list_b_set, visited=visited_forward,
            progress_callback=progress_callback  # ADD THIS
        )  
            # NEW: Report progress back to main.py
            if progress_callback:
                progress_callback({
                    'visited': len(visited_forward),
                    'current': addr
                    
                })

            if found_in_forward:
                # Found connection during forward trace
                overlap = forward_set & list_b_set
                for target_addr in overlap:
                    results['connections_found'].append({
                        'source': addr,
                        'target': target_addr,
                        'path': path,
                        'path_length': len(path),
                        'path_count': len(path),
                        'meeting_points': path
                    })
                results['status'] = 'connected'
                results['total_addresses_examined'] = len(visited_forward)
                print(f"\n[OK] Connection established!")
                print(f" From: {addr}")
                print(f" To: {list(overlap)}")
                print(f" Path: {' -> '.join(path)}")
                return results  # EXIT IMMEDIATELY

            visited_forward.update(forward_set)

        # If forward didn't find, trace backward from list_b
        print("\n[<<] Backward tracing (List B):")
        list_a_set = set(list_a)
        visited_backward = set()
        for idx, addr in enumerate(list_b, 1):
            print(f"[{idx}/{len(list_b)}] {addr}")
            backward_set, found_in_backward, path = await self.trace_backward_with_path(
            addr, max_depth, start_block, end_block, list_a_set, visited=visited_backward,
            progress_callback=progress_callback  # ADD THIS
        )

            if found_in_backward:
                # Found connection during backward trace
                overlap = backward_set & list_a_set
                for source_addr in overlap:
                    reversed_path = list(reversed(path))
                    results['connections_found'].append({
                        'source': source_addr,
                        'target': addr,
                        'path': path,
                        'path_length': len(path),
                        'path_count': len(path),
                        'meeting_points': path
                    })
                results['status'] = 'connected'
                results['total_addresses_examined'] = len(visited_backward)
                print(f"\n[OK] Connection established!")
                print(f" From: {list(overlap)}")
                print(f" To: {addr}")
                print(f" Path: {' -> '.join(reversed_path)}")
                return results  # EXIT IMMEDIATELY

            visited_backward.update(backward_set)

        # No connection found
        results['status'] = 'no_connection'
        results['total_addresses_examined'] = 0
        print(f"\n[ERR] No connection found between lists")
        return results