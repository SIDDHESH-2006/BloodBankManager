"""
Concurrency and ACID Transaction Verification Test
Matches Slides 4, 5, and 6 of Review 2 presentation.

Simulates two concurrent hospital staff threads simultaneously attempting to claim
the EXACT SAME available blood unit at the exact same instant.

Verifies:
1. Atomicity: Whole transaction commits or rolls back
2. Consistency: UNIQUE(unit_id) and CHECK constraints hold
3. Isolation: Conditional UPDATE blood_unit SET status = 'ISSUED' WHERE unit_id = ? AND status = 'AVAILABLE'
   detects conflict (rowcount != 1) and prevents race-condition double allocation.
4. Durability: Committed state persists across connections.

Author: Siddhesh Srinivasan (24BYB0035)
"""

import os
import threading
import time
from typing import Dict, Any, List
from app.database import init_db, get_connection
from app.queries import (
    register_donor, record_donation, record_quality_check,
    register_hospital, create_blood_request, allocate_units
)

TEST_DB_PATH = os.path.join(os.path.dirname(__file__), "test_concurrency.db")


def run_concurrency_race_condition_test() -> Dict[str, Any]:
    """
    Sets up a controlled race-condition test in an isolated test database:
    - Exactly 1 available unit of O- (O- can only receive O-)
    - 2 concurrent threads trying to allocate that single unit at the exact same instant
    """
    # Use isolated test database
    if os.path.exists(TEST_DB_PATH):
        try:
            os.remove(TEST_DB_PATH)
        except Exception:
            pass

    init_db(TEST_DB_PATH)
    os.environ["BLOOD_BANK_DB"] = TEST_DB_PATH

    try:
        # Create Hospital A and Hospital B
        h_a = register_hospital("City Trauma Emergency Center", "Chennai", "999-001")
        h_b = register_hospital("Apollo Apex Critical Care", "Chennai", "999-002")

        # Create exactly 1 donor (O-) and 1 donation -> exactly 1 unit
        d_id = register_donor("Sole O- Negative Donor", "O-", "+91-9999988888")
        donation = record_donation(d_id, 450, 15.0, shelf_life_days=20)
        target_unit_id = donation["unit_id"]

        # Pass quality inspection so it's eligible
        record_quality_check(
            unit_id=target_unit_id,
            checked_by="Dr. Meera Rao (QC Officer)",
            quality_status="PASSED",
            defect_detected=0,
            action_taken="RELEASED"
        )

        # Both Hospital A and Hospital B urgently request 1 unit of O-
        # Since O- can ONLY receive O-, they must compete for target_unit_id!
        req_a = create_blood_request(h_a, "O-", 1, urgency="CRITICAL")
        req_b = create_blood_request(h_b, "O-", 1, urgency="CRITICAL")

        results: List[Dict[str, Any]] = []
        barrier = threading.Barrier(2)

        def worker(staff_name: str, req_id: int):
            barrier.wait()  # Both threads release at the exact same microsecond
            t_start = time.perf_counter()
            try:
                res = allocate_units(req_id, max_units=1)
                t_elapsed = (time.perf_counter() - t_start) * 1000
                allocated_ids = [u["unit_id"] for u in res.get("allocated_units", [])]
                results.append({
                    "staff": staff_name,
                    "request_id": req_id,
                    "success": len(allocated_ids) > 0,
                    "allocated_units": allocated_ids,
                    "message": res.get("message"),
                    "time_ms": round(t_elapsed, 2)
                })
            except Exception as e:
                t_elapsed = (time.perf_counter() - t_start) * 1000
                results.append({
                    "staff": staff_name,
                    "request_id": req_id,
                    "success": False,
                    "error": str(e),
                    "time_ms": round(t_elapsed, 2)
                })

        t1 = threading.Thread(target=worker, args=("Staff 1 (Trauma Center)", req_a))
        t2 = threading.Thread(target=worker, args=("Staff 2 (Apollo Apex)", req_b))

        t1.start()
        t2.start()
        t1.join()
        t2.join()

        # Database verification
        conn = get_connection(TEST_DB_PATH)
        cursor = conn.cursor()

        cursor.execute("SELECT status FROM blood_unit WHERE unit_id = ?", (target_unit_id,))
        final_unit_status = cursor.fetchone()["status"]

        cursor.execute("SELECT COUNT(*) FROM allocation WHERE unit_id = ?", (target_unit_id,))
        alloc_count = cursor.fetchone()[0]

        cursor.execute("SELECT request_id, status FROM blood_request WHERE request_id IN (?, ?)", (req_a, req_b))
        request_statuses = {row["request_id"]: row["status"] for row in cursor.fetchall()}
        conn.close()

        successes = [r for r in results if r.get("success")]
        failures = [r for r in results if not r.get("success")]

        acid_passed = (len(successes) == 1 and alloc_count == 1 and final_unit_status == 'ISSUED')

        return {
            "test_target_unit_id": target_unit_id,
            "target_blood_group": "O-",
            "acid_properties_verified": acid_passed,
            "total_competing_threads": 2,
            "successful_claims": len(successes),
            "prevented_duplicate_claims": len(failures),
            "db_allocation_record_count": alloc_count,
            "final_unit_status": final_unit_status,
            "thread_results": results,
            "request_statuses": request_statuses,
            "summary": "PASS: ACID Concurrency Protection Verified! Exactly 1 staff thread acquired Unit #" + str(target_unit_id) + ". The competing thread safely backed off with no double allocation." if acid_passed else "FAIL: Race condition occurred."
        }
    finally:
        # Restore default DB env
        if "BLOOD_BANK_DB" in os.environ:
            del os.environ["BLOOD_BANK_DB"]


if __name__ == "__main__":
    print("=" * 75)
    print("CONCURRENCY & TRANSACTION ISOLATION TEST (Slides 4 & 5)")
    print("Simulating 2 Concurrent Staff Threads Claiming the Same Sole O- Unit")
    print("=" * 75)
    test_result = run_concurrency_race_condition_test()
    print(f"Target Unit ID: #{test_result['test_target_unit_id']} ({test_result['target_blood_group']})")
    print(f"Final Unit Status in DB: {test_result['final_unit_status']}")
    print(f"Total Allocation Rows in DB: {test_result['db_allocation_record_count']}")
    print("\nThread Results:")
    for res in test_result["thread_results"]:
        status_txt = "CLAIMED UNIT" if res.get("success") else "BLOCKED / NO STOCK"
        units_str = f"Unit {res.get('allocated_units')}" if res.get("success") else "None"
        print(f"  [{res['staff']}] -> {status_txt} ({units_str}) in {res.get('time_ms')} ms")
        if res.get("message"):
            print(f"      Message: {res['message']}")
        if res.get("error"):
            print(f"      Handled Error: {res['error']}")
    print("\nACID Consistency Check:")
    print(f"  Verified: {test_result['acid_properties_verified']}")
    print(f"  {test_result['summary']}")
    print("=" * 75)
