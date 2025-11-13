import sqlite3
import json
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional, Dict, List, Any
from config import CACHE_MAX_SIZE_MB, CHECKPOINT_DIR

class TransactionCache:
    """SQLite-based transaction cache with size limits"""
    
    def __init__(self, db_path: str = "blockchain_cache.db", max_size_mb: int = CACHE_MAX_SIZE_MB):
        self.db_path = db_path
        self.max_size_mb = max_size_mb
        self.conn = None
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
                block_range TEXT,
                size_bytes INTEGER,
                PRIMARY KEY (address, block_range)
            )
        ''')
        c.execute('CREATE INDEX IF NOT EXISTS idx_address ON cached_transactions(address)')
        c.execute('CREATE INDEX IF NOT EXISTS idx_updated ON cached_transactions(last_updated)')
        self.conn.commit()
        print(f"âœ… Cache initialized at {self.db_path}")
    
    def get_cached(self, address: str, block_range: Optional[tuple] = None) -> Optional[List[Dict]]:
        """Retrieve cached transactions"""
        c = self.conn.cursor()
        range_str = f"{block_range[0]}-{block_range[1]}" if block_range else "all"
        c.execute('''
            SELECT transactions, last_updated
            FROM cached_transactions
            WHERE address = ? AND block_range = ?
        ''', (address, range_str))
        result = c.fetchone()
        
        if result:
            txs_json, updated = result
            # Invalidate if older than 24 hours
            updated_dt = datetime.fromisoformat(updated)
            if updated_dt > datetime.now() - timedelta(hours=24):
                return json.loads(txs_json)
            else:
                self.delete_cached(address, block_range)
                return None
    
    def cache(self, address: str, transactions: List[Dict], block_range: Optional[tuple] = None):
        """Store transactions in cache"""
        c = self.conn.cursor()
        range_str = f"{block_range[0]}-{block_range[1]}" if block_range else "all"
        tx_json = json.dumps(transactions)
        size_bytes = len(tx_json.encode('utf-8'))
        
        c.execute('''
            INSERT OR REPLACE INTO cached_transactions
            (address, transactions, block_range, size_bytes)
            VALUES (?, ?, ?, ?)
        ''', (address, tx_json, range_str, size_bytes))
        
        self.conn.commit()
        self._enforce_cache_size()
    
    def _enforce_cache_size(self):
        """Remove oldest entries if cache exceeds max size"""
        c = self.conn.cursor()
        c.execute("SELECT page_count * page_size / 1024 / 1024 FROM pragma_page_count(), pragma_page_size()")
        size_mb = c.fetchone()[0]
        
        if size_mb > self.max_size_mb:
            print(f"âš ï¸  Cache size {size_mb}MB exceeds limit {self.max_size_mb}MB, pruning...")
            
            # Delete oldest 35% (midpoint between 25-50% range)
            # This is more aggressive than before, preventing frequent pruning
            c.execute('''
                DELETE FROM cached_transactions
                WHERE address IN (
                    SELECT address FROM cached_transactions
                    ORDER BY last_updated ASC
                    LIMIT (SELECT CAST(COUNT(*) * 0.35 AS INTEGER) FROM cached_transactions)
                )
            ''')
            
            self.conn.commit()
            c.execute("SELECT page_count * page_size / 1024 / 1024 FROM pragma_page_count(), pragma_page_size()")
            new_size_mb = c.fetchone()[0]
            print(f"âœ… Cache pruned: {size_mb}MB â†’ {new_size_mb}MB")
    
    def delete_cached(self, address: str, block_range: Optional[tuple] = None):
        """Remove specific cache entry"""
        c = self.conn.cursor()
        range_str = f"{block_range[0]}-{block_range[1]}" if block_range else "all"
        c.execute('DELETE FROM cached_transactions WHERE address = ? AND block_range = ?',
                  (address, range_str))
        self.conn.commit()
    
    def close(self):
        if self.conn:
            self.conn.close()