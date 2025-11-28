# -*- coding: utf-8 -*-
"""
Bitcoin Address Linker - Graph Engine with Bidirectional BFS
Connects two sets of Bitcoin addresses through transaction chains.
"""

import asyncio
from typing import Set, Dict, List, Tuple, Optional, Any, Union
from collections import deque
from api_provider import APIProvider, ConnectionLostError
from cache_manager import TransactionCache
from config import (
    MAX_TRANSACTIONS_PER_ADDRESS,
    SKIP_MIXER_INPUT_THRESHOLD,
    SKIP_MIXER_OUTPUT_THRESHOLD,
    SKIP_DISTRIBUTION_MAX_INPUTS,
    SKIP_DISTRIBUTION_MIN_OUTPUTS,
    EXCHANGE_WALLET_THRESHOLD,
    MAX_INPUT_ADDRESSES_PER_TX,
    MAX_OUTPUT_ADDRESSES_PER_TX,
    USE_CACHE
)


class BitcoinAddressLinker:
    """Graph traversal engine for Bitcoin address linking with path tracking"""

    def __init__(self, api_provider: APIProvider, cache_manager: TransactionCache,
                 max_tx_per_address: int = MAX_TRANSACTIONS_PER_ADDRESS):
        self.api = api_provider
        self.cache = cache_manager
        self.max_tx_per_address = max_tx_per_address
        self._exchange_wallet_cache = {}  # Cache exchange wallet status
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

    async def _is_exchange_wallet(self, address: str,
                                  start_block: Optional[int] = None,
                                  end_block: Optional[int] = None) -> bool:
        """
        Check if an address is an exchange wallet (has excessive transactions).
        Uses cached status to avoid repeated API calls.
        This is a lightweight check that uses the cache first.
        """
        # Check cache first
        if address in self._exchange_wallet_cache:
            return self._exchange_wallet_cache[address]
        
        # Check if we have cached transactions - if so, use that count (with fallback mechanism)
        if not USE_CACHE:
            return False  # Cache disabled, can't check from cache
        
        block_range = (start_block, end_block) if (start_block is not None or end_block is not None) else None
        cached_txs = self.cache.get_cached_with_fallback(address, block_range)
        
        if cached_txs is not None:
            # We have cached transactions, check the count
            # If cached count is >= threshold, we know it's an exchange wallet
            if len(cached_txs) >= EXCHANGE_WALLET_THRESHOLD:
                self._exchange_wallet_cache[address] = True
                return True
            # If cached and below threshold, mark as not exchange
            self._exchange_wallet_cache[address] = False
            return False
        
        # No cache - we don't know yet, but we'll find out when get_address_txs is called
        # For now, assume not an exchange wallet (will be updated when transactions are fetched)
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
        block_range = (start_block, end_block) if (start_block is not None or end_block is not None) else None

        # Check cache for exchange wallet status first
        if address in self._exchange_wallet_cache and self._exchange_wallet_cache[address]:
            print(f"  [SKIP] Skipping exchange wallet (cached): {address}")
            return []

        # Try to get from cache FIRST (with fallback mechanism) - only if cache is enabled
        cached = None
        if USE_CACHE:
            cached = self.cache.get_cached_with_fallback(address, block_range)
            if cached is None:
                # Explicitly log that we're about to make an API call
                print(f"[DEBUG] Cache returned None for {address}, proceeding to API call", flush=True)
        
        if cached:
            # Check if cached address is an exchange wallet
            # If we have cached transactions and count is > threshold, mark as exchange
            if len(cached) >= EXCHANGE_WALLET_THRESHOLD:
                self._exchange_wallet_cache[address] = True
                print(f"  [SKIP] Skipping exchange wallet (from cache): {address} ({len(cached)} transactions)")
                return []
            
            # CRITICAL FIX: Resolve input addresses for cached transactions if using ElectrumX
            # Cached transactions may not have input addresses resolved
            if hasattr(self.api, '_resolve_input_addresses'):
                needs_resolution = False
                for tx in cached:
                    vin_list = tx.get('vin', [])
                    if vin_list:
                        for vin in vin_list:
                            # Check if input address is missing (not coinbase)
                            if not vin.get('coinbase') and not vin.get('is_coinbase'):
                                if not vin.get('prevout', {}).get('scriptpubkey_address'):
                                    needs_resolution = True
                                    break
                    if needs_resolution:
                        break
                
                if needs_resolution:
                    print(f"    [CACHE] Resolving input addresses for {len(cached)} cached transactions...")
                    resolved_txs = []
                    for tx in cached:
                        resolved_tx = await self.api._resolve_input_addresses(tx)
                        resolved_txs.append(resolved_tx)
                    # Update cache with resolved transactions
                    if USE_CACHE:
                        self.cache.store(address, resolved_txs, block_range)
                    return resolved_txs
            
            return cached

        # Cache miss or cache disabled - fetch from API
        # IMPORTANT: This print should appear after every cache miss
        print(f"[*] Fetching: {address} (cache miss, making API call)", flush=True)
        try:
            txs = await self.api.get_address_transactions(address, start_block, end_block)
        except ConnectionLostError as e:
            # Re-raise connection loss errors - these should trigger checkpoint save
            print(f"  [CONN_LOST] Connection lost while fetching {address}: {e}", flush=True)
            raise
        except Exception as e:
            print(f"  [ERROR] API call failed for {address}: {e}", flush=True)
            raise

        # Validate txs is a list
        if not isinstance(txs, list):
            print(f"  [WARN] API returned non-list: {type(txs)}")
            return []

        # Check if this is an exchange wallet based on transaction count
        if len(txs) > EXCHANGE_WALLET_THRESHOLD:
            self._exchange_wallet_cache[address] = True
            print(f"  [SKIP] Exchange wallet detected: {address} ({len(txs)} transactions)")
            return []

        # Mark as not an exchange wallet
        self._exchange_wallet_cache[address] = False

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

        # Cache the filtered results using .store() method - only if cache is enabled
        if USE_CACHE and filtered_txs:
            try:
                print(f"  [DEBUG] Attempting to cache {len(filtered_txs)} transactions for {address}")
                self.cache.store(address, filtered_txs, block_range)
                print(f"  [DEBUG] Cache store completed for {address}")
            except Exception as e:
                print(f"  [WARN] Error caching: {e}")
                import traceback
                traceback.print_exc()
        elif not USE_CACHE:
            print(f"  [DEBUG] Cache disabled - not storing transactions for {address}")
        else:
            print(f"  [DEBUG] No transactions to cache for {address} (filtered_txs is empty)")

        return filtered_txs

    async def find_connection(self, list_a: List[str], list_b: List[str],
                            max_depth: int = 5,
                            start_block: Optional[int] = None,
                            end_block: Optional[int] = None,
                            progress_callback=None,
                            connection_callback=None) -> Dict[str, Any]:
        """Fresh trace - calls find_connection_with_visited_state with empty state"""
        return await self.find_connection_with_visited_state(
            list_a, list_b, max_depth, start_block, end_block,
            visited_forward=None,
            visited_backward=None,
            queued_forward=None,
            queued_backward=None,
            progress_callback=progress_callback,
            connection_callback=connection_callback
        )


    async def find_connection_with_visited_state(self, list_a: List[str], list_b: List[str],
                                                max_depth: int = 5,
                                                start_block: Optional[int] = None,
                                                end_block: Optional[int] = None,
                                                visited_forward: Union[Dict, Set, List] = None,
                                                visited_backward: Union[Dict, Set, List] = None,
                                                queued_forward: Union[List] = None,
                                                queued_backward: Union[List] = None,
                                                connections_found: Optional[List] = None,
                                                progress_callback=None,
                                                connection_callback=None) -> Dict[str, Any]:
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

        # Initialize with existing connections from checkpoint if provided
        existing_connections = connections_found if connections_found is not None else []
        # Track existing connection keys to avoid duplicates (use source+target as key)
        existing_connection_keys = set()
        for conn in existing_connections:
            if isinstance(conn, dict):
                key = (conn.get('source'), conn.get('target'))
                existing_connection_keys.add(key)

        results = {
            'connections_found': existing_connections.copy() if existing_connections else [],
            'search_depth': max_depth,
            'total_addresses_examined': 0,
            'block_range': (start_block, end_block),
            'status': 'searching'
        }
        
        # Track which list_b addresses have been matched
        matched_targets = set()

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
        # Only mark as visited if they were actually explored (not just discovered)
        # Addresses in queued_backward were discovered but NOT explored, so exclude them from visited
        backward_visited = set(addr for addr in visited_backward_dict.keys() if addr not in queued_backward_set)
        backward_discovered = dict(visited_backward_dict)
        
        backward_queue = deque()
        if queued_backward:
            print(f"[DEBUG] Loading {len(queued_backward)} queued backward addresses (discovered but not yet explored)")
            for addr in queued_backward:
                path = visited_backward_dict.get(addr, [addr])
                backward_queue.append((addr, path))
                # Remove from visited since we're going to explore it now
                backward_visited.discard(addr)
        else:
            # No queued addresses saved - check if addresses were actually explored or just discovered
            # If they're in visited_backward_dict but we have no queue, they might have been marked as discovered
            # without actually being explored. Re-queue them to ensure they get explored.
            print(f"[DEBUG] No queued addresses - checking if {len(visited_backward_dict)} discovered addresses need exploration")
            print(f"[DEBUG] Starting fresh from initial addresses to find new connections")
            # Start from initial addresses - they may have new neighbors we haven't seen
            for addr in list_b:
                # Remove from visited so we can explore it
                backward_visited.discard(addr)
                backward_queue.append((addr, [addr]))
                print(f"[DEBUG]   Queued initial backward address for exploration: {addr}")

        # Alternating BFS
        # Continue until max_depth is reached OR both queues are exhausted
        current_depth = 0
        while current_depth < max_depth:
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
                        'direction': 'forward',
                        # Include full state for checkpoint saving
                        'visited_forward': dict(forward_discovered),
                        'visited_backward': dict(backward_discovered),
                        'queued_forward': [item[0] for item in list(forward_queue)],
                        'queued_backward': [item[0] for item in list(backward_queue)],
                        'connections_found': list(results['connections_found']),
                        'search_depth': current_depth
                    })

                try:
                    txs = await self.get_address_txs(current, start_block, end_block)
                    
                    output_count = 0
                    skipped_outputs = 0
                    for tx in txs:
                        # FORWARD direction: Only follow OUTPUTS
                        # Who did this address send money TO?
                        outputs = self._extract_addresses(tx, 'output')
                        total_outputs = len(outputs)
                        output_count += total_outputs
                        
                        # Limit output addresses per transaction to prevent queue flooding
                        if total_outputs > MAX_OUTPUT_ADDRESSES_PER_TX:
                            outputs = list(outputs)[:MAX_OUTPUT_ADDRESSES_PER_TX]
                            skipped_outputs += (total_outputs - MAX_OUTPUT_ADDRESSES_PER_TX)
                            print(f"    [LIMIT] Transaction has {total_outputs} outputs, processing first {MAX_OUTPUT_ADDRESSES_PER_TX}")
                        
                        for neighbor in outputs:
                            if neighbor in forward_discovered:
                                continue
                            
                            # Skip exchange wallets
                            if await self._is_exchange_wallet(neighbor, start_block, end_block):
                                print(f"    [SKIP] Exchange wallet neighbor: {neighbor}")
                                continue

                            new_path = path + [neighbor]

                            # Check if meeting point
                            if neighbor in backward_discovered:
                                backward_path = backward_discovered[neighbor]
                                full_path = new_path + list(reversed(backward_path[1:]))
                                target_addr = full_path[-1]
                                
                                # CRITICAL: Validate that target_addr is actually in list_b
                                if target_addr not in list_b:
                                    print(f"\n[!] MEETING POINT FOUND but target not in list_b: {neighbor}")
                                    print(f"    Path: {' -> '.join(full_path)}")
                                    print(f"    Target {target_addr} is not in list_b - continuing search...")
                                    # Don't report this as a connection, continue searching
                                    forward_discovered[neighbor] = new_path
                                    forward_queue.append((neighbor, new_path))
                                    continue
                                
                                print(f"\n[✓] MEETING POINT FOUND: {neighbor}")
                                print(f" Path: {' -> '.join(full_path)}")
                                print(f" Source: {full_path[0]} -> Target: {target_addr} (verified in list_b)")
                                
                                # Create connection object
                                connection = {
                                    'source': full_path[0],
                                    'target': target_addr,
                                    'path': full_path,
                                    'path_length': len(full_path),
                                    'path_count': len(full_path),
                                    'meeting_points': full_path,
                                    'found_at_depth': current_depth,
                                    'direction': 'forward_meets_backward'
                                }
                                
                                # Check for duplicates before adding
                                connection_key = (connection['source'], connection['target'])
                                if connection_key not in existing_connection_keys:
                                    results['connections_found'].append(connection)
                                    existing_connection_keys.add(connection_key)
                                else:
                                    print(f"  [SKIP] Duplicate connection: {connection['source']} -> {connection['target']}")
                                
                                # Mark this target as matched
                                matched_targets.add(target_addr)
                                results['status'] = 'connected'
                                
                                # Update exports immediately if callback provided
                                if connection_callback:
                                    try:
                                        connection_callback(
                                            connection,
                                            len(forward_visited) + len(backward_visited),
                                            max_depth,
                                            (start_block, end_block),
                                            'connected'
                                        )
                                    except Exception as e:
                                        print(f"  [WARN] Error in connection callback: {e}")
                                
                                # Continue searching - don't return yet
                                print(f"  [CONTINUE] Found {len(results['connections_found'])} connection(s), continuing search...")
                                
                                # Check if all list_b addresses have been matched
                                if len(matched_targets) >= len(list_b):
                                    print(f"\n[✓] All {len(list_b)} target addresses matched!")
                                    results['total_addresses_examined'] = len(forward_visited) + len(backward_visited)
                                    results['visited_forward'] = forward_discovered
                                    results['visited_backward'] = backward_discovered
                                    results['queued_forward'] = [item[0] for item in list(forward_queue)]
                                    results['queued_backward'] = [item[0] for item in list(backward_queue)]
                                    return results
                                
                                # After finding a valid connection, still add neighbor to discovered
                                # (it's already in backward_discovered, but add to forward_discovered for consistency)
                                forward_discovered[neighbor] = new_path
                                # Don't add to queue - it's already been explored by backward search
                                continue

                            forward_discovered[neighbor] = new_path
                            forward_queue.append((neighbor, new_path))

                    if output_count == 0 and txs:
                        print(f"    [DEBUG] Found {len(txs)} transactions but 0 extractable output addresses for {current}")
                    elif output_count > 0:
                        if skipped_outputs > 0:
                            print(f"    [DEBUG] Found {output_count} output addresses from {len(txs)} transactions for {current} (skipped {skipped_outputs} due to limit)")
                        else:
                            print(f"    [DEBUG] Found {output_count} output addresses from {len(txs)} transactions for {current}")

                    addresses_explored += 1

                except ConnectionLostError:
                    # Re-raise connection loss errors - these should trigger checkpoint save
                    raise
                except Exception as e:
                    print(f"    Error: {e}")

            print(f"  Forward explored {addresses_explored}, queue: {len(forward_queue)}")

            # Backward step - ONLY FOLLOW INPUTS
            print(f"\n[<<] Backward BFS (queue: {len(backward_queue)}):")
            print(f"    [DIAG] backward_discovered has {len(backward_discovered)} addresses")
            print(f"    [DIAG] backward_visited has {len(backward_visited)} addresses")
            backward_queue_size = len(backward_queue)
            addresses_explored = 0
            
            # Diagnostic counters for entire backward step
            diag_total_txs_retrieved = 0
            diag_total_inputs_extracted = 0
            diag_inputs_already_discovered = 0
            diag_inputs_exchange_wallet = 0
            diag_inputs_added_to_queue = 0

            for _ in range(backward_queue_size):
                if not backward_queue:
                    break

                current, path = backward_queue.popleft()

                # Skip if already visited in THIS SEARCH SESSION
                if current in backward_visited:
                    print(f"    [DIAG] Skipping {current} - already in backward_visited")
                    continue

                backward_visited.add(current)
                print(f"  Exploring: {current}")

                if progress_callback:
                    progress_callback({
                        'visited': len(forward_visited) + len(backward_visited),
                        'current': current,
                        'direction': 'backward',
                        # Include full state for checkpoint saving
                        'visited_forward': dict(forward_discovered),
                        'visited_backward': dict(backward_discovered),
                        'queued_forward': [item[0] for item in list(forward_queue)],
                        'queued_backward': [item[0] for item in list(backward_queue)],
                        'connections_found': list(results['connections_found']),
                        'search_depth': current_depth
                    })

                try:
                    txs = await self.get_address_txs(current, start_block, end_block)
                    diag_total_txs_retrieved += len(txs) if txs else 0
                    
                    if not txs:
                        print(f"    [DIAG] No transactions found for {current}")
                    else:
                        print(f"    [DIAG] Retrieved {len(txs)} transactions for {current}")
                    
                    input_count = 0
                    skipped_inputs = 0
                    addr_inputs_discovered = 0
                    addr_inputs_exchange = 0
                    addr_inputs_added = 0
                    
                    for tx in txs:
                        # BACKWARD direction: Only follow INPUTS
                        # Who SENT money TO this address?
                        # Note: Transactions with 50+ inputs AND 50+ outputs (extreme mixers) are already filtered
                        # by _should_skip_transaction in get_address_txs()
                        inputs = self._extract_addresses(tx, 'input')
                        total_inputs = len(inputs)
                        input_count += total_inputs
                        diag_total_inputs_extracted += total_inputs
                        
                        # Limit input addresses per transaction to prevent queue flooding
                        # This handles transactions with many inputs that weren't filtered as extreme mixers
                        if total_inputs > MAX_INPUT_ADDRESSES_PER_TX:
                            inputs = list(inputs)[:MAX_INPUT_ADDRESSES_PER_TX]
                            skipped_inputs += (total_inputs - MAX_INPUT_ADDRESSES_PER_TX)
                            print(f"    [LIMIT] Transaction has {total_inputs} inputs, processing first {MAX_INPUT_ADDRESSES_PER_TX} (extreme mixers with 50+ inputs/outputs are already filtered)")
                        
                        for neighbor in inputs:
                            if neighbor in backward_discovered:
                                addr_inputs_discovered += 1
                                diag_inputs_already_discovered += 1
                                continue
                            
                            # Skip exchange wallets
                            if await self._is_exchange_wallet(neighbor, start_block, end_block):
                                print(f"    [SKIP] Exchange wallet neighbor: {neighbor}")
                                addr_inputs_exchange += 1
                                diag_inputs_exchange_wallet += 1
                                continue

                            new_path = path + [neighbor]

                            # Check if meeting point
                            if neighbor in forward_discovered:
                                forward_path = forward_discovered[neighbor]
                                full_path = forward_path + list(reversed(new_path[1:]))
                                target_addr = full_path[-1]
                                
                                # CRITICAL: Validate that target_addr is actually in list_b
                                if target_addr not in list_b:
                                    print(f"\n[!] MEETING POINT FOUND but target not in list_b: {neighbor}")
                                    print(f"    Path: {' -> '.join(full_path)}")
                                    print(f"    Target {target_addr} is not in list_b - continuing search...")
                                    # Don't report this as a connection, continue searching
                                    backward_discovered[neighbor] = new_path
                                    backward_queue.append((neighbor, new_path))
                                    continue
                                
                                print(f"\n[✓] MEETING POINT FOUND: {neighbor}")
                                print(f" Path: {' -> '.join(full_path)}")
                                print(f" Source: {full_path[0]} -> Target: {target_addr} (verified in list_b)")
                                
                                # Create connection object
                                connection = {
                                    'source': full_path[0],
                                    'target': target_addr,
                                    'path': full_path,
                                    'path_length': len(full_path),
                                    'path_count': len(full_path),
                                    'meeting_points': full_path,
                                    'found_at_depth': current_depth,
                                    'direction': 'backward_meets_forward'
                                }
                                
                                # Check for duplicates before adding
                                connection_key = (connection['source'], connection['target'])
                                if connection_key not in existing_connection_keys:
                                    results['connections_found'].append(connection)
                                    existing_connection_keys.add(connection_key)
                                else:
                                    print(f"  [SKIP] Duplicate connection: {connection['source']} -> {connection['target']}")
                                
                                # Mark this target as matched
                                matched_targets.add(target_addr)
                                results['status'] = 'connected'
                                
                                # Update exports immediately if callback provided
                                if connection_callback:
                                    try:
                                        connection_callback(
                                            connection,
                                            len(forward_visited) + len(backward_visited),
                                            max_depth,
                                            (start_block, end_block),
                                            'connected'
                                        )
                                    except Exception as e:
                                        print(f"  [WARN] Error in connection callback: {e}")
                                
                                # Continue searching - don't return yet
                                print(f"  [CONTINUE] Found {len(results['connections_found'])} connection(s), continuing search...")
                                
                                # Check if all list_b addresses have been matched
                                if len(matched_targets) >= len(list_b):
                                    print(f"\n[✓] All {len(list_b)} target addresses matched!")
                                    results['total_addresses_examined'] = len(forward_visited) + len(backward_visited)
                                    results['visited_forward'] = forward_discovered
                                    results['visited_backward'] = backward_discovered
                                    results['queued_forward'] = [item[0] for item in list(forward_queue)]
                                    results['queued_backward'] = [item[0] for item in list(backward_queue)]
                                    return results
                                
                                # After finding a valid connection, still add neighbor to discovered
                                # (it's already in forward_discovered, but add to backward_discovered for consistency)
                                backward_discovered[neighbor] = new_path
                                # Don't add to queue - it's already been explored by forward search
                                continue

                            backward_discovered[neighbor] = new_path
                            backward_queue.append((neighbor, new_path))
                            addr_inputs_added += 1
                            diag_inputs_added_to_queue += 1
                    
                    # Per-address diagnostic summary
                    print(f"    [DIAG] Address {current} summary:")
                    print(f"           Txs: {len(txs) if txs else 0}, Inputs extracted: {input_count}")
                    print(f"           Skipped (already discovered): {addr_inputs_discovered}")
                    print(f"           Skipped (exchange wallet): {addr_inputs_exchange}")
                    print(f"           Skipped (limit): {skipped_inputs}")
                    print(f"           Added to queue: {addr_inputs_added}")
                    
                    if input_count == 0 and txs:
                        print(f"    [DEBUG] Found {len(txs)} transactions but 0 extractable input addresses for {current}")
                    elif input_count > 0:
                        if skipped_inputs > 0:
                            print(f"    [DEBUG] Found {input_count} input addresses from {len(txs)} transactions for {current} (skipped {skipped_inputs} due to limit)")
                        else:
                            print(f"    [DEBUG] Found {input_count} input addresses from {len(txs)} transactions for {current}")

                    addresses_explored += 1

                except ConnectionLostError:
                    # Re-raise connection loss errors - these should trigger checkpoint save
                    raise
                except Exception as e:
                    print(f"    Error: {e}")

            print(f"  Backward explored {addresses_explored}, queue: {len(backward_queue)}")
            
            # Overall backward step diagnostic summary
            print(f"\n    [DIAG] ===== BACKWARD STEP SUMMARY (Depth {current_depth}) =====")
            print(f"    [DIAG] Total transactions retrieved: {diag_total_txs_retrieved}")
            print(f"    [DIAG] Total inputs extracted: {diag_total_inputs_extracted}")
            print(f"    [DIAG] Inputs skipped (already discovered): {diag_inputs_already_discovered}")
            print(f"    [DIAG] Inputs skipped (exchange wallet): {diag_inputs_exchange_wallet}")
            print(f"    [DIAG] Inputs added to queue: {diag_inputs_added_to_queue}")
            if diag_total_inputs_extracted > 0:
                skip_rate = ((diag_inputs_already_discovered + diag_inputs_exchange_wallet) / diag_total_inputs_extracted) * 100
                print(f"    [DIAG] Skip rate: {skip_rate:.1f}%")
            elif diag_total_txs_retrieved > 0:
                print(f"    [DIAG] WARNING: {diag_total_txs_retrieved} transactions but 0 inputs extracted!")
            else:
                print(f"    [DIAG] WARNING: No transactions retrieved for any backward address!")
            print(f"    [DIAG] ================================================")

            print(f"\n[STATUS] Depth {current_depth}:")
            print(f" Forward: visited={len(forward_visited)}, discovered={len(forward_discovered)}, queue={len(forward_queue)}")
            print(f" Backward: visited={len(backward_visited)}, discovered={len(backward_discovered)}, queue={len(backward_queue)}")
            print(f" Connections found: {len(results['connections_found'])}")
            print(f" Matched targets: {len(matched_targets)}/{len(list_b)}")

            # Increment depth for next iteration
            current_depth += 1
            
            # Check if we should continue
            if not forward_queue and not backward_queue:
                print(f"\n[!] Both queues exhausted at depth {current_depth-1}")
                break

        # Finalize results
        if len(results['connections_found']) > 0:
            results['status'] = 'connected'
            print(f"\n[✓] Search completed. Found {len(results['connections_found'])} connection(s)")
            print(f" Matched {len(matched_targets)} out of {len(list_b)} target addresses")
        else:
            results['status'] = 'no_connection'
            print(f"\n[✗] No connections found")
        
        results['total_addresses_examined'] = len(forward_visited) + len(backward_visited)
        results['visited_forward'] = forward_discovered
        results['visited_backward'] = backward_discovered
        results['queued_forward'] = [item[0] for item in list(forward_queue)]
        results['queued_backward'] = [item[0] for item in list(backward_queue)]
        
        print(f" Total addresses examined: {results['total_addresses_examined']}")
        
        return results