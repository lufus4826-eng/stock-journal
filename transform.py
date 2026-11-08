import sqlite3
import pandas as pd
from database import get_connection, DB_NAME

def get_split_adjusted_trades(conn):
    """
    ดึงข้อมูลการซื้อขาย และปรับจำนวนหุ้นอัตโนมัติหากหุ้นตัวนั้นมีการแตกพาร์ (Stock Split) ภายหลังวันซื้อ
    """
    trades_df = pd.read_sql_query("SELECT * FROM transactions ORDER BY trade_date ASC", conn)
    try:
        splits_df = pd.read_sql_query("SELECT * FROM stock_splits", conn)
    except Exception:
        splits_df = pd.DataFrame()
        
    if splits_df.empty or trades_df.empty:
        return trades_df

    for idx, trade in trades_df.iterrows():
        ticker = trade['ticker']
        t_date = trade['trade_date']
        applicable_splits = splits_df[(splits_df['ticker'] == ticker) & (splits_df['split_date'] > t_date)]
        if not applicable_splits.empty:
            cum_ratio = applicable_splits['split_ratio'].prod()
            trades_df.at[idx, 'shares'] = trade['shares'] * cum_ratio
            trades_df.at[idx, 'price_per_share'] = trade['price_per_share'] / cum_ratio

    return trades_df

