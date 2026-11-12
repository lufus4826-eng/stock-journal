import sqlite3
import pandas as pd
import yfinance as yf
from database import get_connection, DB_NAME

def get_target_tickers(conn):
    """
    ดึงรายชื่อหุ้นที่ไม่ซ้ำจากตาราง transactions และเพิ่มดัชนี SPY, QQQ
    """
    query = "SELECT DISTINCT ticker FROM transactions"
    df = pd.read_sql_query(query, conn)
    
    tickers = df['ticker'].tolist()
    
    benchmarks = ['SPY', 'QQQ']
    for b in benchmarks:
        if b not in tickers:
            tickers.append(b)
            
    return tickers

def get_start_date(conn):
    """
    หาวันที่ซื้อหุ้นครั้งแรกสุด แล้วถอยหลังไป 7 วัน เพื่อให้ได้ราคาของวันทำการก่อนหน้าเสมอ
    """
    query = "SELECT MIN(trade_date) as start_date FROM transactions"
    df = pd.read_sql_query(query, conn)
    
    start_date = df['start_date'].iloc[0]
    # เผื่อเวลาถอยหลัง 7 วัน สำหรับกรณีวันหยุดตลาด (Market Holidays)
    buffered_start = (pd.to_datetime(start_date) - pd.Timedelta(days=7)).strftime('%Y-%m-%d')
    return buffered_start

def fetch_and_save_prices(conn, tickers, start_date):
    """
    วนลูปดึงราคาหุ้นและดัชนี แล้วบันทึกลงตาราง prices
    """
    cursor = conn.cursor()
    
    for ticker in tickers:
        print(f"[FETCH] Downloading price history for: {ticker}...")
        stock = yf.Ticker(ticker)
        # auto_adjust=False เพื่อให้ได้ทั้ง Close ปกติ และ Adj Close ที่รวมปันผล
        hist = stock.history(start=start_date, auto_adjust=False)
        if not hist.empty:
            # กรองแถวที่ราคาปิดยังเป็นค่าว่าง (NaN) ออกจากผลลัพธ์ของ yfinance
            hist = hist.dropna(subset=['Close', 'Adj Close'])
        
        if hist.empty:
            print(f"[WARN] No price data found for {ticker}")
            continue
            
        data_to_insert = []
        for index, row in hist.iterrows():
            trade_date = index.strftime('%Y-%m-%d')
            close_price = float(row['Close'])
            adj_close_price = float(row['Adj Close'])
            data_to_insert.append((trade_date, ticker, close_price, adj_close_price))
            
        cursor.executemany("""
        INSERT OR REPLACE INTO prices (trade_date, ticker, close, adj_close)
        VALUES (?, ?, ?, ?)
        """, data_to_insert)
        
    conn.commit()
    print("[SUCCESS] All stock prices fetched and saved to SQLite!")

def fetch_and_save_fx(conn, start_date):
    """
    ดึงอัตราแลกเปลี่ยน USD/THB จาก yfinance (THB=X) แล้วบันทึกลงตาราง fx_rates
    """
    cursor = conn.cursor()
    print("[FETCH] Downloading USD/THB exchange rates (THB=X)...")
    
    fx = yf.Ticker("THB=X")
    hist = fx.history(start=start_date)
    if not hist.empty:
        # กรองแถวที่อัตราแลกเปลี่ยนเป็นค่าว่าง (NaN) ออก
        hist = hist.dropna(subset=['Close'])
    
    if hist.empty:
        print("[WARN] No FX data found for THB=X")
        return
        
    data_to_insert = []
    for index, row in hist.iterrows():
        trade_date = index.strftime('%Y-%m-%d')
        rate = float(row['Close'])
        data_to_insert.append((trade_date, rate))
        
    cursor.executemany("""
    INSERT OR REPLACE INTO fx_rates (trade_date, rate)
    VALUES (?, ?)
    """, data_to_insert)
    
    conn.commit()
    print("[SUCCESS] USD/THB exchange rates fetched and saved to SQLite!")

def fetch_and_save_splits(conn, tickers):
    """
    ดึงประวัติการแตกหุ้น (Stock Splits) เพื่อปรับจำนวนหุ้นให้ถูกต้องอัตโนมัติ
    """
    cursor = conn.cursor()
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS stock_splits (
        ticker TEXT NOT NULL,
        split_date TEXT NOT NULL,
        split_ratio REAL NOT NULL,
        PRIMARY KEY (ticker, split_date)
    );
    """)
    
    for ticker in tickers:
        stock = yf.Ticker(ticker)
        splits = stock.splits
        if not splits.empty:
            for dt, ratio in splits.items():
                split_date = dt.strftime('%Y-%m-%d')
                cursor.execute("""
                INSERT OR REPLACE INTO stock_splits (ticker, split_date, split_ratio)
                VALUES (?, ?, ?)
                """, (ticker, split_date, float(ratio)))
                
    conn.commit()
    print("[SUCCESS] Stock splits history fetched and saved to SQLite!")

def run_extract(db_name=DB_NAME):
    """
    ฟังก์ชันหลักที่คอยรันขั้นตอน Extract ทั้งหมด
    """
    print("--- STARTING EXTRACT PROCESS ---")
    conn = get_connection(db_name)
    
    # 1. หาวันเริ่มต้นและหุ้นที่ต้องดึง
    start_date = get_start_date(conn)
    tickers = get_target_tickers(conn)
    
    print(f"Start Date: {start_date}")
    print(f"Target Tickers: {tickers}")
    
    # 2. ดึงราคาหุ้น
    fetch_and_save_prices(conn, tickers, start_date)
    
    # 3. ดึงค่าเงิน USD/THB
    fetch_and_save_fx(conn, start_date)
    
    # 4. ดึงประวัติการแตกหุ้น (Stock Splits)
    fetch_and_save_splits(conn, tickers)
    
    conn.close()
    print("--- EXTRACT PROCESS COMPLETED ---")

if __name__ == "__main__":
    run_extract()
