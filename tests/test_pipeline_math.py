import os
import tempfile
import unittest

import pandas as pd

from analytics import calculate_max_drawdown
from database import get_connection, init_db
from transform import calculate_daily_portfolio, get_split_adjusted_trades


class TestPipelineMath(unittest.TestCase):
    """ทดสอบตรรกะคณิตศาสตร์หลัก: Stock Split, วันหยุดตลาด, Unit NAV และ Max Drawdown"""

    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = os.path.join(self.temp_dir.name, "test_math.db")
        init_db(self.db_path)
        self.conn = get_connection(self.db_path)
        self.conn.execute(
            """
            CREATE TABLE IF NOT EXISTS stock_splits (
                ticker TEXT NOT NULL,
                split_date TEXT NOT NULL,
                split_ratio REAL NOT NULL,
                PRIMARY KEY (ticker, split_date)
            );
            """
        )
        self.conn.commit()

    def tearDown(self):
        self.conn.close()
        self.temp_dir.cleanup()

    def test_stock_split_adjusts_only_pre_split_trades(self):
        """ไม้ที่ซื้อก่อนแตกพาร์ 10:1 ต้องคูณหุ้น x10 หารราคา /10 แต่ไม้หลังแตกพาร์ต้องคงเดิม"""
        self.conn.execute(
            "INSERT INTO stock_splits (ticker, split_date, split_ratio) VALUES ('NVDA', '2024-06-10', 10.0)"
        )
        # ไม้ก่อนแตกพาร์: 0.10 หุ้น @ $693.00 (เงินต้น $69.30)
        self.conn.execute(
            "INSERT INTO transactions (trade_date, ticker, action, shares, price_per_share, fee) "
            "VALUES ('2024-02-05', 'NVDA', 'BUY', 0.10, 693.0, 0.0)"
        )
        # ไม้หลังแตกพาร์: 0.50 หุ้น @ $131.00
        self.conn.execute(
            "INSERT INTO transactions (trade_date, ticker, action, shares, price_per_share, fee) "
            "VALUES ('2024-06-17', 'NVDA', 'BUY', 0.50, 131.0, 0.0)"
        )
        self.conn.commit()

        adjusted = get_split_adjusted_trades(self.conn)
        pre_split = adjusted.iloc[0]
        post_split = adjusted.iloc[1]

        self.assertAlmostEqual(pre_split["shares"], 1.0, places=6)
        self.assertAlmostEqual(pre_split["price_per_share"], 69.3, places=6)
        self.assertAlmostEqual(post_split["shares"], 0.5, places=6)
        self.assertAlmostEqual(post_split["price_per_share"], 131.0, places=6)

    def test_unit_nav_is_unaffected_by_new_cash_deposits(self):
        """เมื่อราคาตลาดเท่าเดิม การเติมเงินซื้อเพิ่มในวันที่ 2 ต้องไม่ทำให้ Unit NAV กระโดดขึ้น"""
        # ซื้อ NVDA $100 ในวันที่ 1 และเติมเงินซื้อเพิ่มอีก $100 ในวันที่ 2 ที่ราคาตลาดเท่าเดิม ($100)
        self.conn.executemany(
            "INSERT INTO transactions (trade_date, ticker, action, shares, price_per_share, fee) VALUES (?, ?, ?, ?, ?, ?)",
            [
                ("2024-01-02", "NVDA", "BUY", 1.0, 100.0, 0.0),
                ("2024-01-03", "NVDA", "BUY", 1.0, 100.0, 0.0),
            ],
        )
        self.conn.executemany(
            "INSERT INTO prices (trade_date, ticker, close, adj_close) VALUES (?, ?, ?, ?)",
            [
                ("2024-01-02", "NVDA", 100.0, 100.0),
                ("2024-01-03", "NVDA", 100.0, 100.0),
                ("2024-01-02", "SPY", 500.0, 500.0),
                ("2024-01-03", "SPY", 500.0, 500.0),
                ("2024-01-02", "QQQ", 400.0, 400.0),
                ("2024-01-03", "QQQ", 400.0, 400.0),
            ],
        )
        self.conn.executemany(
            "INSERT INTO fx_rates (trade_date, rate) VALUES (?, ?)",
            [("2024-01-02", 35.0), ("2024-01-03", 35.0)],
        )
        self.conn.commit()

        calculate_daily_portfolio(self.db_path)

        df_daily = pd.read_sql_query("SELECT * FROM portfolio_daily ORDER BY trade_date ASC", self.conn)
        self.assertEqual(len(df_daily), 2)
        self.assertAlmostEqual(df_daily.iloc[1]["total_invested_usd"], 200.0, places=2)
        self.assertAlmostEqual(df_daily.iloc[1]["real_portfolio_value_usd"], 200.0, places=2)
        # เงินต้นเพิ่มจาก $100 เป็น $200 แต่มูลค่าต่อหน่วย (Unit NAV) ต้องยังอยู่ที่ 100.0 เท่าเดิม
        self.assertAlmostEqual(df_daily.iloc[1]["real_nav"], 100.0, places=4)

    def test_market_holiday_uses_forward_fill(self):
        """คำสั่งซื้อในวันหยุดตลาด (ไม่มีราคาปิดวันนั้น) ต้องดึงราคาก่อนหน้ามาเติมได้โดยไม่เป็น NULL"""
        # สมมติซื้อวันจันทร์ 2024-01-15 (MLK Day) แต่ตารางราคามีเฉพาะวันศุกร์ก่อนหน้ากับวันอังคารถัดไป
        self.conn.execute(
            "INSERT INTO transactions (trade_date, ticker, action, shares, price_per_share, fee) "
            "VALUES ('2024-01-15', 'VOO', 'BUY', 1.0, 436.0, 0.0)"
        )
        self.conn.executemany(
            "INSERT INTO prices (trade_date, ticker, close, adj_close) VALUES (?, ?, ?, ?)",
            [
                ("2024-01-12", "VOO", 436.0, 436.0),
                ("2024-01-16", "VOO", 440.0, 440.0),
                ("2024-01-12", "SPY", 476.0, 476.0),
                ("2024-01-16", "SPY", 475.0, 475.0),
                ("2024-01-12", "QQQ", 409.0, 409.0),
                ("2024-01-16", "QQQ", 410.0, 410.0),
            ],
        )
        self.conn.executemany(
            "INSERT INTO fx_rates (trade_date, rate) VALUES (?, ?)",
            [("2024-01-12", 35.0), ("2024-01-16", 35.0)],
        )
        self.conn.commit()

        calculate_daily_portfolio(self.db_path)

        row = self.conn.execute(
            "SELECT real_portfolio_value_usd, shadow_spy_value_usd FROM portfolio_daily WHERE trade_date = '2024-01-15'"
        ).fetchone()
        self.assertIsNotNone(row)
        self.assertAlmostEqual(row["real_portfolio_value_usd"], 436.0, places=2)
        self.assertAlmostEqual(row["shadow_spy_value_usd"], 436.0, places=2)

    def test_max_drawdown_exact_peak_to_trough(self):
        """ตรวจสอบสูตร Max Drawdown จากจุดสูงสุด 120 ร่วงลงมาที่ 90 ต้องได้ -25.00%"""
        rows = [
            ("2024-01-01", 100.0, 100.0, 100.0),
            ("2024-01-02", 120.0, 100.0, 110.0),
            ("2024-01-03", 90.0, 80.0, 99.0),
            ("2024-01-04", 108.0, 95.0, 105.0),
        ]
        for dt, r_nav, s_nav, q_nav in rows:
            self.conn.execute(
                "INSERT INTO portfolio_daily "
                "(trade_date, total_invested_usd, real_portfolio_value_usd, shadow_spy_value_usd, "
                "shadow_qqq_value_usd, real_portfolio_value_thb, shadow_spy_value_thb, "
                "shadow_qqq_value_thb, fx_rate, real_nav, shadow_spy_nav, shadow_qqq_nav) "
                "VALUES (?, 100.0, 100.0, 100.0, 100.0, 3500.0, 3500.0, 3500.0, 35.0, ?, ?, ?)",
                (dt, r_nav, s_nav, q_nav),
            )
        self.conn.commit()

        df_mdd = calculate_max_drawdown(self.conn).set_index("Portfolio")
        self.assertAlmostEqual(df_mdd.loc["Real Portfolio", "Max Drawdown (%)"], -25.0, places=2)
        self.assertAlmostEqual(df_mdd.loc["Shadow SPY", "Max Drawdown (%)"], -20.0, places=2)
        self.assertAlmostEqual(df_mdd.loc["Shadow QQQ", "Max Drawdown (%)"], -10.0, places=2)


if __name__ == "__main__":
    unittest.main()
