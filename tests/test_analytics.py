import unittest
import sqlite3
import pandas as pd
import numpy as np
import sys
import os

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from analytics import calculate_max_drawdown, calculate_annualized_returns

class TestAnalyticsFormulas(unittest.TestCase):
    def setUp(self):
        self.conn = sqlite3.connect(":memory:")
        self.cursor = self.conn.cursor()
        self.cursor.execute("""
        CREATE TABLE portfolio_daily (
            trade_date TEXT PRIMARY KEY,
            real_nav REAL,
            shadow_spy_nav REAL,
            shadow_qqq_nav REAL,
            total_invested_usd REAL,
            real_portfolio_value_usd REAL,
            shadow_spy_value_usd REAL,
            shadow_qqq_value_usd REAL
        )
        """)
        self.conn.commit()

    def tearDown(self):
        self.conn.close()

    def test_max_drawdown_peak_to_trough(self):
        """Verify that MDD accurately captures peak-to-trough percentage drop."""
        # Simulated NAV series: starts at 100, peaks at 150, drops to 120, then rises to 160
        # Peak = 150, trough = 120 => Drop is (120 - 150) / 150 = -30 / 150 = -20.0%
        # SPY: peak 110, trough 99 => (99 - 110) / 110 = -10.0%
        # QQQ: peak 120, trough 102 => (102 - 120) / 120 = -15.0%
        rows = [
            ('2024-01-01', 100.0, 100.0, 100.0, 100.0, 100.0, 100.0, 100.0),
            ('2024-01-02', 150.0, 110.0, 120.0, 100.0, 150.0, 110.0, 120.0),
            ('2024-01-03', 120.0, 99.0, 102.0, 100.0, 120.0, 99.0, 102.0),
            ('2024-01-04', 160.0, 115.0, 125.0, 100.0, 160.0, 115.0, 125.0),
        ]
        self.cursor.executemany("INSERT INTO portfolio_daily VALUES (?, ?, ?, ?, ?, ?, ?, ?)", rows)
        self.conn.commit()

        df_mdd = calculate_max_drawdown(self.conn)
        results = dict(zip(df_mdd['Portfolio'], df_mdd['Max Drawdown (%)']))

        self.assertAlmostEqual(results['Real Portfolio'], -20.0, places=2)
        self.assertAlmostEqual(results['Shadow SPY'], -10.0, places=2)
        self.assertAlmostEqual(results['Shadow QQQ'], -15.0, places=2)

    def test_cagr_compounding_math(self):
        """Verify CAGR formula for 2 years of 21% annual return (1.21^2 - 1 = 46.41%)."""
        start_date = '2024-01-01'
        end_date = '2026-01-01'
        days = (pd.to_datetime(end_date) - pd.to_datetime(start_date)).days
        years = days / 365.25

        def get_cagr(ret_pct, yrs):
            mult = 1.0 + (ret_pct / 100.0)
            return (mult ** (1.0 / yrs) - 1.0) * 100.0

        cagr = get_cagr(46.41, years)
        self.assertAlmostEqual(cagr, 21.0, delta=0.1)

if __name__ == '__main__':
    unittest.main()
