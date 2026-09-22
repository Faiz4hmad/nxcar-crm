import streamlit as st
import pandas as pd
import sqlite3
import os
import re
import urllib.parse
from datetime import datetime, timedelta
from streamlit_autorefresh import st_autorefresh
from db import init_db, sync_from_sheets, get_db_connection

st.set_page_config(page_title="Personal LMS", layout="wide", page_icon="🚙", initial_sidebar_state="collapsed")
os.makedirs("photos", exist_ok=True) 

# --- DATABASE SETUP ---
init_db()

def upgrade_db_silently():
    conn = get_db_connection()
    c = conn.cursor()
    try: c.execute("ALTER TABLE leads ADD COLUMN followup_reason TEXT")
    except: pass 
    try: c.execute("ALTER TABLE leads ADD COLUMN remark_history TEXT")
    except: pass
    try: c.execute("ALTER TABLE leads ADD COLUMN expectation_history TEXT")
    except: pass
    try: c.execute("ALTER TABLE leads ADD COLUMN ra_name TEXT DEFAULT 'Unassigned'")
    except: pass
    try:
        c.execute('''CREATE TABLE IF NOT EXISTS lead_dealer_offers (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        vehicle_no TEXT,
                        dealer_name TEXT,
                        offer_price INTEGER,
                        offer_date TIMESTAMP
                    )''')
    except: pass
    conn.commit()
    conn.close()

upgrade_db_silently()

# --- SECURITY SYSTEM ---
if "authenticated" not in st.session_state:
    st.session_state.authenticated = False
    st.session_state.current_user = "Unknown"

if not st.session_state.authenticated:
    col1, col2, col3 = st.columns([1, 1, 1])
    with col2:
        st.markdown("<h1 style='color: #00B4D8;'>🔒 Personal CRM Login</h1>", unsafe_allow_html=True)
        with st.form("login_form"):
            username = st.text_input("Username")
            password = st.text_input("Password", type="password")
            if st.form_submit_button("Log In", use_container_width=True):
                user_email = username.strip().lower()
                user_pass = password.strip()
                
                if user_email == "faizahmad@nxcar.in" and user_pass == "9670922123":
                    st.session_state.authenticated = True
                    st.session_state.current_user = "Faiz"
                    st.rerun()
                elif user_email == "sudhir.sharma@nxcar.in" and user_pass == "sudhir@123":
                    st.session_state.authenticated = True
                    st.session_state.current_user = "Sudhir"
                    st.rerun()
                else:
                    st.error("Incorrect credentials.")
    st.stop()

# --- HELPER FUNCTIONS ---
def execute_query(query, params=()):
    conn = get_db_connection()
    c = conn.cursor()
    c.execute(query, params)
    conn.commit()
    conn.close()

def load_all_data():
    conn = get_db_connection()
    df = pd.read_sql_query("SELECT * FROM leads ORDER BY system_date_added DESC", conn)
    conn.close()
    return df

def get_dealer_prefs():
    conn = get_db_connection()
    df = pd.read_sql_query("SELECT * FROM dealer_preferences", conn)
    conn.close()
    return df

def get_vehicle_bids(vehicle_no):
    conn = get_db_connection()
    try:
        df = pd.read_sql_query("SELECT * FROM lead_dealer_offers WHERE vehicle_no=?", conn, params=(vehicle_no,))
    except:
        df = pd.DataFrame()
    conn.close()
    return df
def get_dealer_bids():
    conn = get_db_connection()
    df = pd.read_sql_query("SELECT * FROM dealer_offers", conn)
    conn.close()
    return df

def clean_price(price_str):
    cleaned = re.sub(r'\D', '', str(price_str))
    return int(cleaned) if cleaned else 0

def calculate_expiry(date_str):
    try:
        # Check if the date is missing
        if pd.isna(date_str) or not str(date_str).strip():
            return 5
            
        # Safely convert to a Pandas datetime object
        added = pd.to_datetime(str(date_str).strip(), errors='coerce')
        if pd.isna(added):
            return 5
            
        # Strip away any hidden timezones that break the math
        if added.tz is not None:
            added = added.tz_localize(None)
            
        # Normalize compares pure calendar dates (ignores the exact hour/minute)
        now = pd.Timestamp.now().normalize()
        added = added.normalize()
        
        days_passed = (now - added).days
        remaining = int(5 - days_passed)
        
        # Ensure it doesn't accidentally return a weird negative number
        return remaining if remaining <= 5 else 5
        
    except:
        return 5

