import sqlite3

# กำหนดชื่อไฟล์ฐานข้อมูลเริ่มต้น
DB_NAME = "stock_journal.db"

def get_connection(db_name=DB_NAME):
    """
    ฟังก์ชันสำหรับเปิดการเชื่อมต่อกับฐานข้อมูล SQLite
    """
    conn = sqlite3.connect(db_name)
    # ช่วยให้ผลลัพธ์เวลา query ออกมาเป็น dictionary เข้าถึงด้วยชื่อคอลัมน์ได้ง่าย
    conn.row_factory = sqlite3.Row
    return conn

def init_db(db_name=DB_NAME):
    """
    ฟังก์ชันสร้างตารางทั้งหมดที่จำเป็นสำหรับระบบ Stock Journal
    """
    conn = get_connection(db_name)
    cursor = conn.cursor()

    # 1. ตารางประวัติการซื้อขาย (Transactions)
    # สำหรับบันทึกรายการที่เรากรอกผ่าน Dashboard ในอนาคต
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS transactions (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        trade_date TEXT NOT NULL,           -- รูปแบบ 'YYYY-MM-DD'
        ticker TEXT NOT NULL,               -- เช่น 'AAPL', 'NVDA'
        action TEXT NOT NULL,               -- 'BUY' หรือ 'SELL'
        shares REAL NOT NULL,               -- จำนวนหุ้น (ทศนิยม เช่น 0.1254)
        price_per_share REAL NOT NULL,      -- ราคาต่อหุ้น (USD)
        fee REAL DEFAULT 0.0,               -- ค่าธรรมเนียม (USD)
        reason_category TEXT,               -- ประเภทเหตุผล เช่น 'Growth', 'Dividend', 'FOMO'
        notes TEXT                          -- บันทึกเพิ่มเติม
    );
    """)

    # 2. ตารางราคาปิดหุ้นรายวัน (Prices)
    # ใช้ Composite Primary Key (trade_date, ticker) เพื่อห้ามข้อมูลซ้ำในวันเดียวกัน
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS prices (
        trade_date TEXT NOT NULL,
        ticker TEXT NOT NULL,
        close REAL NOT NULL,
        adj_close REAL NOT NULL,
        PRIMARY KEY (trade_date, ticker)
    );
    """)

    # 3. ตารางอัตราแลกเปลี่ยนรายวัน (FX Rates)
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS fx_rates (
        trade_date TEXT PRIMARY KEY,
        rate REAL NOT NULL                  -- อัตราแลกเปลี่ยน USD/THB เช่น 36.50
    );
    """)

    # 4. ตารางสรุปมูลค่าพอร์ตรายวัน (Daily Portfolio Benchmark)
    # เก็บข้อมูลหลังจากฝั่ง Transform คำนวณเสร็จ เพื่อให้ Dashboard ดึงไปวาดกราฟได้ทันที
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS portfolio_daily (
        trade_date TEXT PRIMARY KEY,
        total_invested_usd REAL NOT NULL,
        real_portfolio_value_usd REAL NOT NULL,
        shadow_spy_value_usd REAL NOT NULL,
        shadow_qqq_value_usd REAL NOT NULL,
        real_portfolio_value_thb REAL NOT NULL,
        shadow_spy_value_thb REAL NOT NULL,
        shadow_qqq_value_thb REAL NOT NULL,
        fx_rate REAL NOT NULL
    );
    """)

    conn.commit()
    conn.close()
    print("[SUCCESS] Database and all 4 tables initialized successfully!")

def add_transaction(trade_date, ticker, action, shares, price_per_share, fee=0.0, reason_category=None, notes=None, db_name=DB_NAME):
    """
    ฟังก์ชันสำหรับเพิ่มรายการซื้อขายใหม่ 1 รายการ 
    (ในอนาคต Dashboard จะเรียกใช้ฟังก์ชันนี้เวลากดปุ่มบันทึก)
    """
    conn = get_connection(db_name)
    cursor = conn.cursor()
    cursor.execute("""
    INSERT INTO transactions (
        trade_date, ticker, action, shares, price_per_share, fee, reason_category, notes
    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    """, (trade_date, ticker.upper(), action.upper(), shares, price_per_share, fee, reason_category, notes))
    
    conn.commit()
    conn.close()
    print(f"[SUCCESS] Recorded {action} {ticker} successfully!")

if __name__ == "__main__":
    init_db()
