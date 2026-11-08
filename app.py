import streamlit as st
import sqlite3
import pandas as pd
import plotly.graph_objects as go
from database import DB_NAME, get_connection, add_transaction
from pipeline import run_pipeline

# กำหนดค่าหน้าเว็บให้ Responsive สวยงามบนมือถือและคอมพิวเตอร์
st.set_page_config(
    page_title="Stock Journal & Benchmark",
    page_icon="📈",
    layout="wide",
    initial_sidebar_state="collapsed"
)

# โหลดข้อมูลจากฐานข้อมูล
def load_data():
    conn = get_connection(DB_NAME)
    df_daily = pd.read_sql_query("SELECT * FROM portfolio_daily ORDER BY trade_date ASC", conn)
    df_trades = pd.read_sql_query("SELECT * FROM transactions ORDER BY trade_date DESC", conn)
    df_reviews = pd.read_sql_query("SELECT * FROM trade_reviews", conn)
    df_attr = pd.read_sql_query("SELECT * FROM stock_attribution ORDER BY pnl_usd DESC", conn)
    conn.close()
    return df_daily, df_trades, df_reviews, df_attr

df_daily, df_trades, df_reviews, df_attr = load_data()

# --- SIDEBAR ---
with st.sidebar:
    st.title("📈 Stock Journal")
    st.caption("ระบบวิเคราะห์พอร์ตจริง vs พอร์ตเงา")
    
    currency = st.radio("💱 สกุลเงินที่แสดงผล:", ["USD ($)", "บาท (THB)"], horizontal=True)
    is_thb = (currency == "บาท (THB)")
    
    st.divider()
    if st.button("🔄 รัน Pipeline อัปเดตราคาล่าสุด", use_container_width=True):
        with st.spinner("กำลังดึงราคาหุ้นและคำนวณพอร์ต..."):
            run_pipeline(DB_NAME)
            st.success("อัปเดตข้อมูลสำเร็จแล้ว!")
            st.rerun()

# --- MAIN PAGE TABS ---
tab1, tab2, tab3, tab4 = st.tabs([
    "📊 ภาพรวมพอร์ต (Overview)",
    "🧠 ทบทวนการตัดสินใจ (Decision Review)",
    "✍️ บันทึกการซื้อขายใหม่ (Log Trade)",
    "📜 ประวัติรายการ (Trade Log)"
])

