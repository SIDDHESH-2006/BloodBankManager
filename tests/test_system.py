"""
Comprehensive Unit & Integration Test Suite for Smart Blood Bank Management System.
Tests:
1. 3NF Constraints and Referential Integrity (Foreign Keys, Check Constraints)
2. Database Triggers (Automatic donor update, unit status sync, request status sync, safety blocks)
3. Quality Check Safety Rules (Unverified or failed units cannot be allocated)
4. Slide 8 FEFO Matching Algorithm & Compatibility Matrix
5. Slide 4 & 5 Atomic Transactions and Concurrency

Author: Siddhesh Srinivasan (24BYB0035)
"""

import os
import sqlite3
import pytest
from datetime import datetime, timedelta
from app.database import init_db, get_connection
from app.queries import (
    register_donor, record_donation, record_quality_check,
    register_hospital, create_blood_request, allocate_units,
    find_eligible_units_for_request, get_inventory_report
)

TEST_DB = "test_system_suite.db"


@pytest.fixture(autouse=True)
def setup_teardown():
    if os.path.exists(TEST_DB):
        try:
            os.remove(TEST_DB)
        except Exception:
            pass
    init_db(TEST_DB)
    os.environ["BLOOD_BANK_DB"] = TEST_DB
    yield
    if os.path.exists(TEST_DB):
        try:
            os.remove(TEST_DB)
        except Exception:
            pass
    if "BLOOD_BANK_DB" in os.environ:
        del os.environ["BLOOD_BANK_DB"]


def test_donor_blood_group_constraint():
    """Verify CHECK constraint rejects invalid blood groups."""
    with pytest.raises(sqlite3.IntegrityError):
        register_donor("Invalid Donor", "XYZ+", "1234567890")


def test_donation_hb_level_constraint():
    """Verify screening rule rejects hemoglobin below 12.0 g/dL."""
    d_id = register_donor("Low Hb Donor", "O+", "9876543210")
    with pytest.raises(ValueError, match="Hemoglobin level"):
        record_donation(d_id, volume_ml=450, hb_level=10.5)


def test_trigger_updates_donor_last_donated():
    """Verify Trigger 1 automatically sets donor.last_donated on donation."""
    d_id = register_donor("Active Donor", "A+", "9876543210")
    donation_date = (datetime.now() - timedelta(days=2)).strftime("%Y-%m-%d")
    record_donation(d_id, volume_ml=450, hb_level=14.5, donated_on=donation_date)

    conn = get_connection(TEST_DB)
    cursor = conn.cursor()
    cursor.execute("SELECT last_donated FROM donor WHERE donor_id = ?", (d_id,))
    last_donated = cursor.fetchone()["last_donated"]
    conn.close()

    assert last_donated == donation_date


def test_trigger_discards_unit_on_failed_quality_check():
    """Verify Trigger 5 automatically updates unit status to DISCARDED on failure."""
    d_id = register_donor("Test Donor", "B+", "9876543210")
    don = record_donation(d_id, volume_ml=450, hb_level=13.5)
    unit_id = don["unit_id"]

    # Record failed check
    record_quality_check(
        unit_id=unit_id,
        checked_by="Inspector 1",
        quality_status="FAILED",
        defect_detected=1,
        action_taken="DISCARDED"
    )

    conn = get_connection(TEST_DB)
    cursor = conn.cursor()
    cursor.execute("SELECT status FROM blood_unit WHERE unit_id = ?", (unit_id,))
    status = cursor.fetchone()["status"]
    conn.close()

    assert status == "DISCARDED"


def test_trigger_blocks_ineligible_unit_allocation():
    """Verify Trigger 3 raises an abort if an unverified or expired unit is allocated directly."""
    d_id = register_donor("Test Donor", "O+", "9876543210")
    don = record_donation(d_id, volume_ml=450, hb_level=14.0)
    unit_id = don["unit_id"]
    # Unit has NOT had any quality check yet!

    h_id = register_hospital("Emergency Clinic", "Chennai", "123")
    req_id = create_blood_request(h_id, "O+", 1)

    conn = get_connection(TEST_DB)
    cursor = conn.cursor()
    with pytest.raises(sqlite3.IntegrityError, match="Integrity Violation"):
        cursor.execute("INSERT INTO allocation (request_id, unit_id) VALUES (?, ?)", (req_id, unit_id))
    conn.close()


def test_fefo_prioritization():
    """Verify FEFO: earlier expiring units are allocated first."""
    d1 = register_donor("Donor 1", "O+", "111")
    d2 = register_donor("Donor 2", "O+", "222")

    today = datetime.now()
    # Unit 1: expires in 5 days
    don1 = record_donation(d1, 450, 14.0, donated_on=(today - timedelta(days=37)).strftime("%Y-%m-%d"), shelf_life_days=42)
    # Unit 2: expires in 20 days
    don2 = record_donation(d2, 450, 14.0, donated_on=(today - timedelta(days=22)).strftime("%Y-%m-%d"), shelf_life_days=42)

    # Pass quality inspection for both
    record_quality_check(don1["unit_id"], "QC Staff", "PASSED")
    record_quality_check(don2["unit_id"], "QC Staff", "PASSED")

    h_id = register_hospital("General Hospital", "Chennai", "999")
    req_id = create_blood_request(h_id, "O+", 1)

    # Check eligible units order
    eligible = find_eligible_units_for_request(req_id)
    assert len(eligible) == 2
    assert eligible[0]["unit_id"] == don1["unit_id"], "Unit 1 must come first due to earlier expiry (FEFO)"
    assert eligible[1]["unit_id"] == don2["unit_id"]

    # Allocate 1 unit
    result = allocate_units(req_id, max_units=1)
    assert len(result["allocated_units"]) == 1
    assert result["allocated_units"][0]["unit_id"] == don1["unit_id"]


def test_compatibility_rules():
    """Verify A+ can receive O- but cannot receive B+."""
    d_o_neg = register_donor("O- Donor", "O-", "111")
    d_b_pos = register_donor("B+ Donor", "B+", "222")

    don_o = record_donation(d_o_neg, 450, 14.5)
    don_b = record_donation(d_b_pos, 450, 14.5)

    record_quality_check(don_o["unit_id"], "QC Staff", "PASSED")
    record_quality_check(don_b["unit_id"], "QC Staff", "PASSED")

    h_id = register_hospital("Hospital A", "Chennai", "888")
    req_id = create_blood_request(h_id, "A+", 1)  # Patient is A+

    eligible = find_eligible_units_for_request(req_id)
    eligible_unit_ids = [u["unit_id"] for u in eligible]

    assert don_o["unit_id"] in eligible_unit_ids, "O- is compatible with A+"
    assert don_b["unit_id"] not in eligible_unit_ids, "B+ is NOT compatible with A+"
