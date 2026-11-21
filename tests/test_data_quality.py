import os
import tempfile
import unittest

from data_quality import (
    DataQualityError,
    check_fx_quality,
    check_portfolio_daily_quality,
    check_prices_quality,
    check_transactions_quality,
)
from database import get_connection, init_db


class TestDataQualityGates(unittest.TestCase):
    """ทดสอบด่านตรวจคุณภาพข้อมูล (Data Quality Gates) ก่อนและหลังประมวลผล"""

    def setUp(self):
        # ใช้ฐานข้อมูลชั่วคราวสำหรับเทสต์ เพื่อไม่ให้กระทบ stock_journal.db จริง
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = os.path.join(self.temp_dir.name, "test_qc.db")
        init_db(self.db_path)
        self.conn = get_connection(self.db_path)

    def tearDown(self):
        self.conn.close()
        self.temp_dir.cleanup()

    def test_valid_records_pass_all_qc_gates(self):
        """ข้อมูลที่ถูกต้องตามกติกาต้องผ่านทั้ง 4 ด่านโดยไม่เกิด Error"""
        cur = self.conn.cursor()
        cur.execute(
            "INSERT INTO transactions (trade_date, ticker, action, shares, price_per_share, fee) "
            "VALUES ('2024-02-05', 'NVDA', 'BUY', 0.1, 693.0, 0.0)"
        )
        cur.execute(
            "INSERT INTO prices (trade_date, ticker, close, adj_close) "
            "VALUES ('2024-02-05', 'NVDA', 693.0, 693.0)"
        )
        cur.execute("INSERT INTO fx_rates (trade_date, rate) VALUES ('2024-02-05', 35.5)")
        cur.execute(
            "INSERT INTO portfolio_daily VALUES "
            "('2024-02-05', 69.3, 69.3, 69.3, 69.3, 2460.15, 2460.15, 2460.15, 35.5, 100.0, 100.0, 100.0)"
        )
        self.conn.commit()

        check_transactions_quality(self.conn)
        check_prices_quality(self.conn)
        check_fx_quality(self.conn)
        check_portfolio_daily_quality(self.conn)

    def test_zero_or_negative_shares_blocks_pipeline(self):
        """จำนวนหุ้น <= 0 ต้องถูกด่าน transactions ดักจับและโยน DataQualityError"""
        self.conn.execute(
            "INSERT INTO transactions (trade_date, ticker, action, shares, price_per_share, fee) "
            "VALUES ('2024-02-05', 'NVDA', 'BUY', -0.5, 693.0, 0.0)"
        )
        self.conn.commit()

        with self.assertRaises(DataQualityError):
            check_transactions_quality(self.conn)

    def test_invalid_trade_action_blocks_pipeline(self):
        """คำสั่งซื้อขายที่ไม่ใช่ BUY หรือ SELL ต้องไม่ผ่านด่าน QC"""
        self.conn.execute(
            "INSERT INTO transactions (trade_date, ticker, action, shares, price_per_share, fee) "
            "VALUES ('2024-02-05', 'NVDA', 'HOLD', 1.0, 693.0, 0.0)"
        )
        self.conn.commit()

        with self.assertRaises(DataQualityError):
            check_transactions_quality(self.conn)

    def test_bad_price_and_fx_rate_block_pipeline(self):
        """ราคาหุ้นหรืออัตราแลกเปลี่ยน <= 0 ต้องไม่ผ่านด่าน QC"""
        self.conn.execute(
            "INSERT INTO prices (trade_date, ticker, close, adj_close) "
            "VALUES ('2024-02-05', 'NVDA', 0.0, 693.0)"
        )
        self.conn.execute("INSERT INTO fx_rates (trade_date, rate) VALUES ('2024-02-05', -35.0)")
        self.conn.commit()

        with self.assertRaises(DataQualityError):
            check_prices_quality(self.conn)
        with self.assertRaises(DataQualityError):
            check_fx_quality(self.conn)

    def test_null_nav_in_portfolio_daily_blocks_pipeline(self):
        """ค่า Unit NAV ที่เป็น NULL ในตารางสรุปผลต้องถูกดักจับที่ด่านสุดท้าย"""
        self.conn.execute(
            "INSERT INTO portfolio_daily "
            "(trade_date, total_invested_usd, real_portfolio_value_usd, shadow_spy_value_usd, "
            "shadow_qqq_value_usd, real_portfolio_value_thb, shadow_spy_value_thb, "
            "shadow_qqq_value_thb, fx_rate, real_nav, shadow_spy_nav, shadow_qqq_nav) "
            "VALUES ('2024-02-05', 100.0, 100.0, 100.0, 100.0, 3500.0, 3500.0, 3500.0, 35.0, NULL, 100.0, 100.0)"
        )
        self.conn.commit()

        with self.assertRaises(DataQualityError):
            check_portfolio_daily_quality(self.conn)


if __name__ == "__main__":
    unittest.main()
