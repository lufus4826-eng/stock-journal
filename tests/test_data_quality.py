import unittest
import sqlite3
import sys
import os

# Add root directory to path for imports
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from data_quality import (
    DataQualityError,
    check_transactions_quality,
    check_prices_quality,
    check_fx_quality
)

class TestDataQualityGates(unittest.TestCase):
    def setUp(self):
        self.conn = sqlite3.connect(":memory:")
        self.cursor = self.conn.cursor()
        
        # Create minimal test schemas with nullable columns to test QC checks
        self.cursor.execute("""
        CREATE TABLE transactions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            trade_date TEXT,
            ticker TEXT,
            action TEXT,
            shares REAL,
            price_per_share REAL,
            fee REAL DEFAULT 0,
            reason_category TEXT,
            notes TEXT
        )
        """)
        
        self.cursor.execute("""
        CREATE TABLE prices (
            trade_date TEXT NOT NULL,
            ticker TEXT NOT NULL,
            close REAL NOT NULL,
            adj_close REAL NOT NULL,
            PRIMARY KEY (trade_date, ticker)
        )
        """)
        
        self.cursor.execute("""
        CREATE TABLE fx_rates (
            trade_date TEXT PRIMARY KEY,
            rate REAL NOT NULL
        )
        """)
        self.conn.commit()

    def tearDown(self):
        self.conn.close()

    def test_transactions_valid_data_passes(self):
        """QC 1: Valid transactions must pass with no error."""
        self.cursor.execute("""
        INSERT INTO transactions (trade_date, ticker, action, shares, price_per_share, fee)
        VALUES ('2024-01-15', 'VOO', 'BUY', 0.5, 430.0, 0.0)
        """)
        self.conn.commit()
        # Should not raise any exception
        check_transactions_quality(self.conn)

    def test_transactions_rejects_nulls(self):
        """QC 1: Transactions with NULL in essential columns must raise DataQualityError."""
        self.cursor.execute("""
        INSERT INTO transactions (trade_date, ticker, action, shares, price_per_share)
        VALUES (NULL, 'AAPL', 'BUY', 1.0, 150.0)
        """)
        self.conn.commit()
        with self.assertRaises(DataQualityError):
            check_transactions_quality(self.conn)

    def test_transactions_rejects_zero_or_negative_shares(self):
        """QC 1: Transactions with shares <= 0 must raise DataQualityError."""
        self.cursor.execute("""
        INSERT INTO transactions (trade_date, ticker, action, shares, price_per_share)
        VALUES ('2024-01-15', 'AAPL', 'BUY', -0.5, 150.0)
        """)
        self.conn.commit()
        with self.assertRaises(DataQualityError):
            check_transactions_quality(self.conn)

    def test_prices_rejects_zero_or_negative(self):
        """QC 2: Prices <= 0 must raise DataQualityError."""
        self.cursor.execute("""
        INSERT INTO prices (trade_date, ticker, close, adj_close)
        VALUES ('2024-01-15', 'SPY', 0.0, 0.0)
        """)
        self.conn.commit()
        with self.assertRaises(DataQualityError):
            check_prices_quality(self.conn)

    def test_fx_rejects_zero_or_negative(self):
        """QC 3: FX rates <= 0 must raise DataQualityError."""
        self.cursor.execute("""
        INSERT INTO fx_rates (trade_date, rate)
        VALUES ('2024-01-15', 0.0)
        """)
        self.conn.commit()
        with self.assertRaises(DataQualityError):
            check_fx_quality(self.conn)

if __name__ == '__main__':
    unittest.main()