def get_car_age(year_str):
    try:
        return 2026 - int(str(year_str).strip())
    except:
        return "?"

# --- DATA PROCESSING ---
# --- DATA PROCESSING ---
df = load_all_data()

if not df.empty:
    # Filter out deleted leads completely so they vanish from the UI
    df = df[df['calling_status'] != 'Deleted']

if not df.empty:
    clean_phones = df['phone_number'].astype(str).str.replace(r'\.0$', '', regex=True).str.replace(r'\D', '', regex=True)
    df['lead_id'] = clean_phones.str[-6:]
    df['days_left'] = df['system_date_added'].apply(calculate_expiry)
    df['is_duplicate'] = df.duplicated(subset=['vehicle_no'], keep=False) | df.duplicated(subset=['phone_number'], keep=False)
    active_df = df[(df['days_left'] > 0) | (df['calling_status'] == 'Closed')]
    expired_df = df[(df['days_left'] <= 0) & (df['calling_status'] != 'Closed')]
else:
    active_df = pd.DataFrame()
    expired_df = pd.DataFrame()

# --- SIDEBAR & SETTINGS ---
with st.sidebar:
    st.header("⚙️ Preferences")
    
    if 'last_sync_time' not in st.session_state:
        st.session_state.last_sync_time = "Not Synced Yet"
        
    auto_sync = st.selectbox("🔄 Auto-Sync", ["Off", "1 Minute", "5 Minutes", "30 Minutes"], index=3)
    
    if auto_sync != "Off":
        st.caption(f"Last Background Sync: {st.session_state.last_sync_time}")
    
    st.divider()
    st.header("🎛️ Feature Toggles")
    show_agenda = st.toggle("🌅 Show Morning Agenda", value=True)
    show_matcher = st.toggle("🤝 Smart Dealer Matcher", value=True)
    show_duplicates = st.toggle("⚠️ Catch Duplicates", value=True)
    
    st.divider()
    st.header("📥 Executive Export")
    if not df.empty:
        csv = df.to_csv(index=False).encode('utf-8')
        st.download_button(
            label="📊 Download Full Pipeline (CSV)",
            data=csv,
            file_name=f"Nxcar_Pipeline_{datetime.now().strftime('%Y%m%d')}.csv",
            mime="text/csv",
            use_container_width=True
        )
    else:
        st.write("No data to export.")
        
    st.divider()
    if st.button("🚪 Log Out", use_container_width=True):
        st.session_state.authenticated = False
        st.rerun()

if auto_sync != "Off":
    minutes = int(auto_sync.split()[0])
    st_autorefresh(interval=minutes * 60 * 1000, key="data_sync")
    st.session_state.last_sync_time = datetime.now().strftime("%I:%M %p")

# --- TOP NAVIGATION ---
# --- TOP NAVIGATION ---
col_head, col_sync = st.columns([8, 2])
with col_head:
    # We use HTML here to force the text to be a bold Teal Blue (#00B4D8)
    st.markdown("<h1 style='color: #00ADB5;'>🚙 Personal LMS</h1>", unsafe_allow_html=True)
with col_sync:
    if st.button("⬇️ Manual Sync"):
            with st.spinner("Syncing your specific leads to the cloud..."):
                from db import sync_from_sheets
                
                # Using direct CSV export links so the app can read the data perfectly
                if st.session_state.current_user == "Faiz":
                    target_sheet = "https://docs.google.com/spreadsheets/d/1Z8JOC7mb7SJ0B8zB1c-M3dDAjRyo-aP4_jzyE2JtgOM/export?format=csv&gid=0"
                elif st.session_state.current_user == "Sudhir":
                    target_sheet = "https://docs.google.com/spreadsheets/d/1ljg4W0RCEJp-b5kkCVNiThiuo3EGunteGPe2J_TdpJg/export?format=csv&gid=0"
                else:
                    target_sheet = None
                
                if target_sheet:
                    sync_from_sheets(target_sheet, st.session_state.current_user)
                    st.success(f"Successfully synced {st.session_state.current_user}'s leads!")
                    st.rerun()
                else:
                    st.error("No sheet assigned to this user.")
    st.session_state.last_sync_time = datetime.now().strftime("%I:%M %p")
    st.toast("Database Synced!")

