import unittest
import sqlite3
import sys
import os
import pandas as pd

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from transform import get_split_adjusted_trades

class TestStockSplitAdjustment(unittest.TestCase):
    def setUp(self):
        self.conn = sqlite3.connect(":memory:")
        self.cursor = self.conn.cursor()
        
        self.cursor.execute("""
        CREATE TABLE transactions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            trade_date TEXT NOT NULL,
            ticker TEXT NOT NULL,
            action TEXT NOT NULL,
            shares REAL NOT NULL,
            price_per_share REAL NOT NULL,
            fee REAL DEFAULT 0,
            reason_category TEXT,
            notes TEXT
        )
        """)
        
        self.cursor.execute("""
        CREATE TABLE stock_splits (
            ticker TEXT NOT NULL,
            split_date TEXT NOT NULL,
            split_ratio REAL NOT NULL,
            PRIMARY KEY (ticker, split_date)
        )
        """)
        self.conn.commit()

    def tearDown(self):
        self.conn.close()

    def test_pre_split_trade_is_adjusted_10x(self):
        """A trade of 1 share at $600 before a 10:1 split must become 10 shares at $60."""
        # 1. Insert NVDA 10:1 split on 2024-06-10
        self.cursor.execute("""
        INSERT INTO stock_splits (ticker, split_date, split_ratio)
        VALUES ('NVDA', '2024-06-10', 10.0)
        """)
        
        # 2. Insert trade before split (2024-02-15)
        self.cursor.execute("""
        INSERT INTO transactions (trade_date, ticker, action, shares, price_per_share, fee)
        VALUES ('2024-02-15', 'NVDA', 'BUY', 1.0, 600.0, 0.0)
        """)
        self.conn.commit()

        adjusted_df = get_split_adjusted_trades(self.conn)
        row = adjusted_df.iloc[0]
        self.assertAlmostEqual(row['shares'], 10.0, places=4)
        self.assertAlmostEqual(row['price_per_share'], 60.0, places=4)

    def test_post_split_trade_remains_unchanged(self):
        """A trade bought after the split date should retain original shares and price."""
        self.cursor.execute("""
        INSERT INTO stock_splits (ticker, split_date, split_ratio)
        VALUES ('NVDA', '2024-06-10', 10.0)
        """)
        
        # Insert trade after split (2024-06-20)
        self.cursor.execute("""
        INSERT INTO transactions (trade_date, ticker, action, shares, price_per_share, fee)
        VALUES ('2024-06-20', 'NVDA', 'BUY', 5.0, 120.0, 0.0)
        """)
        self.conn.commit()

        adjusted_df = get_split_adjusted_trades(self.conn)
        row = adjusted_df.iloc[0]
        self.assertAlmostEqual(row['shares'], 5.0, places=4)
        self.assertAlmostEqual(row['price_per_share'], 120.0, places=4)

if __name__ == '__main__':
    unittest.main()
