"""
LeadGenAI — SQLite persistence layer.

Schema
------
companies     — one row per unique company (deduplicated by normalized domain)
leads         — research result for a company within a job
opportunities — automation opportunities identified per lead
sources       — evidence URLs per lead
jobs          — async job state (for the API polling system)
"""

import json
import re
import sqlite3
from datetime import datetime
from typing import Optional


DB_PATH = "database/leads.db"


# ---------------------------------------------------------------------------
# Connection helper
# ---------------------------------------------------------------------------

def get_connection() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    # Enable WAL mode for better concurrent read/write performance.
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


# ---------------------------------------------------------------------------
# Domain normalisation (used for deduplication)
# ---------------------------------------------------------------------------

def normalize_domain(url_or_name: str) -> str:
    """
    Turn a URL or company name into a stable deduplication key.

    Examples:
        https://www.GlowMedspa.com/about  ->  glowmedspa.com
        GlowMedspa                         ->  glowmedspa
    """
    if not url_or_name:
        return ""

    s = url_or_name.strip().lower()

    # If it looks like a URL, extract the hostname.
    if "://" in s or s.startswith("www."):
        # Strip protocol
        s = re.sub(r"^https?://", "", s)
        # Strip www.
        s = re.sub(r"^www\.", "", s)
        # Keep only the domain part (strip path / query)
        s = s.split("/")[0].split("?")[0].split("#")[0]

    # Remove punctuation common in company names: "Co.", "Ltd.", "Inc." etc.
    s = re.sub(r"\s+(pvt\.?|ltd\.?|inc\.?|llc\.?|co\.?|corp\.?|private\.?)$", "", s)
    # Collapse whitespace and replace spaces with hyphens (for names without domains)
    s = re.sub(r"\s+", "-", s.strip())

    return s


# ---------------------------------------------------------------------------
# Schema initialisation
# ---------------------------------------------------------------------------

def init_db():
    conn = get_connection()

    # ------------------------------------------------------------------
    # companies — one row per unique business (deduplicated by domain)
    # ------------------------------------------------------------------
    conn.execute("""
        CREATE TABLE IF NOT EXISTS companies (
            id               INTEGER PRIMARY KEY AUTOINCREMENT,
            name             TEXT NOT NULL,
            normalized_domain TEXT NOT NULL DEFAULT '',
            website          TEXT NOT NULL DEFAULT '',
            industry         TEXT NOT NULL DEFAULT '',
            location         TEXT NOT NULL DEFAULT '',
            description      TEXT NOT NULL DEFAULT '',
            created_at       TEXT NOT NULL DEFAULT (datetime('now')),
            updated_at       TEXT NOT NULL DEFAULT (datetime('now'))
        )
    """)

    # ------------------------------------------------------------------
    # leads — research result linked to a company (and optionally a job)
    # ------------------------------------------------------------------
    conn.execute("""
        CREATE TABLE IF NOT EXISTS leads (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            company_id      INTEGER NOT NULL REFERENCES companies(id),
            job_id          TEXT,
            score           INTEGER NOT NULL DEFAULT 0,
            score_breakdown TEXT NOT NULL DEFAULT '{}',
            score_reasoning TEXT NOT NULL DEFAULT '',
            why_good_lead   TEXT NOT NULL DEFAULT '',
            research_json   TEXT NOT NULL DEFAULT '{}',
            status          TEXT NOT NULL DEFAULT 'researched',
            created_at      TEXT NOT NULL DEFAULT (datetime('now')),
            updated_at      TEXT NOT NULL DEFAULT (datetime('now'))
        )
    """)

    # ------------------------------------------------------------------
    # opportunities — automation opportunities per lead
    # ------------------------------------------------------------------
    conn.execute("""
        CREATE TABLE IF NOT EXISTS opportunities (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            lead_id     INTEGER NOT NULL REFERENCES leads(id),
            opportunity TEXT NOT NULL,
            reasoning   TEXT NOT NULL DEFAULT '',
            evidence    TEXT NOT NULL DEFAULT '',
            priority    TEXT NOT NULL DEFAULT 'MEDIUM'
        )
    """)

    # ------------------------------------------------------------------
    # sources — evidence URLs per lead
    # ------------------------------------------------------------------
    conn.execute("""
        CREATE TABLE IF NOT EXISTS sources (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            lead_id    INTEGER NOT NULL REFERENCES leads(id),
            company_id INTEGER REFERENCES companies(id),
            url        TEXT NOT NULL,
            title      TEXT NOT NULL DEFAULT '',
            snippet    TEXT NOT NULL DEFAULT ''
        )
    """)

    # ------------------------------------------------------------------
    # jobs — async job state for the API polling system
    # ------------------------------------------------------------------
    conn.execute("""
        CREATE TABLE IF NOT EXISTS jobs (
            job_id     TEXT PRIMARY KEY,
            status     TEXT NOT NULL DEFAULT 'queued',
            progress   INTEGER NOT NULL DEFAULT 0,
            message    TEXT NOT NULL DEFAULT '',
            leads      TEXT NOT NULL DEFAULT '[]',
            created_at TEXT NOT NULL DEFAULT (datetime('now')),
            updated_at TEXT NOT NULL DEFAULT (datetime('now'))
        )
    """)

    # ------------------------------------------------------------------
    # Legacy leads table (kept for backward compatibility, not used by
    # new code).  Only created if it doesn't already exist.
    # ------------------------------------------------------------------
    conn.execute("""
        CREATE TABLE IF NOT EXISTS leads_legacy (
            id           INTEGER PRIMARY KEY AUTOINCREMENT,
            company_name TEXT NOT NULL,
            industry     TEXT,
            company_info TEXT,
            research     TEXT
        )
    """)

    conn.commit()
    conn.close()
    print("[DB] Schema initialised.")