st.divider()
# --- COMPACT PIPELINE METRICS BANNER ---
if not df.empty:
    n_cnt = len(df[df['calling_status'] == 'New'])
    p_cnt = len(df[df['calling_status'] == 'Photos Collected'])
    neg_cnt = len(df[df['calling_status'] == 'Negotiation'])
    c_cnt = len(df[df['calling_status'] == 'Closed'])
    
    st.markdown(
        f"<div style='padding: 10px 15px; background: rgba(255,255,255,0.05); border-radius: 8px; margin-bottom: 15px; text-align: center; font-size: 1.05em;'>"
        f"🆕 New Leads: <b>{n_cnt}</b> &nbsp;&nbsp;&nbsp;|&nbsp;&nbsp;&nbsp; "
        f"📸 Photos: <b>{p_cnt}</b> &nbsp;&nbsp;&nbsp;|&nbsp;&nbsp;&nbsp; "
        f"🗣️ Negotiating: <b>{neg_cnt}</b> &nbsp;&nbsp;&nbsp;|&nbsp;&nbsp;&nbsp; "
        f"🏆 Closed: <b>{c_cnt}</b>"
        f"</div>", 
        unsafe_allow_html=True
    )

# --- MAIN TABS ---
tab_active, tab_expired, tab_crm = st.tabs(["🔥 Active Pipeline", f"📂 Not Converted ({len(expired_df)})", "👥 Dealer CRM & Analytics"])

