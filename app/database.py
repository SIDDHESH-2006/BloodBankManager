"""
Database connection and initialization module.
Smart Blood Bank Management System (Course Project Review 2)
Author: Siddhesh Srinivasan (24BYB0035)
"""

import os
import sqlite3
from pathlib import Path

# Base directory for the project
BASE_DIR = Path(__file__).resolve().parent.parent
DEFAULT_DB_PATH = BASE_DIR / "blood_bank.db"
SCHEMA_PATH = BASE_DIR / "schema.sql"

# Red blood cell compatibility matrix: (recipient, donor)
COMPATIBILITY_RULES = [
    # O- can only receive O-
    ('O-', 'O-'),
    # O+ can receive O-, O+
    ('O+', 'O-'), ('O+', 'O+'),
    # A- can receive O-, A-
    ('A-', 'O-'), ('A-', 'A-'),
    # A+ can receive O-, O+, A-, A+
    ('A+', 'O-'), ('A+', 'O+'), ('A+', 'A-'), ('A+', 'A+'),
    # B- can receive O-, B-
    ('B-', 'O-'), ('B-', 'B-'),
    # B+ can receive O-, O+, B-, B+
    ('B+', 'O-'), ('B+', 'O+'), ('B+', 'B-'), ('B+', 'B+'),
    # AB- can receive O-, A-, B-, AB-
    ('AB-', 'O-'), ('AB-', 'A-'), ('AB-', 'B-'), ('AB-', 'AB-'),
    # AB+ is universal recipient (can receive all)
    ('AB+', 'O-'), ('AB+', 'O+'), ('AB+', 'A-'), ('AB+', 'A+'),
    ('AB+', 'B-'), ('AB+', 'B+'), ('AB+', 'AB-'), ('AB+', 'AB+')
]


def get_connection(db_path=None, timeout=15.0):
    """
    Returns a configured SQLite connection with foreign keys enabled
    and row_factory set to sqlite3.Row for dictionary-style column access.
    """
    path = db_path or os.environ.get("BLOOD_BANK_DB", str(DEFAULT_DB_PATH))
    conn = sqlite3.connect(path, timeout=timeout, isolation_level=None)  # autocommit mode; we manage BEGIN/COMMIT
    conn.execute("PRAGMA foreign_keys = ON;")
    conn.execute("PRAGMA journal_mode = WAL;")  # Write-Ahead Logging for high concurrency
    conn.row_factory = sqlite3.Row
    return conn


def init_db(db_path=None):
    """
    Initializes the database schema from schema.sql and seeds the compatibility matrix.
    """
    path = db_path or os.environ.get("BLOOD_BANK_DB", str(DEFAULT_DB_PATH))
    conn = get_connection(path)
    try:
        with open(SCHEMA_PATH, "r", encoding="utf-8") as f:
            schema_sql = f.read()
        conn.executescript(schema_sql)

        # Seed compatibility matrix if not present
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM compatibility")
        if cursor.fetchone()[0] == 0:
            cursor.executemany(
                "INSERT OR IGNORE INTO compatibility (recipient_group, donor_group) VALUES (?, ?)",
                COMPATIBILITY_RULES
            )
        print(f"Database successfully initialized at {path}")
    finally:
        conn.close()


if __name__ == "__main__":
    init_db()