# ---------------------------------------------------------------------------
# Company helpers
# ---------------------------------------------------------------------------

def get_company_by_domain(normalized_domain: str) -> Optional[dict]:
    """Return a company row by its normalised domain, or None."""
    if not normalized_domain:
        return None

    conn = get_connection()
    row = conn.execute(
        "SELECT * FROM companies WHERE normalized_domain = ? LIMIT 1",
        (normalized_domain,)
    ).fetchone()
    conn.close()

    return dict(row) if row else None


def upsert_company(
    name: str,
    normalized_domain: str,
    website: str = "",
    industry: str = "",
    location: str = "",
    description: str = "",
) -> int:
    """
    Insert a new company or update an existing one (matched by normalized_domain).
    Returns the company id.
    """
    conn = get_connection()

    existing = conn.execute(
        "SELECT id FROM companies WHERE normalized_domain = ? LIMIT 1",
        (normalized_domain,)
    ).fetchone()

    now = datetime.utcnow().isoformat()

    if existing:
        company_id = existing["id"]
        conn.execute(
            """
            UPDATE companies
            SET name = ?, website = ?, industry = ?, location = ?,
                description = ?, updated_at = ?
            WHERE id = ?
            """,
            (name, website, industry, location, description, now, company_id)
        )
    else:
        cursor = conn.execute(
            """
            INSERT INTO companies
                (name, normalized_domain, website, industry, location, description,
                 created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (name, normalized_domain, website, industry, location, description, now, now)
        )
        company_id = cursor.lastrowid

    conn.commit()
    conn.close()
    return company_id


# ---------------------------------------------------------------------------
# Lead (research result) helpers
# ---------------------------------------------------------------------------

def save_full_lead(
    company_id: int,
    job_id: str,
    score: int,
    score_breakdown: dict,
    score_reasoning: str,
    why_good_lead: str,
    research_json: dict,
    opportunities: list[dict],  # [{opportunity, reasoning, evidence, priority}]
    sources: list[dict],        # [{url, title, snippet}]
) -> int:
    """
    Atomically save a lead with its opportunities and sources.
    Returns the lead id.
    """
    conn = get_connection()
    now = datetime.utcnow().isoformat()

    cursor = conn.execute(
        """
        INSERT INTO leads
            (company_id, job_id, score, score_breakdown, score_reasoning,
             why_good_lead, research_json, status, created_at, updated_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, 'researched', ?, ?)
        """,
        (
            company_id, job_id, score,
            json.dumps(score_breakdown),
            score_reasoning,
            why_good_lead,
            json.dumps(research_json),
            now, now,
        )
    )
    lead_id = cursor.lastrowid

    for opp in opportunities:
        conn.execute(
            """
            INSERT INTO opportunities (lead_id, opportunity, reasoning, evidence, priority)
            VALUES (?, ?, ?, ?, ?)
            """,
            (
                lead_id,
                opp.get("opportunity", ""),
                opp.get("reasoning", ""),
                opp.get("evidence", ""),
                opp.get("priority", "MEDIUM"),
            )
        )

    for src in sources:
        conn.execute(
            """
            INSERT INTO sources (lead_id, company_id, url, title, snippet)
            VALUES (?, ?, ?, ?, ?)
            """,
            (
                lead_id,
                company_id,
                src.get("url", ""),
                src.get("title", ""),
                src.get("snippet", ""),
            )
        )

    conn.commit()
    conn.close()
    return lead_id


def get_all_leads_with_details() -> list[dict]:
    """
    Return all leads with joined company, opportunity, and source data.
    Ordered newest first.
    """
    conn = get_connection()

    rows = conn.execute("""
        SELECT
            l.id          AS lead_id,
            l.score,
            l.score_breakdown,
            l.score_reasoning,
            l.why_good_lead,
            l.research_json,
            l.status,
            l.created_at,
            c.id          AS company_id,
            c.name        AS company_name,
            c.website,
            c.industry,
            c.location,
            c.description
        FROM leads l
        JOIN companies c ON c.id = l.company_id
        ORDER BY l.id DESC
    """).fetchall()

    results = []
    for row in rows:
        lead_id = row["lead_id"]

        opps = conn.execute(
            "SELECT opportunity, reasoning, evidence, priority FROM opportunities WHERE lead_id = ?",
            (lead_id,)
        ).fetchall()

        srcs = conn.execute(
            "SELECT url, title, snippet FROM sources WHERE lead_id = ?",
            (lead_id,)
        ).fetchall()

        research = {}
        try:
            research = json.loads(row["research_json"] or "{}")
        except Exception:
            pass

        score_breakdown = {}
        try:
            score_breakdown = json.loads(row["score_breakdown"] or "{}")
        except Exception:
            pass

        results.append({
            "lead_id": lead_id,
            "company_id": row["company_id"],
            "company_name": row["company_name"],
            "website": row["website"],
            "industry": row["industry"],
            "location": row["location"],
            "description": row["description"],
            "score": row["score"],
            "score_breakdown": score_breakdown,
            "score_reasoning": row["score_reasoning"],
            "why_good_lead": row["why_good_lead"],
            "research": research,
            "status": row["status"],
            "created_at": row["created_at"],
            "opportunities": [dict(o) for o in opps],
            "sources": [dict(s) for s in srcs],
        })

    conn.close()
    return results


def get_lead_by_id(lead_id: int) -> Optional[dict]:
    """Return a single lead with full details, or None."""
    all_leads = get_all_leads_with_details()
    for lead in all_leads:
        if lead["lead_id"] == lead_id:
            return lead
    return None


# ---------------------------------------------------------------------------
# Legacy save_lead (kept for backward compat with orchestrator)
# ---------------------------------------------------------------------------

def save_lead(
    company_name: str,
    industry: str,
    company_info: str,
    research: str,
):
    """Legacy save — writes to leads_legacy table."""
    conn = get_connection()
    conn.execute(
        """
        INSERT INTO leads_legacy (company_name, industry, company_info, research)
        VALUES (?, ?, ?, ?)
        """,
        (company_name, industry, company_info, research)
    )
    conn.commit()
    conn.close()


def get_leads():
    """Legacy get — reads from leads_legacy table."""
    conn = get_connection()
    cursor = conn.execute(
        "SELECT id, company_name, industry, company_info, research FROM leads_legacy ORDER BY id DESC"
    )
    leads = cursor.fetchall()
    conn.close()
    return leads


# ---------------------------------------------------------------------------
# Job helpers (unchanged from original — the job system is working)
# ---------------------------------------------------------------------------

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
            SET status = ?, progress = ?, message = ?, leads = ?,
                updated_at = datetime('now')
            WHERE job_id = ?
            """,
            (status, progress, message, leads_json, job_id)
        )
    else:
        conn.execute(
            """
            UPDATE jobs
            SET status = ?, progress = ?, message = ?,
                updated_at = datetime('now')
            WHERE job_id = ?
            """,
            (status, progress, message, job_id)
        )

    conn.commit()
    conn.close()


def get_job_from_db(job_id: str) -> Optional[dict]:
    """Retrieve a job by ID from the database. Returns None if not found."""
    conn = get_connection()
    row = conn.execute(
        "SELECT * FROM jobs WHERE job_id = ?",
        (job_id,)
    ).fetchone()
    conn.close()

    if row is None:
        return None

    return {
        "status": row["status"],
        "progress": row["progress"],
        "message": row["message"],
        "leads": json.loads(row["leads"]),
    }