with tab_active:
    st.write("### 🗂️ View Pipeline By Day")
    
    # 1. CREATE display_df BASED ON THE DAY TAB
    day_filter = st.radio(
        "Filter by Days:",
        ["All Active", "5 Days Left", "4 Days Left", "3 Days Left", "2 Days Left", "1 Day Left", "Closed Deals"],
        horizontal=True,
        label_visibility="collapsed"
    )

    if day_filter == "All Active":
        display_df = active_df
    elif day_filter == "Closed Deals":
        display_df = active_df[active_df['calling_status'] == 'Closed']
    else:
        d_target = int(day_filter.split()[0])
        display_df = active_df[(active_df['days_left'] == d_target) & (active_df['calling_status'] != 'Closed')]

    # 2. FILTER display_df USING THE SEARCH BAR
    search_term = st.text_input("🔍 Search Leads (Car Number, Name, or Phone):", "")
    if search_term:
        display_df = display_df[
            display_df['vehicle_no'].astype(str).str.contains(search_term, case=False, na=False) |
            display_df['seller_name'].astype(str).str.contains(search_term, case=False, na=False) |
            display_df['phone_number'].astype(str).str.contains(search_term, case=False, na=False)
        ]

    # 3. CHECK IF IT IS EMPTY AND DRAW CARDS
    if display_df.empty:
        st.info("No leads found matching this filter or search.")
    else:
        for i in range(0, len(display_df), 2):
            cols = st.columns(2)
            for j in range(2):
                if i + j < len(display_df):
                    row = display_df.iloc[i + j]
                    v_no = str(row['vehicle_no']).strip()
            for j in range(2):
                if i + j < len(display_df):
                    row = display_df.iloc[i + j]
                    v_no = str(row['vehicle_no']).strip()
                    rto_code = v_no[:2].upper() if len(v_no) >= 2 else "NA"
                    car_age = get_car_age(row['year'])
                    
                    seller_ask = clean_price(row['customer_expectation'])
                    prefs = get_dealer_prefs()
                    matches = pd.DataFrame()
                    
                    if show_matcher and not prefs.empty and seller_ask > 0:
                        matches = prefs[
                            (prefs['budget_max'] >= seller_ask) & 
                            (prefs['preferred_fuel'].str.contains(str(row['fuel_type']), case=False, na=False) | (prefs['preferred_fuel'] == 'Any')) &
                            (prefs['preferred_city'].str.contains(rto_code, case=False, na=False) | (prefs['preferred_city'] == 'Any'))
                        ]
                    has_match = not matches.empty
                    
                    with cols[j]:
                        with st.container(border=True):
                            if has_match and show_matcher:
                                st.markdown(f"""
                                    <div style="background-color: #FFF9C4; padding: 4px 8px; border-radius: 4px; border: 1px solid #FBC02D; margin-bottom: 8px;">
                                        <strong style="color: #D84315; font-size: 0.85em;">🌟 {len(matches)} DEALER MATCHES (RTO: {rto_code})</strong>
                                    </div>
                                """, unsafe_allow_html=True)
                            
                            # --- RA OWNERSHIP BADGE ---
                            curr_ra = row.get('ra_name', 'Unassigned')
                            if pd.isna(curr_ra) or curr_ra == "": curr_ra = "Unassigned"
                            badge_color = "#10B981" if curr_ra != "Unassigned" else "#FF5252"
                            
                            st.markdown(f"### 🏎️ {row['make_model']} &nbsp;<span style='background:{badge_color};color:white;padding:3px 10px;border-radius:12px;font-size:0.55em;vertical-align:middle;'>RA: {curr_ra}</span>", unsafe_allow_html=True)
                            
                            raw_phone = re.sub(r'\D', '', str(row['phone_number']))
                            if len(raw_phone) == 10:
                                raw_phone = "91" + raw_phone
                            seller_msg = urllib.parse.quote(f"Hi {row['seller_name']}, this is Faiz from Nxcar regarding your {row['make_model']}.")
                            wa_link = f"https://wa.me/{raw_phone}?text={seller_msg}"
                            
                            st.markdown(f"**🆔 {v_no}** (RTO: {rto_code}) | 👤 **{row['seller_name']}** (📞 {row['phone_number']} | [💬 WhatsApp Seller]({wa_link}))")
                            st.markdown(f"📍 **{row['city']}** | ⏳ Expires: {row['days_left']} Days | Lead ID: `#{row['lead_id']}`")

                            # --- COMPACT SPECS & FINANCIALS ---
                            bids_df = get_vehicle_bids(v_no)
                            max_bid = int(bids_df['offer_price'].max()) if not bids_df.empty else 0
                            price_diff = seller_ask - max_bid if max_bid > 0 else 0
                            
                            # Inline Strike-Through Math
                            ask_display = f"<b>₹{seller_ask:,}</b>"
                            if pd.notna(row.get('expectation_history')) and row.get('expectation_history'):
                                old_prices = re.findall(r'₹(\d+)\s*➡️', row.get('expectation_history'))
                                if old_prices:
                                    seen = set()
                                    ordered_old = [p for p in old_prices if not (p in seen or seen.add(p))]
                                    strike_html = " ".join([f"<s>₹{int(p):,}</s>" for p in ordered_old])
                                    ask_display = f"<span style='color:#FF5252; font-size:0.9em; margin-right: 6px;'>{strike_html}</span><b>₹{seller_ask:,}</b>"

                            # Status or Bid Logic
                            if max_bid > 0:
                                bid_display = f"💵 High Bid: <b>₹{max_bid:,}</b> <span style='color:#10B981; font-size:0.9em; font-weight:bold; margin-left: 6px;'>(Gap: ₹{price_diff:,})</span>"
                            else:
                                bid_display = f"📌 Stage: <span style='color:#00B4D8; font-weight:bold;'>{row['calling_status']}</span>"

                            # Print everything as a single tight block
                            st.markdown(
                                f"<div style='margin-bottom: 12px; line-height: 1.8;'>"
                                f"📅 <b>{row['year']}</b> ({car_age} yrs) &nbsp;&nbsp;|&nbsp;&nbsp; "
                                f"⛽ <b>{row['fuel_type']}</b> &nbsp;&nbsp;|&nbsp;&nbsp; "
                                f"🛣️ <b>{row['km_driven']} km</b> &nbsp;&nbsp;|&nbsp;&nbsp; "
                                f"🔑 <b>{row['ownership']}</b><br/>"
                                f"💰 Ask: {ask_display} &nbsp;&nbsp;|&nbsp;&nbsp; {bid_display}"
                                f"</div>", 
                                unsafe_allow_html=True
                            )

                            if not bids_df.empty:
                                st.markdown("**🤝 Active Dealer Bids:**")
                                for _, bid in bids_df.iterrows():
                                    b_time = datetime.strptime(bid['offer_date'], "%Y-%m-%d %H:%M:%S").strftime("%d %b")
                                    st.markdown(f"<span style='color: #00ADB5; font-weight: bold; font-size: 0.9em;'>- {bid['dealer_name']}: ₹{bid['offer_price']:,}</span> <i style='font-size: 0.8em;'>({b_time})</i>", unsafe_allow_html=True)
                
                            if pd.notna(row['followup_time']) and row['followup_time']:
                                f_time = datetime.strptime(row['followup_time'], "%Y-%m-%d %H:%M:%S")
                                now_time = datetime.now()
                                reason_text = f" [{row['followup_reason']}]" if 'followup_reason' in row and pd.notna(row['followup_reason']) and row['followup_reason'] else ""
                                
                                if f_time > now_time:
                                    diff = f_time - now_time
                                    hrs, remainder = divmod(diff.seconds, 3600)
                                    mins, _ = divmod(remainder, 60)
                                    time_str = f"{diff.days}d {hrs}h {mins}m" if diff.days > 0 else f"{hrs}h {mins}m"
                                    st.markdown(f"<div style='color: #FFC107; font-size: 0.85em; font-weight: bold; margin-bottom: 4px;'>⏰ Follow-up in: {time_str}{reason_text}</div>", unsafe_allow_html=True)
                                else:
                                    st.markdown(f"<div style='color: #FF5252; font-size: 0.85em; font-weight: bold; margin-bottom: 4px;'>🚨 OVERDUE FOLLOW-UP{reason_text}</div>", unsafe_allow_html=True)
                                
                            if row['is_duplicate'] and show_duplicates:
                                st.markdown(f"<div style='color: #FF5252; font-size: 0.85em; font-weight: bold; margin-bottom: 4px;'>⚠️ DUPLICATE FOUND</div>", unsafe_allow_html=True)

                            st.divider()

                            # --- FRONT EDITABLE REMARK BOX ---
                            rc1, rc2 = st.columns([5, 1])
                            new_remark = rc1.text_input("Remarks", value=row.get('final_remarks', '') if pd.notna(row.get('final_remarks')) else '', key=f"f_rem_{v_no}", placeholder="Add a remark...", label_visibility="collapsed")
                            if rc2.button("💾 Save", key=f"save_rem_{v_no}", use_container_width=True):
                                if new_remark != row.get('final_remarks', ''):
                                    now_str = datetime.now().strftime("%d-%b %I:%M %p")
                                    rem_hist = row.get('remark_history', '') if pd.notna(row.get('remark_history', '')) else ""
                                    rem_hist += f"[{now_str}] {new_remark}\n"
                                    execute_query("UPDATE leads SET final_remarks=?, remark_history=?, local_lock=1 WHERE vehicle_no=?", (new_remark, rem_hist, v_no))
                                    st.rerun()

                            # --- COMPACT ACTION BUTTONS ---
                            pop1, pop2, pop3, pop4 = st.columns([1, 1, 1.3, 1])
                            
                            with pop1:
                                with st.popover("✏️ Edit", use_container_width=True):
                                    with st.form(key=f"edit_{v_no}"):
                                        pipeline = ["New", "Photos Collected", "Pitched to Dealers", "Negotiation", "Physical Visit", "Closed", "Lost"]
                                        c_stat = row['calling_status'] if row['calling_status'] in pipeline else "New"
                                        
                                        db_ra = row.get('ra_name', 'Unassigned')
                                        if pd.isna(db_ra) or db_ra not in ["Unassigned", "Faiz", "Sudhir"]:
                                            db_ra = "Unassigned"

                                        u_ra = st.selectbox("Assign RA:", ["Unassigned", "Faiz", "Sudhir"], index=["Unassigned", "Faiz", "Sudhir"].index(db_ra))
                                        u_status = st.selectbox("Status", pipeline, index=pipeline.index(c_stat))
                                        u_exp = st.text_input("Expectation (₹)", value=row['customer_expectation'])
                                        
                                        if st.form_submit_button("Save Edits"):
                                            now_str = datetime.now().strftime("%d-%b %I:%M %p")
                                            
                                            exp_hist = row.get('expectation_history', '') if pd.notna(row.get('expectation_history', '')) else ""
                                            if str(u_exp) != str(row['customer_expectation']):
                                                exp_hist += f"[{now_str}] ₹{row['customer_expectation']} ➡️ ₹{u_exp}\n"
                                            
                                            execute_query('''UPDATE leads SET customer_expectation=?, calling_status=?, 
                                                             expectation_history=?, ra_name=?, local_lock=1 WHERE vehicle_no=?''', 
                                                          (u_exp, u_status, exp_hist, u_ra, v_no))
                                            st.rerun()
                                            
                                    st.divider()
                                    if st.button("🗑️ Delete Lead", key=f"del_{v_no}", use_container_width=True):
                                        execute_query("UPDATE leads SET calling_status='Deleted', local_lock=1 WHERE vehicle_no=?", (v_no,))
                                        st.rerun()
                                            
                            with pop2:
                                with st.popover("⏰ Remind", use_container_width=True):
                                    f_reason = st.selectbox("Reason for Follow-up:", ["Call Back", "Ask for Photos", "Price Negotiation", "Physical Visit", "Other"], key=f"rsn_{v_no}")
                                    rf1, rf2, rf3 = st.columns(3)
                                    if rf1.button("+2H", key=f"2h_{v_no}", use_container_width=True):
                                        new_time = (datetime.now() + timedelta(hours=2)).strftime("%Y-%m-%d %H:%M:%S")
                                        execute_query("UPDATE leads SET followup_time=?, followup_reason=?, local_lock=1 WHERE vehicle_no=?", (new_time, st.session_state[f"rsn_{v_no}"], v_no))
                                        st.rerun()
                                    if rf2.button("+4H", key=f"4h_{v_no}", use_container_width=True):
                                        new_time = (datetime.now() + timedelta(hours=4)).strftime("%Y-%m-%d %H:%M:%S")
                                        execute_query("UPDATE leads SET followup_time=?, followup_reason=?, local_lock=1 WHERE vehicle_no=?", (new_time, st.session_state[f"rsn_{v_no}"], v_no))
                                        st.rerun()
                                    if rf3.button("+24H", key=f"24h_{v_no}", use_container_width=True):
                                        new_time = (datetime.now() + timedelta(hours=24)).strftime("%Y-%m-%d %H:%M:%S")
                                        execute_query("UPDATE leads SET followup_time=?, followup_reason=?, local_lock=1 WHERE vehicle_no=?", (new_time, st.session_state[f"rsn_{v_no}"], v_no))
                                        st.rerun()
                                    
                                    st.divider()
                                    if st.button("✅ Mark Done / Cancel", key=f"cancel_{v_no}", use_container_width=True):
                                        execute_query("UPDATE leads SET followup_time=NULL, followup_reason=NULL, local_lock=1 WHERE vehicle_no=?", (v_no,))
                                        st.rerun()
                                        
                            with pop3:
                                with st.popover("🤝 Match & Bids", use_container_width=True):
                                    
                                    # 1. SMART DEALER MATCHER
                                    if show_matcher and has_match:
                                        st.success(f"🔥 {len(matches)} Match(es) Found!")
                                        for _, m in matches.iterrows():
                                            st.write(f"- **{m['dealer_name']}** (₹{m['budget_max']:,})")
                                    elif seller_ask <= 0:
                                        st.write("Enter the seller's expected price to find matches.")
                                    else:
                                        st.warning("No matches found.")
                                    
                                    pitch_msg = f"🚗 *Car Available for Bid*\n\n*Make & Model:* {row['make_model']}\n*Year:* {row['year']} ({car_age} yrs)\n*KM Driven:* {row['km_driven']} km\n*Fuel:* {row['fuel_type']}\n*Location:* {row['city']}\n\nLet me know your best offer!"
                                    wa_pitch_url = f"https://wa.me/?text={urllib.parse.quote(pitch_msg)}"
                                    st.link_button("🟢 Pitch via WhatsApp", wa_pitch_url, use_container_width=True)
                                    
                                    st.divider()
                                    
                                    # 2. LOG A DEALER BID
                                    st.markdown("**⚡ Add Dealer Bid**")
                                    with st.form(key=f"bid_{v_no}"):
                                        b_dealer = st.text_input("Dealer Name", placeholder="Name")
                                        b_price = st.text_input("Offer Price", placeholder="₹ Amount")
                                        if st.form_submit_button("Save Bid", use_container_width=True):
                                            if b_dealer and clean_price(b_price) > 0:
                                                bid_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                                                execute_query("INSERT INTO lead_dealer_offers (vehicle_no, dealer_name, offer_price, offer_date) VALUES (?, ?, ?, ?)", 
                                                              (v_no, b_dealer, clean_price(b_price), bid_time))
                                                execute_query("UPDATE leads SET local_lock=1 WHERE vehicle_no=?", (v_no,))
                                                st.rerun()
                                    
                                    # 3. SHOW ACTIVE BIDS
                                    if not bids_df.empty:
                                        st.divider()
                                        st.markdown("**🤝 Active Bids:**")
                                        for _, bid in bids_df.iterrows():
                                            b_time = datetime.strptime(bid['offer_date'], "%Y-%m-%d %H:%M:%S").strftime("%d %b")
                                            st.markdown(f"- **{bid['dealer_name']}**: ₹{bid['offer_price']:,} <i style='font-size:0.8em;'>({b_time})</i>", unsafe_allow_html=True)
                                    
                                    
                                        
                            with pop4:
                                with st.popover("📸 Photo", use_container_width=True):
                                    img = st.file_uploader("Upload Image", key=f"img_{v_no}", label_visibility="collapsed")
                                    if img:
                                        file_path = os.path.join("photos", f"{v_no}.jpg")
                                        with open(file_path, "wb") as f:
                                            f.write(img.getbuffer())
                                        execute_query("UPDATE leads SET photo_path=?, local_lock=1 WHERE vehicle_no=?", (file_path, v_no))
                                        st.rerun()