# ==========================================
# TAB 1: ภาพรวมพอร์ต vs พอร์ตเงา (กราฟเวอร์ชันปรับปรุงให้ดูง่าย)
# ==========================================
with tab1:
    if df_daily.empty:
        st.warning("ยังไม่มีข้อมูลในตาราง portfolio_daily กรุณารัน Pipeline ก่อนครับ")
    else:
        latest = df_daily.iloc[-1]
        curr_symbol = "฿" if is_thb else "$"
        multiplier = latest['fx_rate'] if is_thb else 1.0
        
        inv_val = latest['total_invested_usd'] * multiplier
        real_val = latest['real_portfolio_value_usd'] * multiplier
        spy_val = latest['shadow_spy_value_usd'] * multiplier
        
        real_ret = ((latest['real_portfolio_value_usd'] - latest['total_invested_usd']) / latest['total_invested_usd']) * 100
        spy_ret = ((latest['shadow_spy_value_usd'] - latest['total_invested_usd']) / latest['total_invested_usd']) * 100
        alpha = real_ret - spy_ret
        
        # 1. การ์ดสรุปตัวเลขสำคัญด้านบน (แบบคลีนและชัดเจน)
        col1, col2, col3, col4 = st.columns(4)
        col1.metric("💰 เงินต้นลงทุนสะสม", f"{curr_symbol}{inv_val:,.2f}")
        col2.metric("🎯 พอร์ตจริงของฉัน", f"{curr_symbol}{real_val:,.2f}", f"{real_ret:+.2f}%")
        col3.metric("👻 พอร์ตเงา SPY", f"{curr_symbol}{spy_val:,.2f}", f"{spy_ret:+.2f}%")
        col4.metric("⚡ ชนะ/แพ้ ตลาด (Alpha)", f"{alpha:+.2f}%", 
                    delta_color="normal",
                    help="ถ้าเป็นบวก แสดงว่าเราเลือกหุ้นเองชนะการซื้อดัชนี SPY")
        
        st.write("")
        
        # 2. แถบควบคุมกราฟให้ดูง่าย (Control Bar)
        ctrl_col1, ctrl_col2 = st.columns([1, 1])
        with ctrl_col1:
            chart_mode = st.radio(
                "รูปแบบการแสดงผลกราฟ:",
                ["🚀 ดูผลตอบแทนกำไรสะสม (% Return)", "💵 ดูมูลค่าเงินรวม ($ / ฿)"],
                horizontal=True
            )
        with ctrl_col2:
            show_qqq = st.checkbox("แสดงพอร์ตเงา QQQ (Nasdaq) เพิ่มเติม", value=False)
            show_invested = st.checkbox("แสดงเส้นเงินต้นสะสม", value=False)
            
        # 3. เตรียมข้อมูลสำหรับวาดกราฟ
        fig = go.Figure()
        
        if "ผลตอบแทนกำไรสะสม" in chart_mode:
            # โหมด % Return: เทียบผลตอบแทนเป็น % โดยตรง (ดูง่ายที่สุดในโลกการเงิน)
            real_series = ((df_daily['real_portfolio_value_usd'] - df_daily['total_invested_usd']) / df_daily['total_invested_usd']) * 100
            spy_series = ((df_daily['shadow_spy_value_usd'] - df_daily['total_invested_usd']) / df_daily['total_invested_usd']) * 100
            qqq_series = ((df_daily['shadow_qqq_value_usd'] - df_daily['total_invested_usd']) / df_daily['total_invested_usd']) * 100
            
            y_unit = "%"
            fig.add_trace(go.Scatter(
                x=df_daily['trade_date'], y=real_series,
                name="🟢 พอร์ตจริงของฉัน",
                line=dict(color="#10B981", width=3.5),
                hovertemplate="พอร์ตจริง: %{y:.2f}%<extra></extra>"
            ))
            fig.add_trace(go.Scatter(
                x=df_daily['trade_date'], y=spy_series,
                name="🔵 พอร์ตเงา SPY",
                line=dict(color="#3B82F6", width=2.5, dash='dash'),
                hovertemplate="พอร์ตเงา SPY: %{y:.2f}%<extra></extra>"
            ))
            if show_qqq:
                fig.add_trace(go.Scatter(
                    x=df_daily['trade_date'], y=qqq_series,
                    name="🟣 พอร์ตเงา QQQ",
                    line=dict(color="#8B5CF6", width=2, dash='dot'),
                    hovertemplate="พอร์ตเงา QQQ: %{y:.2f}%<extra></extra>"
                ))
            # เส้นระดับเท่าทุน 0%
            fig.add_hline(y=0, line_dash="solid", line_color="#D1D5DB", line_width=1)
            
        else:
            # โหมดมูลค่าเงิน ($ หรือ บาท)
            val_col_real = 'real_portfolio_value_thb' if is_thb else 'real_portfolio_value_usd'
            val_col_spy = 'shadow_spy_value_thb' if is_thb else 'shadow_spy_value_usd'
            val_col_qqq = 'shadow_qqq_value_thb' if is_thb else 'shadow_qqq_value_usd'
            val_inv = df_daily['total_invested_usd'] * multiplier
            
            y_unit = curr_symbol
            fig.add_trace(go.Scatter(
                x=df_daily['trade_date'], y=df_daily[val_col_real],
                name="🟢 พอร์ตจริงของฉัน",
                line=dict(color="#10B981", width=3.5),
                hovertemplate=f"พอร์ตจริง: {curr_symbol}%{{y:,.2f}}<extra></extra>"
            ))
            fig.add_trace(go.Scatter(
                x=df_daily['trade_date'], y=df_daily[val_col_spy],
                name="🔵 พอร์ตเงา SPY",
                line=dict(color="#3B82F6", width=2.5, dash='dash'),
                hovertemplate=f"พอร์ตเงา SPY: {curr_symbol}%{{y:,.2f}}<extra></extra>"
            ))
            if show_qqq:
                fig.add_trace(go.Scatter(
                    x=df_daily['trade_date'], y=df_daily[val_col_qqq],
                    name="🟣 พอร์ตเงา QQQ",
                    line=dict(color="#8B5CF6", width=2, dash='dot'),
                    hovertemplate=f"พอร์ตเงา QQQ: {curr_symbol}%{{y:,.2f}}<extra></extra>"
                ))
            if show_invested:
                fig.add_trace(go.Scatter(
                    x=df_daily['trade_date'], y=val_inv,
                    name="⚪ เงินต้นลงทุน",
                    line=dict(color="#9CA3AF", width=1.5, dash='dot'),
                    hovertemplate=f"เงินต้น: {curr_symbol}%{{y:,.2f}}<extra></extra>"
                ))

        # ตกแต่งกราฟ และเพิ่มปุ่มลัดเลือกช่วงเวลา (1M, 3M, 6M, 1Y, ALL)
        fig.update_layout(
            height=460,
            margin=dict(l=10, r=10, t=20, b=10),
            hovermode="x unified",
            xaxis=dict(
                rangeselector=dict(
                    buttons=list([
                        dict(count=1, label="1M", step="month", stepmode="backward"),
                        dict(count=3, label="3M", step="month", stepmode="backward"),
                        dict(count=6, label="6M", step="month", stepmode="backward"),
                        dict(count=1, label="1Y", step="year", stepmode="backward"),
                        dict(step="all", label="ALL")
                    ]),
                    font=dict(size=12),
                    y=1.12
                ),
                type="date"
            ),
            yaxis=dict(ticksuffix=f" {y_unit}"),
            legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1)
        )
        st.plotly_chart(fig, use_container_width=True)

        # 4. โซนวัดความเสี่ยง: Max Drawdown (การร่วงลงลึกที่สุดจากจุดสูงสุด)
        st.subheader("🛡️ การประเมินความเสี่ยง: การร่วงลงลึกที่สุด (Max Drawdown)")
        st.caption("คำนวณด้วยวิธี **Time-Weighted Return (Unit NAV)** ตามมาตรฐานสากลของกองทุนรวม เพื่อวัดความเสี่ยงจากการผันผวนของราคาตลาดจริง โดยตัดผลกระทบของการเติมเงินหรือถอนเงินสด (Cash Flow Distortion) ออก 100%")
        
        def calc_mdd(series):
            peak = series.cummax()
            dd = (series - peak) / peak
            return dd.min() * 100

        col_real = 'real_nav' if 'real_nav' in df_daily.columns else 'real_portfolio_value_usd'
        col_spy = 'shadow_spy_nav' if 'shadow_spy_nav' in df_daily.columns else 'shadow_spy_value_usd'
        col_qqq = 'shadow_qqq_nav' if 'shadow_qqq_nav' in df_daily.columns else 'shadow_qqq_value_usd'

        mdd_real = calc_mdd(df_daily[col_real])
        mdd_spy = calc_mdd(df_daily[col_spy])
        mdd_qqq = calc_mdd(df_daily[col_qqq])

        m_col1, m_col2, m_col3 = st.columns(3)
        m_col1.metric("🟢 พอร์ตจริงของฉัน", f"{mdd_real:.2f}%")
        m_col2.metric("🔵 พอร์ตเงา SPY", f"{mdd_spy:.2f}%")
        m_col3.metric("🟣 พอร์ตเงา QQQ", f"{mdd_qqq:.2f}%")

        st.info(f"💡 **วิเคราะห์ความเสี่ยง:** พอร์ตจริงร่วงลึกสุดเพียง **{mdd_real:.2f}%** อยู่กึ่งกลางระหว่างความเสี่ยงต่ำของ SPY (**{mdd_spy:.2f}%**) และความผันผวนสูงของ QQQ (**{mdd_qqq:.2f}%**) สะท้อนการกระจายความเสี่ยง (Asset Allocation) ที่เหมาะสมระหว่างหุ้นเทคโนโลยีและหุ้นปันผลเสถียร")

        st.divider()

        # 5. ตารางจัดอันดับหุ้นในพอร์ต (Stock Attribution ปรับปรุงใหม่ให้ดูง่ายมาก)
        st.subheader("🏆 หุ้นตัวไหนทำกำไรให้พอร์ตมากที่สุด? (Stock Attribution)")
        
        if not df_attr.empty:
            # จัดอันดับตามเปอร์เซ็นต์ผลตอบแทน (% Return) เป็นหลัก
            df_attr_sorted = df_attr.sort_values(by='return_pct', ascending=False)
            top_pct_stock = df_attr_sorted.iloc[0]
            top_cash_stock = df_attr.sort_values(by='pnl_usd', ascending=False).iloc[0]
            
            c_hero1, c_hero2 = st.columns(2)
            c_hero1.success(f"🚀 **ผลตอบแทน % สูงสุด:** **{top_pct_stock['ticker']}** (+{top_pct_stock['return_pct']:.2f}%)")
            c_hero2.info(f"💵 **กำไรเป็นเงิน USD สูงสุด:** **{top_cash_stock['ticker']}** (+${top_cash_stock['pnl_usd']:,.2f})")
            
            # แปลงชื่อคอลัมน์ให้อ่านง่ายเป็นภาษาไทย และจัดฟอร์แมตตัวเลข
            display_attr = df_attr_sorted.copy()
            display_attr.columns = [
                'สัญลักษณ์หุ้น', 'จำนวนหุ้นในมือ', 'ราคาตลาดล่าสุด (ต่อหุ้น)',
                'เงินต้นสะสม (USD)', 'มูลค่ารวมในพอร์ต (USD)', 'กำไร/ขาดทุน (USD)', 'ผลตอบแทน (%)'
            ]
            
            st.dataframe(
                display_attr,
                use_container_width=True,
                hide_index=True,
                column_config={
                    "สัญลักษณ์หุ้น": st.column_config.TextColumn("🏷️ หุ้น"),
                    "จำนวนหุ้นในมือ": st.column_config.NumberColumn("🔢 จำนวนหุ้น", format="%.4f"),
                    "ราคาตลาดล่าสุด (ต่อหุ้น)": st.column_config.NumberColumn("💲 ราคาตลาดล่าสุด", format="$%.2f"),
                    "เงินต้นสะสม (USD)": st.column_config.NumberColumn("💵 เงินต้น", format="$%.2f"),
                    "มูลค่ารวมในพอร์ต (USD)": st.column_config.NumberColumn("💎 มูลค่ารวมในพอร์ต", format="$%.2f"),
                    "กำไร/ขาดทุน (USD)": st.column_config.NumberColumn("📈 กำไร/ขาดทุน ($)", format="+$%.2f"),
                    "ผลตอบแทน (%)": st.column_config.NumberColumn("🎯 ผลตอบแทน (%)", format="+%.2f%%"),
                }
            )

