import sqlite3
import pandas as pd
from database import get_connection, DB_NAME
from transform import get_split_adjusted_trades

def review_decisions(conn):
    """
    1. ทบทวนการตัดสินใจซื้อแต่ละครั้งเมื่อผ่านไป 1, 3, 6 เดือน เทียบกับ SPY
    """
    print("\n--- 1. DECISION REVIEW & REASON WIN RATE ---")
    trades_df = get_split_adjusted_trades(conn)
    trades_df = trades_df[trades_df['action'] == 'BUY'].sort_values('trade_date')
    prices_raw = pd.read_sql_query("SELECT trade_date, ticker, adj_close FROM prices", conn)
    
    # Pivot ตารางราคาหุ้นและเติมวันหยุดด้วย ffill
    full_dates = pd.date_range(start=prices_raw['trade_date'].min(), end=prices_raw['trade_date'].max(), freq='D').strftime('%Y-%m-%d')
    price_matrix = prices_raw.pivot(index='trade_date', columns='ticker', values='adj_close').reindex(full_dates).ffill().bfill()

    latest_date = pd.to_datetime(price_matrix.index.max())
    
    review_records = []
    
    for _, trade in trades_df.iterrows():
        t_id = trade['id']
        t_date_str = trade['trade_date']
        t_date = pd.to_datetime(t_date_str)
        ticker = trade['ticker']
        reason = trade['reason_category'] or 'Uncategorized'
        
        # ราคาตั้งต้นวันซื้อ
        stock_p0 = price_matrix.loc[t_date_str, ticker]
        spy_p0 = price_matrix.loc[t_date_str, 'SPY']
        
        row_res = {
            'trade_id': t_id,
            'trade_date': t_date_str,
            'ticker': ticker,
            'reason_category': reason
        }
        
        for months in [1, 3, 6]:
            future_date = t_date + pd.DateOffset(months=months)
            future_date_str = future_date.strftime('%Y-%m-%d')
            
            if future_date > latest_date:
                # ยังไม่ครบกำหนดเวลา
                row_res[f'return_{months}m'] = None
                row_res[f'spy_{months}m'] = None
                row_res[f'beat_{months}m'] = None
            else:
                stock_p_future = price_matrix.loc[future_date_str, ticker]
                spy_p_future = price_matrix.loc[future_date_str, 'SPY']
                
                stock_ret = (stock_p_future - stock_p0) / stock_p0
                spy_ret = (spy_p_future - spy_p0) / spy_p0
                beat = 1 if stock_ret > spy_ret else 0
                
                row_res[f'return_{months}m'] = round(stock_ret * 100, 2)
                row_res[f'spy_{months}m'] = round(spy_ret * 100, 2)
                row_res[f'beat_{months}m'] = beat
                
        review_records.append(row_res)
        
    df_reviews = pd.DataFrame(review_records)
    
    # บันทึกผลลัพธ์ลง SQLite
    cursor = conn.cursor()
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS trade_reviews (
        trade_id INTEGER PRIMARY KEY,
        trade_date TEXT,
        ticker TEXT,
        reason_category TEXT,
        return_1m REAL,
        spy_1m REAL,
        beat_1m INTEGER,
        return_3m REAL,
        spy_3m REAL,
        beat_3m INTEGER,
        return_6m REAL,
        spy_6m REAL,
        beat_6m INTEGER
    );
    """)
    cursor.execute("DELETE FROM trade_reviews")
    
    for r in review_records:
        cursor.execute("""
        INSERT INTO trade_reviews VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            r['trade_id'], r['trade_date'], r['ticker'], r['reason_category'],
            r['return_1m'], r['spy_1m'], r['beat_1m'],
            r['return_3m'], r['spy_3m'], r['beat_3m'],
            r['return_6m'], r['spy_6m'], r['beat_6m']
        ))
    conn.commit()

    # สรุปอัตราชนะ (Win Rate) ตามหมวดหมู่เหตุผล
    summary = df_reviews.groupby('reason_category').agg(
        total_trades=('trade_id', 'count'),
        win_rate_1m=('beat_1m', lambda x: f"{round(x.dropna().mean() * 100, 1)}%" if x.dropna().count() > 0 else "N/A"),
        win_rate_3m=('beat_3m', lambda x: f"{round(x.dropna().mean() * 100, 1)}%" if x.dropna().count() > 0 else "N/A"),
        win_rate_6m=('beat_6m', lambda x: f"{round(x.dropna().mean() * 100, 1)}%" if x.dropna().count() > 0 else "N/A")
    ).reset_index()
    
    print(summary.to_string(index=False))
    return summary