with tab_expired:
    st.write("### 📂 Leads Not Converted within 5 Days")
    
    col_exp1, col_exp2 = st.columns([7, 3])
    with col_exp1:
        if not expired_df.empty and 'vehicle_no' in expired_df.columns:
                st.dataframe(expired_df[['vehicle_no', 'make_model', 'customer_expectation', 'seller_name', 'phone_number']], use_container_width=True)
    with col_exp2:
        st.info("Want to continue working a lead? Enter the Vehicle Number below to reset its 5-day timer and push it back to the Active Pipeline.")
        with st.form("revive_form"):
            revive_vno = st.text_input("Enter Vehicle No (🆔)")
            if st.form_submit_button("🔄 Revive Lead", use_container_width=True):
                if revive_vno:
                    execute_query("UPDATE leads SET system_date_added=CURRENT_TIMESTAMP, local_lock=1 WHERE vehicle_no=?", (revive_vno.strip(),))
                    st.success("Lead Revived!")
                    st.rerun()

with tab_crm:
    crm_col1, crm_col2 = st.columns([1, 1])
    
    with crm_col1:
        st.write("### 👥 Add Dealer to CRM")
        with st.form("add_dealer"):
            d_name = st.text_input("Dealer Name")
            d_budget = st.text_input("Max Budget (₹)")
            d_fuel = st.selectbox("Preferred Fuel", ["Any", "Petrol", "Diesel", "CNG", "EV"])
            d_make = st.text_input("Preferred Make (e.g., Maruti, Hyundai)", value="Any")
            d_rto = st.text_input("Preferred Location/RTO (e.g., DL, UP, HR)", value="Any")
            
            if st.form_submit_button("💾 Save Dealer"):
                if d_name and clean_price(d_budget) > 0:
                    execute_query('''
                        INSERT INTO dealer_preferences (dealer_name, budget_max, preferred_make, preferred_fuel, preferred_city)
                        VALUES (?, ?, ?, ?, ?)
                    ''', (d_name, clean_price(d_budget), d_make, d_fuel, d_rto))
                    st.success(f"{d_name} added to Network!")
                    st.rerun()
                else:
                    st.error("Name and Budget are required.")
                    
        st.divider()
        st.write("**Current Dealer Network:**")
        st.dataframe(get_dealer_prefs())
        
    with crm_col2:
        st.write("### 📊 Dealer Leaderboard & Activity")
        st.info("Tracks which dealers are actively bidding on your vehicles.")
        bids_df = get_dealer_bids()
        if not bids_df.empty:
            bid_counts = bids_df.groupby('dealer_name').size().reset_index(name='Total Bids Placed')
            bid_counts = bid_counts.sort_values(by='Total Bids Placed', ascending=False)
            st.dataframe(bid_counts, use_container_width=True)
        else:
            st.write("No bids recorded yet. Add bids via the Match Dealer popover to track activity.")