def calculate_daily_portfolio(db_name=DB_NAME):
    """
    ฟังก์ชันคำนวณมูลค่าพอร์ตจริง เทียบกับ พอร์ตเงา SPY และ QQQ แบบวันต่อวัน
    """
    print("--- STARTING TRANSFORM: DAILY PORTFOLIO BENCHMARK ---")
    conn = get_connection(db_name)
    
    # 1. ดึงประวัติการซื้อขายที่ปรับแตกพาร์แล้ว
    trades_df = get_split_adjusted_trades(conn)
    if trades_df.empty:
        print("[WARN] No transactions found to process.")
        conn.close()
        return

    # 2. ดึงราคาหุ้นทั้งหมด แล้วทำ Pivot ให้ชื่อหุ้นเป็นหัวคอลัมน์
    prices_raw = pd.read_sql_query("SELECT trade_date, ticker, adj_close FROM prices", conn)
    price_matrix = prices_raw.pivot(index='trade_date', columns='ticker', values='adj_close')
    
    # 3. ดึงอัตราแลกเปลี่ยน USD/THB
    fx_raw = pd.read_sql_query("SELECT trade_date, rate FROM fx_rates", conn)
    fx_series = fx_raw.set_index('trade_date')['rate']

    # 4. เติมราคาเต็มทุกวันตั้งแต่วันที่มีข้อมูลใน DB (รวม 7 วันบัฟเฟอร์) ด้วย ffill
    full_dates = pd.date_range(start=price_matrix.index.min(), end=price_matrix.index.max(), freq='D').strftime('%Y-%m-%d')
    price_matrix = price_matrix.reindex(full_dates).ffill().bfill()
    fx_series = fx_series.reindex(full_dates).ffill().bfill()

    # เส้นเวลาจำลองพอร์ต เริ่มจากวันที่ซื้อครั้งแรกสุด ถึงวันล่าสุด
    start_date = trades_df['trade_date'].min()
    end_date = price_matrix.index.max()
    all_dates = pd.date_range(start=start_date, end=end_date, freq='D').strftime('%Y-%m-%d')

    # 5. ตัวแปรเก็บสถานะพอร์ต (State Tracking)
    real_holdings = {}           # เช่น {'AAPL': 0.5432, 'NVDA': 0.125}
    total_invested_usd = 0.0     # เงินต้นสะสมสุทธิ (USD)
    shadow_spy_shares = 0.0      # หุ้น SPY ในพอร์ตเงา
    shadow_qqq_shares = 0.0      # หุ้น QQQ ในพอร์ตเงา

    # ตัวแปร Time-Weighted Return (Unit NAV) เริ่มต้นที่ 100.0 (มาตรฐานกองทุนรวม)
    # เพื่อตัดผลกระทบของการเติมเงินหรือถอนเงิน (Cash Flow Distortion)
    real_nav = 100.0
    shadow_spy_nav = 100.0
    shadow_qqq_nav = 100.0
    prev_date = None

    daily_records = []

    # 6. เดินหน้าจำลองพอร์ตวันต่อวัน
    for current_date in all_dates:
        # อัปเดต Unit NAV จากการขยับของราคาตลาดของหุ้นที่ถือครองข้ามคืน (ก่อนมีรายการซื้อขายใหม่ของวันนี้)
        if prev_date is not None and sum(real_holdings.values()) > 0:
            val_yesterday = sum(s * price_matrix.loc[prev_date, t] for t, s in real_holdings.items() if t in price_matrix.columns)
            val_today_prior = sum(s * price_matrix.loc[current_date, t] for t, s in real_holdings.items() if t in price_matrix.columns)
            r_real = (val_today_prior / val_yesterday - 1.0) if val_yesterday > 0 else 0.0
            real_nav *= (1.0 + r_real)

            r_spy = (price_matrix.loc[current_date, 'SPY'] / price_matrix.loc[prev_date, 'SPY']) - 1.0
            shadow_spy_nav *= (1.0 + r_spy)

            r_qqq = (price_matrix.loc[current_date, 'QQQ'] / price_matrix.loc[prev_date, 'QQQ']) - 1.0
            shadow_qqq_nav *= (1.0 + r_qqq)

        # เช็กว่าวันนี้มีรายการซื้อขายในตาราง transactions หรือไม่
        days_trades = trades_df[trades_df['trade_date'] == current_date]
        
        for _, trade in days_trades.iterrows():
            ticker = trade['ticker']
            action = trade['action'].upper()
            shares = float(trade['shares'])
            price = float(trade['price_per_share'])
            fee = float(trade['fee'])
            
            # ราคา SPY และ QQQ ณ วันที่ทำรายการ (ถ้าเป็นวันหยุด ffill จะดึงราคาก่อนหน้ามาให้)
            spy_price = price_matrix.loc[current_date, 'SPY']
            qqq_price = price_matrix.loc[current_date, 'QQQ']

            if action == 'BUY':
                # พอร์ตจริง: เพิ่มจำนวนหุ้น
                real_holdings[ticker] = real_holdings.get(ticker, 0.0) + shares
                
                # คิดเงินสดที่จ่ายไปทั้งหมด (รวมค่าธรรมเนียม)
                cash_flow = (shares * price) + fee
                total_invested_usd += cash_flow
                
                # พอร์ตเงา: เอาเงินก้อนเดียวกันไปซื้อ SPY และ QQQ
                shadow_spy_shares += cash_flow / spy_price
                shadow_qqq_shares += cash_flow / qqq_price

            elif action == 'SELL':
                # พอร์ตจริง: ลดจำนวนหุ้น
                real_holdings[ticker] = real_holdings.get(ticker, 0.0) - shares
                
                # คิดเงินสดสุทธิที่ได้รับกลับมา (หักค่าธรรมเนียม)
                cash_flow = (shares * price) - fee
                total_invested_usd -= cash_flow
                
                # พอร์ตเงา: ขาย SPY และ QQQ ออกมาเป็นมูลค่าเงินเท่ากัน
                shadow_spy_shares -= cash_flow / spy_price
                shadow_qqq_shares -= cash_flow / qqq_price

        # คำนวณมูลค่าพอร์ตจริงตอนสิ้นวัน (รวมหุ้นทุกตัวในพอร์ต)
        real_portfolio_value_usd = 0.0
        for t, s in real_holdings.items():
            if t in price_matrix.columns and pd.notna(price_matrix.loc[current_date, t]):
                real_portfolio_value_usd += s * price_matrix.loc[current_date, t]

        # คำนวณมูลค่าพอร์ตเงาตอนสิ้นวัน
        current_spy_price = price_matrix.loc[current_date, 'SPY']
        current_qqq_price = price_matrix.loc[current_date, 'QQQ']
        shadow_spy_val_usd = shadow_spy_shares * current_spy_price
        shadow_qqq_val_usd = shadow_qqq_shares * current_qqq_price

        # คำนวณมูลค่าในหน่วยเงินบาท (THB)
        current_fx = fx_series.loc[current_date]
        real_val_thb = real_portfolio_value_usd * current_fx
        shadow_spy_val_thb = shadow_spy_val_usd * current_fx
        shadow_qqq_val_thb = shadow_qqq_val_usd * current_fx

        prev_date = current_date

        # บันทึกแถวผลลัพธ์ประจำวันนี้ (รวมค่า NAV สำหรับวัดความเสี่ยงจริง)
        daily_records.append((
            current_date,
            round(total_invested_usd, 2),
            round(real_portfolio_value_usd, 2),
            round(shadow_spy_val_usd, 2),
            round(shadow_qqq_val_usd, 2),
            round(real_val_thb, 2),
            round(shadow_spy_val_thb, 2),
            round(shadow_qqq_val_thb, 2),
            round(current_fx, 4),
            round(real_nav, 4),
            round(shadow_spy_nav, 4),
            round(shadow_qqq_nav, 4)
        ))

    # 7. บันทึกผลลัพธ์ทั้งหมดลงตาราง portfolio_daily
    cursor = conn.cursor()
    cursor.executemany("""
    INSERT OR REPLACE INTO portfolio_daily (
        trade_date,
        total_invested_usd,
        real_portfolio_value_usd,
        shadow_spy_value_usd,
        shadow_qqq_value_usd,
        real_portfolio_value_thb,
        shadow_spy_value_thb,
        shadow_qqq_value_thb,
        fx_rate,
        real_nav,
        shadow_spy_nav,
        shadow_qqq_nav
    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, daily_records)

    conn.commit()
    conn.close()
    print(f"[SUCCESS] Calculated daily portfolio for {len(daily_records)} days!")
    print("--- TRANSFORM PROCESS COMPLETED ---")

if __name__ == "__main__":
    calculate_daily_portfolio()
