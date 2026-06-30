import sqlite3
import os
from datetime import datetime

DB_PATH = os.path.join(os.path.dirname(__file__), "phishguard.db")


def get_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    conn = get_conn()
    c = conn.cursor()

    # ── CUSTOMERS (the paying businesses) ──────────────────────────────
    c.execute("""
        CREATE TABLE IF NOT EXISTS customers (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            company_name    TEXT NOT NULL,
            contact_name    TEXT NOT NULL,
            contact_email   TEXT NOT NULL UNIQUE,
            phone           TEXT,
            plan            TEXT DEFAULT 'trial',      -- trial / starter / growth / enterprise
            employee_limit  INTEGER DEFAULT 10,
            status          TEXT DEFAULT 'active',     -- active / past_due / cancelled
            razorpay_customer_id   TEXT,
            razorpay_subscription_id TEXT,
            authorization_signed   INTEGER DEFAULT 0,  -- 1 = legal MoU signed
            authorization_signed_at DATETIME,
            created_at      DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # ── LEADS (people who requested a free audit, not yet customers) ───
    c.execute("""
        CREATE TABLE IF NOT EXISTS leads (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            email       TEXT NOT NULL,
            company_name TEXT,
            phone       TEXT,
            source      TEXT DEFAULT 'landing_page',
            status      TEXT DEFAULT 'new',            -- new / contacted / converted / lost
            created_at  DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # ── CAMPAIGNS ────────────────────────────────────────────────────────
    c.execute("""
        CREATE TABLE IF NOT EXISTS campaigns (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            customer_id INTEGER,
            name        TEXT NOT NULL,
            template    TEXT NOT NULL,
            status      TEXT DEFAULT 'active',          -- active / completed / draft
            created_at  DATETIME DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (customer_id) REFERENCES customers(id)
        )
    """)

    # ── RECIPIENTS ───────────────────────────────────────────────────────
    c.execute("""
        CREATE TABLE IF NOT EXISTS recipients (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            campaign_id INTEGER NOT NULL,
            email       TEXT NOT NULL,
            name        TEXT,
            department  TEXT,
            token       TEXT UNIQUE NOT NULL,
            sent_at     DATETIME DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (campaign_id) REFERENCES campaigns(id)
        )
    """)

    # ── CLICKS ───────────────────────────────────────────────────────────
    c.execute("""
        CREATE TABLE IF NOT EXISTS clicks (
            id           INTEGER PRIMARY KEY AUTOINCREMENT,
            token        TEXT NOT NULL,
            ip           TEXT,
            user_agent   TEXT,
            clicked_at   DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # ── PAYMENTS (Razorpay transaction log) ────────────────────────────
    c.execute("""
        CREATE TABLE IF NOT EXISTS payments (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            customer_id     INTEGER NOT NULL,
            razorpay_payment_id TEXT,
            razorpay_order_id   TEXT,
            amount          INTEGER,                   -- in paise
            currency        TEXT DEFAULT 'INR',
            status          TEXT DEFAULT 'created',     -- created / captured / failed
            plan            TEXT,
            created_at      DATETIME DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (customer_id) REFERENCES customers(id)
        )
    """)

    conn.commit()
    conn.close()
    print("✅ Database ready — customers, leads, campaigns, recipients, clicks, payments")


def seed_demo_data():
    """Optional: insert demo data so the dashboard isn't empty on first run."""
    conn = get_conn()
    c = conn.cursor()
    existing = c.execute("SELECT COUNT(*) as n FROM customers").fetchone()["n"]
    if existing > 0:
        conn.close()
        return
    c.execute("""
        INSERT INTO customers (company_name, contact_name, contact_email, plan, employee_limit, authorization_signed, authorization_signed_at)
        VALUES ('Acme Logistics Pvt Ltd', 'Priya Sharma', 'priya@acmelogistics.in', 'growth', 100, 1, CURRENT_TIMESTAMP)
    """)
    conn.commit()
    conn.close()
    print("✅ Demo customer seeded")


if __name__ == "__main__":
    init_db()
    seed_demo_data()