def calculate_stock_attribution(conn):
    """
    2. วิเคราะห์กำไรขาดทุนรายหุ้น (Attribution) ตัวไหนพาพอร์ตชนะหรือแพ้
    """
    print("\n--- 2. STOCK ATTRIBUTION (HERO VS LAGGARD) ---")
    trades_df = get_split_adjusted_trades(conn)
    prices_raw = pd.read_sql_query("SELECT trade_date, ticker, adj_close FROM prices", conn)
    
    # หาราคาปิดล่าสุดของแต่ละหุ้น
    latest_prices = prices_raw.sort_values('trade_date').groupby('ticker').last()['adj_close']
    
    attribution = []
    for ticker, group in trades_df.groupby('ticker'):
        total_invested = 0.0
        shares_held = 0.0
        realized_cash = 0.0
        
        for _, trade in group.iterrows():
            action = trade['action'].upper()
            s = float(trade['shares'])
            p = float(trade['price_per_share'])
            fee = float(trade['fee'])
            
            if action == 'BUY':
                shares_held += s
                total_invested += (s * p) + fee
            elif action == 'SELL':
                shares_held -= s
                realized_cash += (s * p) - fee
                
        current_price = latest_prices.get(ticker, 0.0)
        current_val = shares_held * current_price
        total_pnl = (current_val + realized_cash) - total_invested
        ret_pct = (total_pnl / total_invested * 100) if total_invested > 0 else 0.0
        
        attribution.append({
            'ticker': ticker,
            'shares_held': round(shares_held, 4),
            'latest_price_usd': round(current_price, 2),
            'total_invested_usd': round(total_invested, 2),
            'current_value_usd': round(current_val, 2),
            'pnl_usd': round(total_pnl, 2),
            'return_pct': round(ret_pct, 2)
        })
        
    df_attr = pd.DataFrame(attribution).sort_values(by='pnl_usd', ascending=False)
    
    # บันทึกผลลัพธ์ลง SQLite (สร้างตารางใหม่พร้อมคอลัมน์ latest_price_usd)
    cursor = conn.cursor()
    cursor.execute("DROP TABLE IF EXISTS stock_attribution")
    cursor.execute("""
    CREATE TABLE stock_attribution (
        ticker TEXT PRIMARY KEY,
        shares_held REAL,
        latest_price_usd REAL,
        total_invested_usd REAL,
        current_value_usd REAL,
        pnl_usd REAL,
        return_pct REAL
    );
    """)
    for _, row in df_attr.iterrows():
        cursor.execute("INSERT INTO stock_attribution VALUES (?, ?, ?, ?, ?, ?, ?)", (
            row['ticker'], row['shares_held'], row['latest_price_usd'],
            row['total_invested_usd'], row['current_value_usd'],
            row['pnl_usd'], row['return_pct']
        ))
    conn.commit()
    
    print(df_attr.to_string(index=False))
    return df_attr

def calculate_max_drawdown(conn):
    """
    3. คำนวณ Max Drawdown (MDD) พอร์ตจริง vs SPY vs QQQ
    """
    print("\n--- 3. MAX DRAWDOWN COMPARISON ---")
    daily_df = pd.read_sql_query("SELECT trade_date, real_portfolio_value_usd, shadow_spy_value_usd, shadow_qqq_value_usd FROM portfolio_daily ORDER BY trade_date ASC", conn)
    daily_df = daily_df.set_index('trade_date')
    
    results = {}
    for col, label in [
        ('real_portfolio_value_usd', 'Real Portfolio'),
        ('shadow_spy_value_usd', 'Shadow SPY'),
        ('shadow_qqq_value_usd', 'Shadow QQQ')
    ]:
        series = daily_df[col]
        # จุดสูงสุดสะสม
        peak = series.cummax()
        # เปอร์เซ็นต์การดิ่งลงจากจุดสูงสุด
        drawdown = (series - peak) / peak
        # การดิ่งลงลึกที่สุด
        mdd = drawdown.min() * 100
        results[label] = round(mdd, 2)
        
    df_mdd = pd.DataFrame(list(results.items()), columns=['Portfolio', 'Max Drawdown (%)'])
    print(df_mdd.to_string(index=False))
    return df_mdd

def run_analytics(db_name=DB_NAME):
    conn = get_connection(db_name)
    review_decisions(conn)
    calculate_stock_attribution(conn)
    calculate_max_drawdown(conn)
    conn.close()

if __name__ == "__main__":
    run_analytics()