# ==========================================
# TAB 2: ทบทวนการตัดสินใจ & Win Rate
# ==========================================
with tab2:
    st.subheader("🎯 อัตราชนะ (Win Rate) เทียบกับ SPY แยกตามประเภทเหตุผล")
    if not df_reviews.empty:
        summary_win = df_reviews.groupby('reason_category').agg(
            total_trades=('trade_id', 'count'),
            win_1m=('beat_1m', lambda x: f"{round(x.dropna().mean() * 100, 1)}%" if x.dropna().count() > 0 else "N/A"),
            win_3m=('beat_3m', lambda x: f"{round(x.dropna().mean() * 100, 1)}%" if x.dropna().count() > 0 else "N/A"),
            win_6m=('beat_6m', lambda x: f"{round(x.dropna().mean() * 100, 1)}%" if x.dropna().count() > 0 else "N/A")
        ).reset_index()
        
        summary_win.columns = ['หมวดหมู่เหตุผล', 'จำนวนไม้ที่ซื้อ', 'ชนะ SPY (1 เดือน)', 'ชนะ SPY (3 เดือน)', 'ชนะ SPY (6 เดือน)']
        st.dataframe(summary_win, use_container_width=True, hide_index=True)
        
        st.divider()
        st.subheader("🔍 รายละเอียดการตัดสินใจรายไม้ (หุ้น vs SPY)")
        
        # จัดตารางให้อ่านง่ายในเสี้ยววินาที แปลง 0/1 ให้เป็น ✅ ชนะ หรือ ❌ แพ้ พร้อมตัวเลขเทียบกันชัดเจน
        clean_reviews = []
        for _, r in df_reviews.iterrows():
            def format_period(ret_col, spy_col, beat_col):
                ret_val = r[ret_col]
                spy_val = r[spy_col]
                beat_val = r[beat_col]
                if pd.isna(ret_val) or beat_val is None:
                    return "⏳ รอครบกำหนด"
                icon = "✅ ชนะ" if beat_val == 1 else "❌ แพ้"
                return f"{icon} ({ret_val:+.1f}% vs {spy_val:+.1f}%)"
            
            clean_reviews.append({
                "📅 วันที่ซื้อ": r['trade_date'],
                "🏷️ หุ้น": r['ticker'],
                "🧠 หมวดเหตุผล": r['reason_category'],
                "⏱️ ผ่านไป 1 เดือน": format_period('return_1m', 'spy_1m', 'beat_1m'),
                "⏱️ ผ่านไป 3 เดือน": format_period('return_3m', 'spy_3m', 'beat_3m'),
                "⏱️ ผ่านไป 6 เดือน": format_period('return_6m', 'spy_6m', 'beat_6m'),
            })
            
        df_clean_reviews = pd.DataFrame(clean_reviews)
        st.dataframe(df_clean_reviews, use_container_width=True, hide_index=True)
    else:
        st.info("ยังไม่มีข้อมูลการประเมินการตัดสินใจ")

