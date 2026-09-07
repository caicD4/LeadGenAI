import sqlite3


DB_PATH = "database/leads.db"


def get_connection():
    return sqlite3.connect(DB_PATH)


def init_db():
    conn = get_connection()

    conn.execute("""
        CREATE TABLE IF NOT EXISTS leads (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            company_name TEXT NOT NULL,
            industry TEXT,
            company_info TEXT,
            research TEXT
        )
    """)

    conn.commit()
    conn.close()

def save_lead(company_name: str, industry: str, company_info: str, research: str):
    conn = get_connection()

    conn.execute(
        """
        INSERT INTO leads (
            company_name,
            industry,
            company_info,
            research
        )
        VALUES (?, ?, ?, ?)
        """,
        (company_name, industry, company_info, research)
    )

    conn.commit()
    conn.close()

def get_leads():
    conn = get_connection()

    cursor = conn.execute(
        """
        SELECT id, company_name, industry, company_info, research
        FROM leads
        ORDER BY id DESC
        """
    )

    leads = cursor.fetchall()

    conn.close()

    return leads