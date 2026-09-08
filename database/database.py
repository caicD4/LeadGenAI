import json
import sqlite3


DB_PATH = "database/leads.db"


def get_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


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

    # Jobs table — persists job state across server restarts so a uvicorn
    # reload does not silently lose an in-flight or completed job.
    conn.execute("""
        CREATE TABLE IF NOT EXISTS jobs (
            job_id TEXT PRIMARY KEY,
            status TEXT NOT NULL DEFAULT 'queued',
            progress INTEGER NOT NULL DEFAULT 0,
            message TEXT NOT NULL DEFAULT '',
            leads TEXT NOT NULL DEFAULT '[]',
            created_at TEXT NOT NULL DEFAULT (datetime('now')),
            updated_at TEXT NOT NULL DEFAULT (datetime('now'))
        )
    """)

    conn.commit()
    conn.close()


# ── Leads ─────────────────────────────────────────────────────────────────────

def save_lead(
    company_name: str,
    industry: str,
    company_info: str,
    research: str,
):
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


# ── Jobs ──────────────────────────────────────────────────────────────────────

def create_job_in_db(job_id: str):
    """Insert a new job row with default queued state."""
    conn = get_connection()

    conn.execute(
        """
        INSERT INTO jobs (job_id, status, progress, message, leads)
        VALUES (?, 'queued', 0, 'Job queued...', '[]')
        """,
        (job_id,)
    )

    conn.commit()
    conn.close()


def update_job_in_db(
    job_id: str,
    status: str,
    progress: int,
    message: str,
    leads=None,
):
    """Persist job state to the database."""
    conn = get_connection()

    leads_json = json.dumps(leads) if leads is not None else None

    if leads_json is not None:
        conn.execute(
            """
            UPDATE jobs
            SET status = ?,
                progress = ?,
                message = ?,
                leads = ?,
                updated_at = datetime('now')
            WHERE job_id = ?
            """,
            (status, progress, message, leads_json, job_id)
        )
    else:
        conn.execute(
            """
            UPDATE jobs
            SET status = ?,
                progress = ?,
                message = ?,
                updated_at = datetime('now')
            WHERE job_id = ?
            """,
            (status, progress, message, job_id)
        )

    conn.commit()
    conn.close()


def get_job_from_db(job_id: str) -> dict | None:
    """Retrieve a job by ID from the database. Returns None if not found."""
    conn = get_connection()

    cursor = conn.execute(
        "SELECT * FROM jobs WHERE job_id = ?",
        (job_id,)
    )

    row = cursor.fetchone()
    conn.close()

    if row is None:
        return None

    return {
        "status": row["status"],
        "progress": row["progress"],
        "message": row["message"],
        "leads": json.loads(row["leads"]),
    }