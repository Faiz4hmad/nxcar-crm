import pandas as pd
import psycopg2
import streamlit as st
from datetime import datetime
import urllib.parse as urlparse

@st.cache_resource
def get_db_connection():
    # Connect directly to Supabase using the Streamlit secret URL string
    return psycopg2.connect(st.secrets["DB_URL"])

def init_db():
    conn = get_db_connection()
    conn.autocommit = True
    c = conn.cursor()
    
    # Create tables with PostgreSQL syntax (SERIAL instead of AUTOINCREMENT)
    c.execute('''
        CREATE TABLE IF NOT EXISTS leads (
            vehicle_no TEXT PRIMARY KEY, date TEXT, source TEXT, ra_assigned TEXT, 
            vehicle_id TEXT, seller_name TEXT, phone_number TEXT, make_model TEXT,
            year TEXT, km_driven TEXT, city TEXT, fuel_type TEXT, ownership TEXT, 
            competitor_inspected TEXT, inspected_date TEXT, customer_expectation TEXT, 
            calling_status TEXT, final_remarks TEXT, photo_path TEXT, 
            followup_time TEXT, local_lock INTEGER DEFAULT 0,
            system_date_added TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    c.execute('''
        CREATE TABLE IF NOT EXISTS dealer_offers (
            id SERIAL PRIMARY KEY,
            vehicle_no TEXT, dealer_name TEXT, offer_price TEXT, offer_date TEXT
        )
    ''')
    c.execute('''
        CREATE TABLE IF NOT EXISTS historical_deals (
            id SERIAL PRIMARY KEY,
            make_model TEXT, year TEXT, closed_price INTEGER
        )
    ''')
    c.execute('''
        CREATE TABLE IF NOT EXISTS dealer_preferences (
            id SERIAL PRIMARY KEY,
            dealer_name TEXT, budget_max INTEGER, 
            preferred_make TEXT, preferred_fuel TEXT, preferred_city TEXT
        )
    ''')
    
    # Ensure UI-specific columns exist
    for col in ['followup_reason', 'remark_history', 'expectation_history', 'ra_name', 'assigned_to']:
        try: c.execute(f"ALTER TABLE leads ADD COLUMN {col} TEXT")
        except: pass
        
    

def sync_from_sheets(sheet_url, current_user):
    if not sheet_url or "google.com/spreadsheets" not in sheet_url:
        return False
        
    try:
        if "/edit" in sheet_url:
            # Handles both standard links and Sudhir's specific formatting
            sheet_url = sheet_url.replace("/edit?usp=sharing", "/export?format=csv&gid=0")
            sheet_url = sheet_url.replace("/edit#gid=", "/export?format=csv&gid=")
            sheet_url = sheet_url.replace("/edit?pli=1&gid=0#gid=0", "/export?format=csv&gid=0")
        df = pd.read_csv(sheet_url).fillna('')
    except:
        return False
        
    init_db()
    conn = get_db_connection()
    conn.autocommit = True
    c = conn.cursor()
    current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    
    for index, row in df.iterrows():
        v_no = str(row.get('Vehicle No', '')).strip()
        if not v_no: continue
            
        c.execute("SELECT local_lock FROM leads WHERE vehicle_no=%s", (v_no,))
        existing = c.fetchone()
        
        if existing:
            if existing[0] == 0:
                c.execute('''
                    UPDATE leads SET 
                    date=%s, source=%s, ra_assigned=%s, vehicle_id=%s, seller_name=%s, 
                    phone_number=%s, make_model=%s, year=%s, km_driven=%s, city=%s, 
                    fuel_type=%s, ownership=%s, competitor_inspected=%s, inspected_date=%s
                    WHERE vehicle_no=%s
                ''', (
                    str(row.get('Date', '')), str(row.get('Source', '')), str(row.get('RA Assigned', '')), 
                    str(row.get('Vehicle ID', '')), str(row.get('Seller Name', '')), str(row.get('Phone Number', '')), 
                    str(row.get('Manufacturer and Model', '')), str(row.get('Year', '')), str(row.get('KM\'s Driven', '')), 
                    str(row.get('City', '')), str(row.get('Fuel Type', '')), str(row.get('Ownership', '')), 
                    str(row.get('Cars24 / Spinny Inspected', '')), str(row.get('Inspected Date', '')), v_no
                ))
        else:
            # This tags the new lead with current_user (Faiz or Sudhir)
            c.execute('''
                INSERT INTO leads (
                    vehicle_no, date, source, ra_assigned, vehicle_id, seller_name, phone_number, 
                    make_model, year, km_driven, city, fuel_type, ownership, 
                    competitor_inspected, inspected_date, customer_expectation, calling_status, final_remarks, local_lock, system_date_added, ra_name
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, 0, %s, %s)
            ''', (
                v_no, str(row.get('Date', '')), str(row.get('Source', '')), str(row.get('RA Assigned', '')), 
                str(row.get('Vehicle ID', '')), str(row.get('Seller Name', '')), str(row.get('Phone Number', '')), 
                str(row.get('Manufacturer and Model', '')), str(row.get('Year', '')), str(row.get('KM\'s Driven', '')), 
                str(row.get('City', '')), str(row.get('Fuel Type', '')), str(row.get('Ownership', '')), 
                str(row.get('Cars24 / Spinny Inspected', '')), str(row.get('Inspected Date', '')),
                str(row.get('Customer Expectation', '')), str(row.get('Caling Status', 'New')), str(row.get('Final Remarks', '')), current_time, current_user
            ))
    
    
    return True
