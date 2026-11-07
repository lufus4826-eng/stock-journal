import logging
import sys

def setup_logger(name="StockJournal"):
    """
    ตั้งค่า Logger ให้พิมพ์ออกหน้าจอ และบันทึกลงไฟล์ stock_journal.log พร้อมกัน
    """
    logger = logging.getLogger(name)
    logger.setLevel(logging.INFO)

    # ป้องกันการผูก Handler ซ้ำซ้อนเวลารันหลายรอบ
    if not logger.handlers:
        formatter = logging.Formatter(
            '[%(asctime)s] [%(levelname)s] [%(name)s]: %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S'
        )

        # 1. แสดงผลออกหน้าจอ Console (รองรับ UTF-8 ปลอดภัยบนทุกระบบปฏิบัติการ)
        import io
        safe_stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
        console_handler = logging.StreamHandler(safe_stdout)
        console_handler.setFormatter(formatter)
        logger.addHandler(console_handler)

        # 2. บันทึกลงไฟล์ stock_journal.log (ใช้ encoding utf-8 เสมอ)
        file_handler = logging.FileHandler("stock_journal.log", encoding="utf-8")
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)

    return logger

logger = setup_logger()
