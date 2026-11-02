"""
Application Entry Point.
Smart Blood Bank Management System (Course Project Review 2)
Author: Siddhesh Srinivasan (24BYB0035)
"""

import os
from app.routes import app
from app.database import init_db, DEFAULT_DB_PATH

if __name__ == "__main__":
    # Ensure database exists before launching
    if not os.path.exists(DEFAULT_DB_PATH):
        print("Database not found. Initializing schema and seed data...")
        from seed_data import seed_database
        seed_database()

    port = int(os.environ.get("PORT", 5000))
    print(f"Starting Smart Blood Bank Management System on http://127.0.0.1:{port}")
    app.run(host="0.0.0.0", port=port, debug=True)
