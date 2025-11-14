# IMPROVED cache_manager.py with better pruning

import sqlite3
import json
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional, Dict, List, Any
from config import CACHE_MAX_SIZE_MB, CHECKPOINT_DIR


class TransactionCache:
    """SQLite-based transaction cache with size limits and pruning metrics"""

    def __init__(self, db_path: str = "blockchain_cache.db", max_size_mb: int = CACHE_MAX_SIZE_MB):
        self.db_path = db_path
        self.max_size_mb = max_size_mb
        self.conn = None
        
        # Pruning metrics
        self.cache_hits = 0
        self.cache_misses = 0
        self.pruning_count = 0
        self.entries_deleted_total = 0
        
        self.init_db()

    def init_db(self):
        """Initialize SQLite database"""
        self.conn = sqlite3.connect(self.db_path)
        c = self.conn.cursor()

        c.execute('''
        CREATE TABLE IF NOT EXISTS cached_transactions (
            address TEXT NOT NULL,
            transactions JSON NOT NULL,
            last_updated TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            access_count INTEGER DEFAULT 0,
            block_range TEXT,
            size_bytes INTEGER,
            PRIMARY KEY (address, block_range)
        )
        ''')

        c.execute('CREATE INDEX IF NOT EXISTS idx_address ON cached_transactions(address)')
        c.execute('CREATE INDEX IF NOT EXISTS idx_updated ON cached_transactions(last_updated)')
        c.execute('CREATE INDEX IF NOT EXISTS idx_access ON cached_transactions(access_count)')
        
        self.conn.commit()
        print(f"âœ… Cache initialized at {self.db_path}")

    def get_cached(self, address: str, block_range: Optional[tuple] = None) -> Optional[List[Dict]]:
        """Retrieve cached transactions"""
        c = self.conn.cursor()
        range_str = f"{block_range[0]}-{block_range[1]}" if block_range else "all"

        c.execute('''
        SELECT transactions, last_updated, access_count
        FROM cached_transactions
        WHERE address = ? AND block_range = ?
        ''', (address, range_str))

        result = c.fetchone()

        if result:
            txs_json, updated, access_count = result
            
            # Invalidate if older than 24 hours
            updated_dt = datetime.fromisoformat(updated)
            if updated_dt > datetime.now() - timedelta(hours=24):
                # Update access count and timestamp on hit
                c.execute('''
                UPDATE cached_transactions 
                SET access_count = access_count + 1, last_updated = CURRENT_TIMESTAMP
                WHERE address = ? AND block_range = ?
                ''', (address, range_str))
                self.conn.commit()
                
                self.cache_hits += 1
                return json.loads(txs_json)
            else:
                self.delete_cached(address, block_range)
                self.cache_misses += 1
                return None
        
        self.cache_misses += 1
        return None

    def cache(self, address: str, transactions: List[Dict], block_range: Optional[tuple] = None):
        """Store transactions in cache"""
        c = self.conn.cursor()
        range_str = f"{block_range[0]}-{block_range[1]}" if block_range else "all"
        tx_json = json.dumps(transactions)
        size_bytes = len(tx_json.encode('utf-8'))

        c.execute('''
        INSERT OR REPLACE INTO cached_transactions
        (address, transactions, block_range, size_bytes, access_count)
        VALUES (?, ?, ?, ?, 1)
        ''', (address, tx_json, range_str, size_bytes))

        self.conn.commit()
        self._enforce_cache_size()

    def _enforce_cache_size(self):
        """Remove oldest entries if cache exceeds max size - IMPROVED"""
        c = self.conn.cursor()
        c.execute("SELECT page_count * page_size / 1024 / 1024 FROM pragma_page_count(), pragma_page_size()")
        size_mb = c.fetchone()[0]

        if size_mb > self.max_size_mb:
            print(f"\nâš ï¸  Cache size {size_mb:.2f}MB exceeds limit {self.max_size_mb}MB, pruning...")
            
            # Get total entry count BEFORE pruning
            c.execute("SELECT COUNT(*) FROM cached_transactions")
            entries_before = c.fetchone()[0]
            
            # IMPROVED: Use a smarter deletion strategy
            # Delete bottom 50% of entries by (access_count * recency score)
            # This preserves frequently-accessed and recent entries
            
            c.execute('''
            DELETE FROM cached_transactions
            WHERE address IN (
                SELECT address FROM cached_transactions
                ORDER BY (
                    -- Score: (access_count * 0.7) + (recency_score * 0.3)
                    (access_count * 0.7) +
                    (CAST((datetime('now') - last_updated) AS REAL) / 86400.0 * 0.3)
                ) ASC
                LIMIT (SELECT CAST(COUNT(*) * 0.50 AS INTEGER) FROM cached_transactions)
            )
            ''')
            
            self.conn.commit()
            
            # Get new size and count
            c.execute("SELECT page_count * page_size / 1024 / 1024 FROM pragma_page_count(), pragma_page_size()")
            new_size_mb = c.fetchone()[0]
            
            c.execute("SELECT COUNT(*) FROM cached_transactions")
            entries_after = c.fetchone()[0]
            entries_deleted = entries_before - entries_after
            
            self.pruning_count += 1
            self.entries_deleted_total += entries_deleted
            
            print(f"âœ… Cache pruned:")
            print(f"   Size: {size_mb:.2f}MB â†’ {new_size_mb:.2f}MB (target: {self.max_size_mb}MB)")
            print(f"   Entries: {entries_before} â†’ {entries_after} (deleted: {entries_deleted})")
            print(f"   Cache efficiency: {self._get_hit_rate():.1f}% hit rate")

    def _get_hit_rate(self) -> float:
        """Calculate cache hit rate"""
        total = self.cache_hits + self.cache_misses
        if total == 0:
            return 0.0
        return (self.cache_hits / total) * 100

    def get_cache_stats(self) -> Dict[str, Any]:
        """Get cache performance statistics"""
        c = self.conn.cursor()
        
        c.execute("SELECT page_count * page_size / 1024 / 1024 FROM pragma_page_count(), pragma_page_size()")
        size_mb = c.fetchone()[0]
        
        c.execute("SELECT COUNT(*) FROM cached_transactions")
        entry_count = c.fetchone()[0]
        
        c.execute("SELECT SUM(size_bytes) / 1024 / 1024 FROM cached_transactions")
        data_size_mb = c.fetchone()[0] or 0
        
        c.execute("SELECT AVG(access_count) FROM cached_transactions")
        avg_access = c.fetchone()[0] or 0
        
        c.execute("SELECT MAX(access_count) FROM cached_transactions")
        max_access = c.fetchone()[0] or 0
        
        return {
            'cache_size_mb': size_mb,
            'data_size_mb': data_size_mb,
            'entries': entry_count,
            'avg_access_count': avg_access,
            'max_access_count': max_access,
            'cache_hits': self.cache_hits,
            'cache_misses': self.cache_misses,
            'hit_rate_percent': self._get_hit_rate(),
            'pruning_count': self.pruning_count,
            'total_entries_deleted': self.entries_deleted_total,
            'max_size_limit_mb': self.max_size_mb
        }

    def delete_cached(self, address: str, block_range: Optional[tuple] = None):
        """Remove specific cache entry"""
        c = self.conn.cursor()
        range_str = f"{block_range[0]}-{block_range[1]}" if block_range else "all"
        c.execute('DELETE FROM cached_transactions WHERE address = ? AND block_range = ?',
                  (address, range_str))
        self.conn.commit()

    def clear_old_entries(self, hours: int = 24):
        """Manually clear entries older than N hours"""
        c = self.conn.cursor()
        cutoff_time = (datetime.now() - timedelta(hours=hours)).isoformat()
        
        c.execute("SELECT COUNT(*) FROM cached_transactions WHERE last_updated < ?", (cutoff_time,))
        count = c.fetchone()[0]
        
        c.execute("DELETE FROM cached_transactions WHERE last_updated < ?", (cutoff_time,))
        self.conn.commit()
        
        print(f"ðŸ§¹ Cleared {count} entries older than {hours} hours")

    def close(self):
        if self.conn:
            self.conn.close()