import sqlite3
from logger import logger
from database import get_connection, DB_NAME

class DataQualityError(Exception):
    """Custom Exception สำหรับข้อผิดพลาดด้านคุณภาพข้อมูล"""
    pass

def check_transactions_quality(conn):
    """
    QC 1: ตรวจสอบตาราง transactions
    """
    cursor = conn.cursor()
    
    # 1. ห้ามมีค่าว่างในคอลัมน์สำคัญ
    cursor.execute("""
    SELECT COUNT(*) FROM transactions 
    WHERE trade_date IS NULL OR ticker IS NULL OR action IS NULL 
       OR shares IS NULL OR price_per_share IS NULL
    """)
    null_count = cursor.fetchone()[0]
    if null_count > 0:
        raise DataQualityError(f"พบค่าว่างในตาราง transactions จำนวน {null_count} รายการ!")

    # 2. จำนวนหุ้นและราคาต้อง > 0, ค่าธรรมเนียมต้อง >= 0
    cursor.execute("""
    SELECT COUNT(*) FROM transactions 
    WHERE shares <= 0 OR price_per_share <= 0 OR fee < 0
    """)
    invalid_nums = cursor.fetchone()[0]
    if invalid_nums > 0:
        raise DataQualityError(f"พบจำนวนหุ้นหรือราคาที่ <= 0 จำนวน {invalid_nums} รายการ!")

    # 3. action ต้องเป็น BUY หรือ SELL เท่านั้น
    cursor.execute("""
    SELECT COUNT(*) FROM transactions 
    WHERE UPPER(action) NOT IN ('BUY', 'SELL')
    """)
    invalid_action = cursor.fetchone()[0]
    if invalid_action > 0:
        raise DataQualityError(f"พบประเภทคำสั่งที่ไม่ใช่ BUY/SELL จำนวน {invalid_action} รายการ!")

    logger.info("[QC PASSED] ตาราง transactions ผ่านการตรวจสอบคุณภาพ 100%")

def check_prices_quality(conn):
    """
    QC 2: ตรวจสอบตาราง prices
    """
    cursor = conn.cursor()
    
    # 1. ราคาปิดต้อง > 0
    cursor.execute("SELECT COUNT(*) FROM prices WHERE close <= 0 OR adj_close <= 0")
    bad_prices = cursor.fetchone()[0]
    if bad_prices > 0:
        raise DataQualityError(f"พบราคาหุ้น <= 0 จำนวน {bad_prices} รายการในตาราง prices!")

    # 2. ห้ามมีค่าว่าง
    cursor.execute("SELECT COUNT(*) FROM prices WHERE close IS NULL OR adj_close IS NULL")
    null_prices = cursor.fetchone()[0]
    if null_prices > 0:
        raise DataQualityError(f"พบค่าว่างในตาราง prices จำนวน {null_prices} รายการ!")

    logger.info("[QC PASSED] ตาราง prices ผ่านการตรวจสอบคุณภาพ 100%")

def check_fx_quality(conn):
    """
    QC 3: ตรวจสอบตาราง fx_rates
    """
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM fx_rates WHERE rate <= 0 OR rate IS NULL")
    bad_fx = cursor.fetchone()[0]
    if bad_fx > 0:
        raise DataQualityError(f"พบอัตราแลกเปลี่ยนผิดปกติ (<= 0 หรือเป็นค่าว่าง) จำนวน {bad_fx} รายการ!")

    logger.info("[QC PASSED] ตาราง fx_rates ผ่านการตรวจสอบคุณภาพ 100%")

def check_portfolio_daily_quality(conn):
    """
    QC 4: ตรวจสอบตาราง portfolio_daily
    """
    cursor = conn.cursor()
    cursor.execute("""
    SELECT COUNT(*) FROM portfolio_daily 
    WHERE real_portfolio_value_usd IS NULL 
       OR shadow_spy_value_usd IS NULL 
       OR shadow_qqq_value_usd IS NULL
    """)
    null_vals = cursor.fetchone()[0]
    if null_vals > 0:
        raise DataQualityError(f"พบค่าว่างในตารางสรุป portfolio_daily จำนวน {null_vals} วัน!")

    logger.info("[QC PASSED] ตาราง portfolio_daily ผ่านการตรวจสอบคุณภาพ 100%")

def run_all_qc_checks(db_name=DB_NAME):
    conn = get_connection(db_name)
    check_transactions_quality(conn)
    check_prices_quality(conn)
    check_fx_quality(conn)
    check_portfolio_daily_quality(conn)
    conn.close()

if __name__ == "__main__":
    run_all_qc_checks()
