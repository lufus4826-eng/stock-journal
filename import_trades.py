import pandas as pd
import sqlite3

def load_trades_from_csv(csv_path="trades_input.csv", db_path="stock_journal.db"):
    # 1. อ่านไฟล์ CSV ด้วย pandas
    df = pd.read_csv(csv_path)
    
    # 2. เชื่อมต่อฐานข้อมูล SQLite
    conn = sqlite3.connect(db_path)
    
    # 3. โยนข้อมูลจาก DataFrame ลงตาราง transactions
    df.to_sql(name="transactions", con=conn, if_exists="append", index=False)
    
    conn.close()
    print("[SUCCESS] Loaded trades from CSV into SQLite successfully!")

if __name__ == "__main__":
    load_trades_from_csv()