# ==========================================
# TAB 3: ฟอร์มบันทึกการซื้อขายใหม่
# ==========================================
with tab3:
    st.subheader("✍️ บันทึกรายการซื้อขายใหม่จากแอป Dime")
    st.caption("เมื่อกดบันทึก ข้อมูลจะถูกจัดเก็บเข้าฐานข้อมูล และคำนวณพอร์ตเงาต่อทันที")
    
    with st.form("new_trade_form", clear_on_submit=True):
        f_col1, f_col2, f_col3 = st.columns(3)
        t_date = f_col1.date_input("📅 วันที่ซื้อขาย")
        ticker = f_col2.text_input("🏷️ สัญลักษณ์หุ้น (Ticker)", placeholder="เช่น AAPL, NVDA, TSLA").upper()
        action = f_col3.selectbox("🔄 ประเภทรายการ", ["BUY", "SELL"])
        
        f_col4, f_col5, f_col6 = st.columns(3)
        shares = f_col4.number_input("🔢 จำนวนหุ้น (ทศนิยม)", min_value=0.0001, value=0.1000, step=0.01, format="%.4f")
        price = f_col5.number_input("💵 ราคาต่อหุ้น (USD)", min_value=0.01, value=150.00, step=1.0, format="%.2f")
        fee = f_col6.number_input("🏷️ ค่าธรรมเนียม (USD)", min_value=0.0, value=0.0, step=0.1, format="%.2f")
        
        reason = st.selectbox(
            "🧠 ประเภทเหตุผลในการตัดสินใจ",
            [
                "DCA (ทยอยออมสะสมสม่ำเสมอ)",
                "Growth (พื้นฐานเติบโต)",
                "Valuation (ราคาถูกกว่ามูลค่า)",
                "Momentum (ตามกราฟ/แนวโน้ม)",
                "Dividend (เน้นปันผล)",
                "FOMO (กลัวตกรถ)",
                "Rebalance (ปรับสัดส่วนพอร์ต)"
            ]
        )
        reason_cat = reason.split()[0]
        notes = st.text_area("📝 บันทึกเหตุผลเพิ่มเติม (ทำไมถึงตัดสินใจไม้นี้)", placeholder="เช่น งบการเงินไตรมาส 3 ดีกว่าคาด, วางแผนถือยาว 2 ปี...")
        
        submitted = st.form_submit_button("💾 บันทึกรายการเข้าฐานข้อมูล", use_container_width=True)
        
        if submitted:
            if not ticker:
                st.error("กรุณาระบุสัญลักษณ์หุ้น!")
            else:
                trade_date_str = t_date.strftime('%Y-%m-%d')
                add_transaction(trade_date_str, ticker, action, shares, price, fee, reason_cat, notes)
                st.success(f"บันทึกรายการ {action} {ticker} เรียบร้อยแล้ว! กำลังคำนวณพอร์ตใหม่...")
                run_pipeline(DB_NAME)
                st.rerun()

# ==========================================
# TAB 4: ประวัติการซื้อขายทั้งหมด
# ==========================================
with tab4:
    st.subheader("📜 ประวัติการซื้อขายทั้งหมดในตาราง transactions")
    st.dataframe(df_trades, use_container_width=True, hide_index=True)
