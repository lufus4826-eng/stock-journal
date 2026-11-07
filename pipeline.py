import time
import sys
from logger import logger
from database import init_db, get_connection, DB_NAME
from data_quality import (
    check_transactions_quality,
    check_prices_quality,
    check_fx_quality,
    check_portfolio_daily_quality,
    DataQualityError
)
from extract import run_extract
from transform import calculate_daily_portfolio
from analytics import run_analytics

def run_pipeline(db_name=DB_NAME):
    """
    Master Pipeline: ควบคุมกระบวนการตั้งแต่ต้นจนจบแบบอัตโนมัติ
    พร้อมระบบตรวจจับข้อผิดพลาด (Error Handling) และบันทึก Log
    """
    start_time = time.time()
    logger.info("==================================================")
    logger.info("🚀 STARTING STOCK JOURNAL DAILY ETL PIPELINE")
    logger.info("==================================================")

    conn = None
    try:
        # Step 1: ตรวจสอบและสร้างฐานข้อมูล (ถ้ายังไม่มี)
        logger.info("[STEP 1/6] Initializing database schema...")
        init_db(db_name)

        conn = get_connection(db_name)

        # Step 2: ตรวจคุณภาพข้อมูลการซื้อขายก่อนเริ่มงาน (Pre-Check)
        logger.info("[STEP 2/6] Running Data Quality check on transactions...")
        check_transactions_quality(conn)

        # Step 3: ดึงข้อมูลราคาหุ้นและอัตราแลกเปลี่ยน (Extract)
        logger.info("[STEP 3/6] Running Extract process (yfinance)...")
        run_extract(db_name)

        # Step 4: ตรวจคุณภาพข้อมูลราคาที่เพิ่งดึงมา
        logger.info("[STEP 4/6] Running Data Quality check on market prices & FX...")
        check_prices_quality(conn)
        check_fx_quality(conn)

        # Step 5: คำนวณมูลค่าพอร์ตจริงและพอร์ตเงารายวัน (Transform)
        logger.info("[STEP 5/6] Running Transform process (Daily Portfolio Benchmark)...")
        calculate_daily_portfolio(db_name)

        # Step 6: วิเคราะห์ผลตอบแทนเชิงลึก และตรวจคุณภาพผลลัพธ์สุดท้าย
        logger.info("[STEP 6/6] Running Analytics & Decision Review...")
        run_analytics(db_name)
        check_portfolio_daily_quality(conn)

        elapsed = round(time.time() - start_time, 2)
        logger.info("==================================================")
        logger.info(f"✅ PIPELINE EXECUTED SUCCESSFULLY in {elapsed} seconds!")
        logger.info("==================================================")

    except DataQualityError as dqe:
        logger.error(f"❌ [DATA QUALITY HALT] ระบบถูกระงับเนื่องจากข้อมูลไม่ได้มาตรฐาน: {dqe}")
        sys.exit(1)

    except Exception as e:
        logger.error(f"❌ [CRITICAL ERROR] เกิดข้อผิดพลาดที่ไม่คาดคิดใน Pipeline: {str(e)}", exc_info=True)
        sys.exit(1)

    finally:
        if conn:
            conn.close()
            logger.info("Closed database connection safely.")

if __name__ == "__main__":
    run_pipeline()
