# FIXED cache_manager.py - rename method to avoid naming collision

# -*- coding: utf-8 -*-
import time
import sqlite3
import pickle
from typing import Dict, Any, Optional, Tuple, List

class TransactionCache:
    """
    Improved cache manager with SQLite persistence and aggressive memory management
    Strategies: LRU (Least Recently Used), Keep only recent addresses
    """

    def __init__(self, db_path: str = "blockchain_cache.db", max_size_mb: int = 2048):
        self.db_path = db_path
        self.max_size_mb = max_size_mb
        self.cache_hits = 0
        self.total_requests = 0
        
        # Initialize database
        self._init_database()
        
        # Load stats from database
        self._load_stats()
        
        print(f"[CACHE] Initialized with SQLite database: {db_path}")
        print(f"[CACHE] Max size: {max_size_mb}MB, Current entries: {self._get_entry_count()}")
    
    def _init_database(self):
        """Initialize SQLite database with cache table"""
        conn = sqlite3.connect(self.db_path)
        c = conn.cursor()
        
        # Create table for cached transactions
        c.execute('''
            CREATE TABLE IF NOT EXISTS cached_transactions (
                cache_key TEXT PRIMARY KEY,
                address TEXT NOT NULL,
                block_range TEXT,
                transactions BLOB NOT NULL,
                size_bytes INTEGER NOT NULL,
                access_time REAL NOT NULL,
                created_at REAL NOT NULL
            )
        ''')
        
        # Create indexes for faster queries
        c.execute('CREATE INDEX IF NOT EXISTS idx_address ON cached_transactions(address)')
        c.execute('CREATE INDEX IF NOT EXISTS idx_access_time ON cached_transactions(access_time)')
        c.execute('CREATE INDEX IF NOT EXISTS idx_created_at ON cached_transactions(created_at)')
        
        conn.commit()
        conn.close()
        print(f"[CACHE] Database initialized at {self.db_path}")
    
    def _load_stats(self):
        """Load cache statistics from database"""
        conn = sqlite3.connect(self.db_path)
        c = conn.cursor()
        
        # Try to load stats from metadata table (if exists)
        try:
            c.execute('SELECT hits, requests FROM cache_stats LIMIT 1')
            row = c.fetchone()
            if row:
                self.cache_hits = row[0] or 0
                self.total_requests = row[1] or 0
        except sqlite3.OperationalError:
            # Stats table doesn't exist yet, start fresh
            pass
        
        conn.close()
    
    def _save_stats(self):
        """Save cache statistics to database"""
        conn = sqlite3.connect(self.db_path)
        c = conn.cursor()
        
        # Create stats table if it doesn't exist
        c.execute('''
            CREATE TABLE IF NOT EXISTS cache_stats (
                id INTEGER PRIMARY KEY,
                hits INTEGER DEFAULT 0,
                requests INTEGER DEFAULT 0
            )
        ''')
        
        # Update or insert stats
        c.execute('SELECT COUNT(*) FROM cache_stats')
        if c.fetchone()[0] == 0:
            c.execute('INSERT INTO cache_stats (hits, requests) VALUES (?, ?)', 
                     (self.cache_hits, self.total_requests))
        else:
            c.execute('UPDATE cache_stats SET hits = ?, requests = ? WHERE id = 1',
                     (self.cache_hits, self.total_requests))
        
        conn.commit()
        conn.close()
    
    def _get_entry_count(self) -> int:
        """Get current number of cache entries"""
        conn = sqlite3.connect(self.db_path)
        c = conn.cursor()
        c.execute('SELECT COUNT(*) FROM cached_transactions')
        count = c.fetchone()[0]
        conn.close()
        return count

    def _estimate_size(self, data: Any) -> int:
        """Estimate size in bytes by pickling the data"""
        try:
            pickled = pickle.dumps(data)
            return len(pickled)
        except:
            return 1000000  # Assume 1MB if error

    def _get_current_size_mb(self) -> float:
        """Get total cache size in MB from database"""
        conn = sqlite3.connect(self.db_path)
        c = conn.cursor()
        c.execute('SELECT SUM(size_bytes) FROM cached_transactions')
        result = c.fetchone()[0]
        conn.close()
        total_bytes = result if result else 0
        return total_bytes / (1024 * 1024)

    def _aggressive_prune(self) -> Tuple[float, int]:
        """
        Aggressively prune cache - remove oldest entries until well below limit.
        Returns: (new_size_mb, entries_deleted)
        """
        initial_size = self._get_current_size_mb()
        initial_count = self._get_entry_count()
        deleted = 0

        # Target: 30% below limit (buffer for new data)
        target_size_mb = self.max_size_mb * 0.7
        
        conn = sqlite3.connect(self.db_path)
        c = conn.cursor()
        
        # Delete oldest entries (by access_time) until below target
        while self._get_current_size_mb() > target_size_mb:
            # Get oldest entry
            c.execute('''
                SELECT cache_key, size_bytes FROM cached_transactions 
                ORDER BY access_time ASC 
                LIMIT 1
            ''')
            row = c.fetchone()
            
            if not row:
                break
            
            cache_key, size_bytes = row
            
            # Delete it
            c.execute('DELETE FROM cached_transactions WHERE cache_key = ?', (cache_key,))
            deleted += 1
            
            # Check size again
            conn.commit()
        
        conn.close()
        
        final_size = self._get_current_size_mb()
        final_count = self._get_entry_count()
        print(f"⚠️  Cache size {initial_size:.2f}MB exceeds limit {self.max_size_mb}MB, aggressive pruning...")
        print(f"✅ Cache pruned:")
        print(f"   Size: {initial_size:.2f}MB → {final_size:.2f}MB (target: {target_size_mb:.2f}MB)")
        print(f"   Entries: {initial_count} → {final_count} (deleted: {deleted})")
        print(f"   Cache efficiency: {self._get_hit_rate():.1f}% hit rate\n")

        return final_size, deleted

    def _get_hit_rate(self) -> float:
        """Calculate cache hit rate (percentage)"""
        total = self.total_requests if self.total_requests > 0 else 1
        hits = self.cache_hits
        return (hits / total * 100) if total > 0 else 0

    def _make_key(self, address: str, block_range: Optional[Tuple] = None) -> str:
        """Create consistent cache key"""
        if block_range:
            return f"{address}_{block_range[0]}_{block_range[1]}"
        return f"{address}_None"
    
    def get_cached(self, address: str, block_range: Optional[Tuple] = None) -> Optional[List]:
        """Get from cache if exists"""
        key = self._make_key(address, block_range)
        self.total_requests += 1
        
        conn = sqlite3.connect(self.db_path)
        c = conn.cursor()
        
        # Try to get from database
        c.execute('''
            SELECT transactions FROM cached_transactions 
            WHERE cache_key = ?
        ''', (key,))
        
        row = c.fetchone()
        
        if row:
            # Update access time
            current_time = time.time()
            c.execute('''
                UPDATE cached_transactions 
                SET access_time = ? 
                WHERE cache_key = ?
            ''', (current_time, key))
            conn.commit()
            
            # Deserialize and return
            transactions = pickle.loads(row[0])
            self.cache_hits += 1
            self._save_stats()
            
            conn.close()
            # Only print hit every 10th time to reduce noise
            if self.cache_hits % 10 == 0:
                print(f"[CACHE HIT #{self.cache_hits}] {address} - {len(transactions)} transactions")
            return transactions
        
        conn.close()
        
        # Cache miss - only print occasionally to reduce noise
        if self.total_requests % 20 == 0:
            print(f"[CACHE MISS #{self.total_requests}] {address}")
            # Show sample of existing keys
            conn = sqlite3.connect(self.db_path)
            c = conn.cursor()
            c.execute('SELECT cache_key FROM cached_transactions LIMIT 5')
            existing_keys = [row[0] for row in c.fetchall()]
            conn.close()
            
            if existing_keys:
                print(f"[CACHE DEBUG] Existing keys sample: {existing_keys}")
            else:
                print(f"[CACHE DEBUG] Cache is empty - no entries stored yet")
        
        self._save_stats()
        return None

    def store(self, address: str, txs: List[Dict], block_range: Optional[Tuple] = None):
        """Store in cache with size check - RENAMED from cache() to store()"""
        if not txs:
            print(f"[CACHE STORE] Skipping empty transaction list for {address}")
            return
            
        key = self._make_key(address, block_range)
        size = self._estimate_size(txs)
        
        # Serialize transactions
        pickled_txs = pickle.dumps(txs)
        
        # Prepare block_range string for storage
        block_range_str = None
        if block_range:
            block_range_str = f"{block_range[0]}_{block_range[1]}"
        
        current_time = time.time()
        
        conn = sqlite3.connect(self.db_path)
        c = conn.cursor()
        
        # Insert or replace (upsert)
        c.execute('''
            INSERT OR REPLACE INTO cached_transactions 
            (cache_key, address, block_range, transactions, size_bytes, access_time, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        ''', (key, address, block_range_str, pickled_txs, size, current_time, current_time))
        
        conn.commit()
        conn.close()
        
        current_size = self._get_current_size_mb()
        entry_count = self._get_entry_count()
        
        # Only print store message every 10th entry to reduce noise
        if entry_count % 10 == 0 or entry_count <= 5:
            print(f"[CACHE STORE #{entry_count}] {address} - {len(txs)} txs, size: {size/(1024*1024):.2f}MB, total: {current_size:.2f}MB/{self.max_size_mb}MB")
        
        # Verify it was stored (silently, only log errors)
        conn = sqlite3.connect(self.db_path)
        c = conn.cursor()
        c.execute('SELECT COUNT(*) FROM cached_transactions WHERE cache_key = ?', (key,))
        exists = c.fetchone()[0] > 0
        conn.close()
        
        if not exists:
            print(f"[CACHE ERROR] Key '{key}' was not stored! This should not happen.")

        # Check if over limit - if so, prune aggressively
        if current_size > self.max_size_mb:
            self._aggressive_prune()

    def close(self):
        """Close cache and save stats"""
        self._save_stats()
        print(f"[CACHE] Closed. Final stats: {self.cache_hits}/{self.total_requests} hits ({self._get_hit_rate():.1f}% hit rate)")

    def get_cache_stats(self) -> Dict[str, Any]:
        """Return cache statistics"""
        return {
            'size_mb': self._get_current_size_mb(),
            'max_size_mb': self.max_size_mb,
            'entries': self._get_entry_count(),
            'hit_rate': self._get_hit_rate(),
            'hits': self.cache_hits,
            'total_requests': self.total_requests,
            'db_path': self.db_path
        }