import sqlite3
import pandas as pd
import os
from datetime import datetime

from data_generator import generate_sample_data

ROOT = os.path.dirname(__file__)
DB_FILE = os.path.join(ROOT, "claims.db")
CSV_BACKUP = os.path.join(ROOT, "sample_claims.csv")

def get_connection():
    return sqlite3.connect(DB_FILE, check_same_thread=False)


def _get_table_columns(conn, table_name: str) -> list:
    cursor = conn.cursor()
    cursor.execute(f"PRAGMA table_info({table_name})")
    return [row[1] for row in cursor.fetchall()]


def initialize_db():
    conn = get_connection()
    cursor = conn.cursor()
    
    # Create tables
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS claims_history (
            claim_id TEXT PRIMARY KEY,
            provider_id TEXT,
            provider_name TEXT,
            network TEXT,
            patient_id TEXT,
            patient_age INTEGER,
            patient_gender TEXT,
            admission_date TEXT,
            discharge_date TEXT,
            procedure_code TEXT,
            procedure_codes TEXT,
            diagnosis_code TEXT,
            claim_type TEXT,
            billed_amount REAL,
            item_count INTEGER,
            decision TEXT,
            claim_hash TEXT,
            decision_reasons TEXT,
            rule_triggered TEXT,
            explanation TEXT
        )
    ''')
    
    # Ensure table schema can accept imported columns from CSV
    existing_columns = _get_table_columns(conn, 'claims_history')
    required_columns = [
        'claim_id', 'provider_id', 'provider_name', 'network', 'patient_id', 'patient_age',
        'patient_gender', 'admission_date', 'discharge_date', 'procedure_code', 'procedure_codes',
        'diagnosis_code', 'claim_type', 'billed_amount', 'item_count', 'decision', 'claim_hash',
        'decision_reasons', 'rule_triggered', 'explanation'
    ]
    for col in required_columns:
        if col not in existing_columns:
            cursor.execute(f'ALTER TABLE claims_history ADD COLUMN {col} TEXT')
    
    # Check if empty
    cursor.execute('SELECT COUNT(*) FROM claims_history')
    count = cursor.fetchone()[0]
    
    if count == 0:
        if os.path.exists(CSV_BACKUP):
            df = pd.read_csv(CSV_BACKUP)
        else:
            df = generate_sample_data()
        
        # Ensure new columns exist on import dataframe
        for col in required_columns:
            if col not in df.columns:
                df[col] = None
        
        df.to_sql('claims_history', conn, if_exists='append', index=False)
        
    conn.commit()
    conn.close()

def get_historical_claims() -> pd.DataFrame:
    conn = get_connection()
    df = pd.read_sql('SELECT * FROM claims_history', conn)
    conn.close()
    return df

def insert_claim(claim_data: dict):
    conn = get_connection()
    df = pd.DataFrame([claim_data])
    df.to_sql('claims_history', conn, if_exists='append', index=False)
    conn.close()

# Initialize upon import
initialize_db()
