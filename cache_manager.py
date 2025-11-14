# FIXED cache_manager.py - rename method to avoid naming collision

# -*- coding: utf-8 -*-
import time
from typing import Dict, Any, Optional, Tuple, List
import sys

class TransactionCache:
    """
    Improved cache manager with aggressive memory management
    Strategies: LRU (Least Recently Used), Keep only recent addresses
    """

    def __init__(self, max_size_mb: int = 2048):
        self.data: Dict[str, List[Dict]] = {}  # RENAMED from 'cache' to 'data'
        self.max_size_mb = max_size_mb
        self.access_times: Dict[str, float] = {}
        self.entry_sizes: Dict[str, int] = {}

    def _estimate_size(self, data: Any) -> int:
        """Estimate size in bytes using sys.getsizeof"""
        try:
            return sys.getsizeof(data)
        except:
            return 1000000  # Assume 1MB if error

    def _get_current_size_mb(self) -> float:
        """Get total cache size in MB"""
        total = sum(self.entry_sizes.values())
        return total / (1024 * 1024)

    def _aggressive_prune(self) -> Tuple[float, int]:
        """
        Aggressively prune cache - remove oldest entries until well below limit.
        Returns: (new_size_mb, entries_deleted)
        """
        initial_size = self._get_current_size_mb()
        initial_count = len(self.data)
        deleted = 0

        # Target: 30% below limit (buffer for new data)
        target_size_mb = self.max_size_mb * 0.7
        
        # Sort by access time (oldest first)
        sorted_entries = sorted(
            self.access_times.items(),
            key=lambda x: x[1]  # Sort by timestamp
        )

        # Delete oldest entries until below target
        for address, _ in sorted_entries:
            if self._get_current_size_mb() <= target_size_mb:
                break
            
            if address in self.data:
                size = self.entry_sizes.get(address, 0)
                del self.data[address]
                del self.access_times[address]
                del self.entry_sizes[address]
                deleted += 1

        final_size = self._get_current_size_mb()
        print(f"âš ï¸  Cache size {initial_size:.2f}MB exceeds limit {self.max_size_mb}MB, aggressive pruning...")
        print(f"âœ… Cache pruned:")
        print(f"   Size: {initial_size:.2f}MB â†’ {final_size:.2f}MB (target: {target_size_mb:.2f}MB)")
        print(f"   Entries: {initial_count} â†’ {len(self.data)} (deleted: {deleted})")
        print(f"   Cache efficiency: {self._get_hit_rate():.1f}% hit rate\n")

        return final_size, deleted

    def _get_hit_rate(self) -> float:
        """Calculate cache hit rate (percentage)"""
        total = getattr(self, 'total_requests', 1)
        hits = getattr(self, 'cache_hits', 0)
        return (hits / total * 100) if total > 0 else 0

    def get_cached(self, address: str, block_range: Optional[Tuple] = None) -> Optional[List]:
        """Get from cache if exists"""
        key = f"{address}_{block_range}"
        
        if key in self.data:
            self.access_times[key] = time.time()
            self.cache_hits = getattr(self, 'cache_hits', 0) + 1
            return self.data[key]
        
        self.total_requests = getattr(self, 'total_requests', 0) + 1
        return None

    def store(self, address: str, txs: List[Dict], block_range: Optional[Tuple] = None):
        """Store in cache with size check - RENAMED from cache() to store()"""
        key = f"{address}_{block_range}"
        size = self._estimate_size(txs)

        # Store entry
        self.data[key] = txs
        self.entry_sizes[key] = size
        self.access_times[key] = time.time()

        # Check if over limit - if so, prune aggressively
        current_size = self._get_current_size_mb()
        if current_size > self.max_size_mb:
            self._aggressive_prune()

    def close(self):
        """Close and clear cache"""
        self.data.clear()
        self.entry_sizes.clear()
        self.access_times.clear()

    def get_cache_stats(self) -> Dict[str, Any]:
        """Return cache statistics"""
        return {
            'size_mb': self._get_current_size_mb(),
            'max_size_mb': self.max_size_mb,
            'entries': len(self.data),
            'hit_rate': self._get_hit_rate()
        }