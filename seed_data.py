"""
Seed script for Smart Blood Bank Management System.
Populates realistic sample data to demonstrate:
1. Multi-donor donations with proper Hb levels
2. Units with varied expiry dates (demonstrating FEFO prioritization)
3. Quality check history (PASSED, FAILED, QUARANTINED)
4. Hospitals and Blood Requests (Critical, Urgent, Normal)
5. Proof of integrity constraints and triggers

Author: Siddhesh Srinivasan (24BYB0035)
"""

from datetime import datetime, timedelta
from app.database import init_db, get_connection
from app.queries import (
    register_donor, record_donation, record_quality_check,
    register_hospital, create_blood_request
)


def seed_database():
    print("--- Initializing fresh database schema ---")
    init_db()

    conn = get_connection()
    cursor = conn.cursor()

    # Clear existing dynamic data (in child-to-parent order)
    cursor.execute("DELETE FROM allocation;")
    cursor.execute("DELETE FROM blood_quality_check;")
    cursor.execute("DELETE FROM blood_unit;")
    cursor.execute("DELETE FROM donation;")
    cursor.execute("DELETE FROM blood_request;")
    cursor.execute("DELETE FROM hospital;")
    cursor.execute("DELETE FROM donor;")
    conn.close()

    print("--- Seeding Donors ---")
    donors_data = [
        ("Rahul Sharma", "O+", "+91-9876543210"),
        ("Priya Nair", "A+", "+91-9876543211"),
        ("Siddhesh Srinivasan", "O-", "+91-9876543212"),  # Universal Donor
        ("Ananya Deshmukh", "B+", "+91-9876543213"),
        ("Vikram Singh", "AB+", "+91-9876543214"), # Universal Recipient
        ("Neha Gupta", "A-", "+91-9876543215"),
        ("Karthik Raman", "B-", "+91-9876543216"),
        ("Sneha Iyer", "AB-", "+91-9876543217"),
        ("Amit Verma", "O+", "+91-9876543218"),
        ("Pooja Patel", "A+", "+91-9876543219"),
    ]
    donor_ids = {}
    for name, group, phone in donors_data:
        d_id = register_donor(name, group, phone)
        donor_ids[name] = d_id
    print(f"Registered {len(donor_ids)} donors.")

    print("--- Seeding Donations & Blood Units (with varied expiry for FEFO) ---")
    today = datetime.now()

    donations_config = [
        # (donor_name, volume, hb, days_ago, shelf_life_days)
        # Unit 1: Rahul (O+), donated 38 days ago, shelf life 42 -> expires in 4 days! (FEFO Priority)
        ("Rahul Sharma", 450, 14.2, 38, 42),
        # Unit 2: Amit (O+), donated 10 days ago, shelf life 42 -> expires in 32 days
        ("Amit Verma", 450, 15.0, 10, 42),
        # Unit 3: Priya (A+), donated 39 days ago, shelf life 42 -> expires in 3 days! (FEFO Priority)
        ("Priya Nair", 400, 13.5, 39, 42),
        # Unit 4: Pooja (A+), donated 15 days ago, shelf life 42 -> expires in 27 days
        ("Pooja Patel", 450, 13.8, 15, 42),
        # Unit 5: Siddhesh (O-), donated 25 days ago, shelf life 42 -> expires in 17 days
        ("Siddhesh Srinivasan", 450, 14.8, 25, 42),
        # Unit 6: Siddhesh (O-), donated 5 days ago, shelf life 42 -> expires in 37 days
        ("Siddhesh Srinivasan", 450, 15.2, 5, 42),
        # Unit 7: Ananya (B+), donated 36 days ago, shelf life 42 -> expires in 6 days! (FEFO Priority)
        ("Ananya Deshmukh", 450, 12.8, 36, 42),
        # Unit 8: Vikram (AB+), donated 12 days ago, shelf life 42 -> expires in 30 days
        ("Vikram Singh", 450, 16.0, 12, 42),
        # Unit 9: Neha (A-), donated 20 days ago, shelf life 42 -> expires in 22 days
        ("Neha Gupta", 400, 13.0, 20, 42),
        # Unit 10: Karthik (B-), donated 18 days ago, shelf life 42 -> expires in 24 days
        ("Karthik Raman", 450, 14.5, 18, 42),
        # Unit 11: Sneha (AB-), donated 14 days ago, shelf life 42 -> expires in 28 days
        ("Sneha Iyer", 400, 12.6, 14, 42),
    ]

    unit_records = []
    for d_name, vol, hb, days_ago, shelf_life in donations_config:
        d_id = donor_ids[d_name]
        d_date = (today - timedelta(days=days_ago)).strftime("%Y-%m-%d")
        record = record_donation(d_id, vol, hb, donated_on=d_date, shelf_life_days=shelf_life)
        unit_records.append(record)

    print(f"Recorded {len(unit_records)} donations and blood units.")

    print("--- Seeding Quality Inspection Checks ---")
    # All units except one get PASSED check.
    # Unit 4 will get PASSED check.
    # Unit 7 (B+) will get a FAILED check (defect: high turbidity) to demonstrate block on release!
    for idx, u in enumerate(unit_records):
        unit_id = u["unit_id"]
        if idx == 6:  # Unit 7: defect detected!
            record_quality_check(
                unit_id=unit_id,
                checked_by="Dr. Meera Rao (Chief Pathologist)",
                quality_status="FAILED",
                defect_detected=1,
                abnormality_details="High bacterial endotoxin reading and unusual turbidity.",
                action_taken="DISCARDED"
            )
            print(f"  -> Unit #{unit_id} ({u['blood_group']}) marked FAILED / DISCARDED (Testing safety blocks)")
        elif idx == 10:  # Unit 11: Quarantined for re-test
            record_quality_check(
                unit_id=unit_id,
                checked_by="Dr. Arun Varma",
                quality_status="PENDING",
                defect_detected=0,
                abnormality_details="Awaiting secondary ELISA confirmation panel.",
                action_taken="QUARANTINED"
            )
            print(f"  -> Unit #{unit_id} ({u['blood_group']}) marked PENDING / QUARANTINED")
        else:
            record_quality_check(
                unit_id=unit_id,
                checked_by="Dr. Meera Rao (Chief Pathologist)",
                quality_status="PASSED",
                defect_detected=0,
                abnormality_details="Clear morphology, sterile culture, negative for viral markers.",
                action_taken="RELEASED"
            )
    print("Quality inspections recorded.")

    print("--- Seeding Hospitals ---")
    hospitals_data = [
        ("Apollo Multispeciality Hospital", "Chennai", "+91-44-28290200"),
        ("Fortis Malar Hospital", "Chennai", "+91-44-42892222"),
        ("MIOT International", "Chennai", "+91-44-42002288"),
        ("Gleneagles Global Health City", "Chennai", "+91-44-44777000"),
    ]
    hospital_ids = {}
    for name, city, phone in hospitals_data:
        h_id = register_hospital(name, city, phone)
        hospital_ids[name] = h_id
    print(f"Registered {len(hospital_ids)} hospitals.")

    print("--- Seeding Blood Requests ---")
    # 1. Critical request: Apollo urgently needs 2 units of O+
    req1 = create_blood_request(
        hospital_id=hospital_ids["Apollo Multispeciality Hospital"],
        blood_group="O+",
        units_needed=2,
        urgency="CRITICAL"
    )
    # 2. Urgent request: Fortis needs 1 unit of A+
    req2 = create_blood_request(
        hospital_id=hospital_ids["Fortis Malar Hospital"],
        blood_group="A+",
        units_needed=2,
        urgency="URGENT"
    )
    # 3. Normal request: MIOT needs 1 unit of B+ (Note: Unit 7 is B+ but FAILED! Should match O+ or O- if compatible, or wait)
    req3 = create_blood_request(
        hospital_id=hospital_ids["MIOT International"],
        blood_group="B+",
        units_needed=1,
        urgency="NORMAL"
    )

    print(f"Created 3 test requests: Req #{req1} (CRITICAL O+), Req #{req2} (URGENT A+), Req #{req3} (NORMAL B+).")
    print("=== Database Seeding Complete! Ready for demonstration ===")


if __name__ == "__main__":
    seed_database()
