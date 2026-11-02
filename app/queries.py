"""
Query and business logic module for Smart Blood Bank Management System.
Implements 3NF constraints, Slide 4 & 5 Concurrency/Transaction management,
Slide 8 FEFO matching, and Slide 9 analytical reports.

Author: Siddhesh Srinivasan (24BYB0035)
"""

from datetime import datetime, timedelta
from typing import List, Dict, Any, Optional
from app.database import get_connection


# -----------------------------------------------------------------------------
# 1. DONOR QUERIES
# -----------------------------------------------------------------------------
def get_donors() -> List[Dict[str, Any]]:
    """Returns all registered donors with donation counts."""
    conn = get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT 
                d.donor_id,
                d.full_name,
                d.blood_group,
                d.phone,
                d.last_donated,
                COUNT(dn.donation_id) as total_donations
            FROM donor d
            LEFT JOIN donation dn ON d.donor_id = dn.donor_id
            GROUP BY d.donor_id
            ORDER BY d.donor_id DESC
        """)
        return [dict(row) for row in cursor.fetchall()]
    finally:
        conn.close()


def register_donor(full_name: str, blood_group: str, phone: str) -> int:
    """Registers a new donor adhering to CHECK constraints."""
    conn = get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO donor (full_name, blood_group, phone) VALUES (?, ?, ?)",
            (full_name.strip(), blood_group.strip().upper(), phone.strip())
        )
        return cursor.lastrowid
    finally:
        conn.close()


def get_donor_details(donor_id: int) -> Optional[Dict[str, Any]]:
    """Fetches single donor details and donation history."""
    conn = get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM donor WHERE donor_id = ?", (donor_id,))
        donor = cursor.fetchone()
        if not donor:
            return None
        
        result = dict(donor)
        cursor.execute("""
            SELECT d.donation_id, d.donated_on, d.volume_ml, d.hb_level,
                   u.unit_id, u.status as unit_status, u.expiry_date
            FROM donation d
            LEFT JOIN blood_unit u ON d.donation_id = u.donation_id
            WHERE d.donor_id = ?
            ORDER BY d.donated_on DESC
        """, (donor_id,))
        result["donations"] = [dict(row) for row in cursor.fetchall()]
        return result
    finally:
        conn.close()


# -----------------------------------------------------------------------------
# 2. DONATION & BLOOD UNIT CREATION
# -----------------------------------------------------------------------------
def record_donation(donor_id: int, volume_ml: int, hb_level: float, 
                    donated_on: Optional[str] = None, shelf_life_days: int = 42) -> Dict[str, Any]:
    """
    Records a donation and auto-generates the corresponding BLOOD_UNIT.
    Enforces donor eligibility check (Hb >= 12.0) and uses transaction.
    """
    if hb_level < 12.0:
        raise ValueError(f"Screening failed: Hemoglobin level ({hb_level} g/dL) is below minimum required 12.0 g/dL.")

    if volume_ml <= 0:
        raise ValueError("Donation volume must be greater than 0 ml.")

    donated_date = donated_on or datetime.now().strftime("%Y-%m-%d")
    expiry_date = (datetime.strptime(donated_date, "%Y-%m-%d") + timedelta(days=shelf_life_days)).strftime("%Y-%m-%d")

    conn = get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("BEGIN IMMEDIATE")
        try:
            # Fetch donor's blood group
            cursor.execute("SELECT blood_group, full_name FROM donor WHERE donor_id = ?", (donor_id,))
            donor = cursor.fetchone()
            if not donor:
                raise ValueError(f"Donor ID {donor_id} does not exist.")
            blood_group = donor["blood_group"]

            # 1. Insert donation record
            cursor.execute("""
                INSERT INTO donation (donor_id, donated_on, volume_ml, hb_level)
                VALUES (?, ?, ?, ?)
            """, (donor_id, donated_date, volume_ml, hb_level))
            donation_id = cursor.lastrowid

            # 2. Insert blood unit (status defaults to AVAILABLE)
            cursor.execute("""
                INSERT INTO blood_unit (donation_id, blood_group, expiry_date, status)
                VALUES (?, ?, ?, 'AVAILABLE')
            """, (donation_id, blood_group, expiry_date))
            unit_id = cursor.lastrowid

            conn.commit()
            return {
                "donation_id": donation_id,
                "unit_id": unit_id,
                "donor_name": donor["full_name"],
                "blood_group": blood_group,
                "expiry_date": expiry_date,
                "status": "AVAILABLE"
            }
        except Exception:
            conn.rollback()
            raise
    finally:
        conn.close()


def get_blood_units(status_filter: Optional[str] = None, blood_group_filter: Optional[str] = None) -> List[Dict[str, Any]]:
    """Returns blood units with donation info and latest inspection status."""
    conn = get_connection()
    try:
        cursor = conn.cursor()
        query = """
            SELECT 
                u.unit_id,
                u.blood_group,
                u.expiry_date,
                u.status,
                u.created_at,
                d.donation_id,
                d.donated_on,
                d.volume_ml,
                dn.full_name as donor_name,
                dn.donor_id,
                qc.quality_status as latest_quality_status,
                qc.defect_detected as latest_defect_detected,
                qc.action_taken as latest_action_taken,
                CAST(ROUND(julianday(u.expiry_date) - julianday('now')) AS INTEGER) as days_to_expiry
            FROM blood_unit u
            JOIN donation d ON u.donation_id = d.donation_id
            JOIN donor dn ON d.donor_id = dn.donor_id
            LEFT JOIN blood_quality_check qc ON qc.check_id = (
                SELECT check_id FROM blood_quality_check 
                WHERE unit_id = u.unit_id 
                ORDER BY check_id DESC LIMIT 1
            )
            WHERE 1=1
        """
        params = []
        if status_filter:
            query += " AND u.status = ?"
            params.append(status_filter)
        if blood_group_filter:
            query += " AND u.blood_group = ?"
            params.append(blood_group_filter)

        query += " ORDER BY u.expiry_date ASC, u.unit_id ASC"
        cursor.execute(query, params)
        return [dict(row) for row in cursor.fetchall()]
    finally:
        conn.close()


# -----------------------------------------------------------------------------
# 3. QUALITY CHECK (INSPECTION HISTORY & CLEARANCE)
# -----------------------------------------------------------------------------
def record_quality_check(unit_id: int, checked_by: str, quality_status: str,
                         defect_detected: int = 0, abnormality_details: Optional[str] = None,
                         action_taken: str = "RELEASED", checked_on: Optional[str] = None) -> int:
    """
    Records an inspection in BLOOD_QUALITY_CHECK.
    Triggers automatically discard or quarantine unit if defects/failures occur.
    """
    check_date = checked_on or datetime.now().strftime("%Y-%m-%d")
    conn = get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("BEGIN IMMEDIATE")
        try:
            cursor.execute("SELECT status FROM blood_unit WHERE unit_id = ?", (unit_id,))
            unit = cursor.fetchone()
            if not unit:
                raise ValueError(f"Blood Unit #{unit_id} not found.")

            cursor.execute("""
                INSERT INTO blood_quality_check 
                (unit_id, checked_on, checked_by, quality_status, defect_detected, abnormality_details, action_taken)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (unit_id, check_date, checked_by.strip(), quality_status.strip().upper(),
                  defect_detected, abnormality_details, action_taken.strip().upper()))
            check_id = cursor.lastrowid
            conn.commit()
            return check_id
        except Exception:
            conn.rollback()
            raise
    finally:
        conn.close()


def get_quality_checks_for_unit(unit_id: int) -> List[Dict[str, Any]]:
    """Returns all historical quality checks for a blood unit."""
    conn = get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT * FROM blood_quality_check 
            WHERE unit_id = ? 
            ORDER BY check_id DESC
        """, (unit_id,))
        return [dict(row) for row in cursor.fetchall()]
    finally:
        conn.close()


# -----------------------------------------------------------------------------
# 4. HOSPITALS & BLOOD REQUESTS
# -----------------------------------------------------------------------------
def get_hospitals() -> List[Dict[str, Any]]:
    """Returns all hospitals."""
    conn = get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM hospital ORDER BY name ASC")
        return [dict(row) for row in cursor.fetchall()]
    finally:
        conn.close()


def register_hospital(name: str, city: str, phone: str) -> int:
    """Registers a hospital."""
    conn = get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("INSERT INTO hospital (name, city, phone) VALUES (?, ?, ?)",
                       (name.strip(), city.strip(), phone.strip()))
        return cursor.lastrowid
    finally:
        conn.close()


def get_blood_requests(status_filter: Optional[str] = None) -> List[Dict[str, Any]]:
    """Returns requests with hospital details and allocation progress."""
    conn = get_connection()
    try:
        cursor = conn.cursor()
        query = """
            SELECT 
                r.request_id,
                r.hospital_id,
                h.name as hospital_name,
                h.city as hospital_city,
                r.blood_group,
                r.units_needed,
                r.urgency,
                r.status,
                r.requested_on,
                COUNT(a.alloc_id) as units_allocated,
                (r.units_needed - COUNT(a.alloc_id)) as units_remaining
            FROM blood_request r
            JOIN hospital h ON r.hospital_id = h.hospital_id
            LEFT JOIN allocation a ON r.request_id = a.request_id
            WHERE 1=1
        """
        params = []
        if status_filter:
            query += " AND r.status = ?"
            params.append(status_filter)

        query += """
            GROUP BY r.request_id
            ORDER BY 
                CASE r.urgency 
                    WHEN 'CRITICAL' THEN 1 
                    WHEN 'URGENT' THEN 2 
                    ELSE 3 
                END ASC,
                r.request_id DESC
        """
        cursor.execute(query, params)
        return [dict(row) for row in cursor.fetchall()]
    finally:
        conn.close()


def create_blood_request(hospital_id: int, blood_group: str, units_needed: int, urgency: str = "NORMAL") -> int:
    """Creates a new blood request."""
    if units_needed <= 0:
        raise ValueError("Units needed must be greater than 0.")

    conn = get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO blood_request (hospital_id, blood_group, units_needed, urgency, status)
            VALUES (?, ?, ?, ?, 'PENDING')
        """, (hospital_id, blood_group.strip().upper(), units_needed, urgency.strip().upper()))
        return cursor.lastrowid
    finally:
        conn.close()


def cancel_blood_request(request_id: int):
    """Cancels a pending or partially fulfilled request."""
    conn = get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("UPDATE blood_request SET status = 'CANCELLED' WHERE request_id = ?", (request_id,))
    finally:
        conn.close()


# -----------------------------------------------------------------------------
# 5. SMART ALLOCATION ENGINE (Slides 4, 5, 8)
# FEFO Matching + Atomic Transaction with Concurrency Lock
# -----------------------------------------------------------------------------
def find_eligible_units_for_request(request_id: int) -> List[Dict[str, Any]]:
    """
    Implements Slide 8 FEFO matching query:
    1. Status should be AVAILABLE
    2. Expiry date must be later than today (expiry_date > DATE('now'))
    3. Blood group must be compatible with requested blood group
    4. Required quality checks should have passed and no unresolved holds must exist.
    """
    conn = get_connection()
    try:
        cursor = conn.cursor()
        # Fetch request blood group
        cursor.execute("SELECT blood_group FROM blood_request WHERE request_id = ?", (request_id,))
        req = cursor.fetchone()
        if not req:
            raise ValueError(f"Request #{request_id} not found.")

        req_group = req["blood_group"]

        query = """
            SELECT 
                u.unit_id, 
                u.blood_group, 
                u.expiry_date,
                d.donation_id,
                d.donated_on,
                d.volume_ml,
                CAST(ROUND(julianday(u.expiry_date) - julianday('now')) AS INTEGER) as days_to_expiry,
                c.recipient_group
            FROM blood_unit u
            JOIN compatibility c ON c.donor_group = u.blood_group
            JOIN donation d ON u.donation_id = d.donation_id
            WHERE c.recipient_group = ?
              AND u.status = 'AVAILABLE'
              AND u.expiry_date > DATE('now')
              -- Must have at least one quality check that PASSED
              AND EXISTS (
                  SELECT 1 FROM blood_quality_check qc
                  WHERE qc.unit_id = u.unit_id
                    AND qc.quality_status = 'PASSED'
              )
              -- And no unresolved holds or failures
              AND NOT EXISTS (
                  SELECT 1 FROM blood_quality_check qc
                  WHERE qc.unit_id = u.unit_id
                    AND (qc.quality_status != 'PASSED' OR qc.action_taken IN ('QUARANTINED', 'DISCARDED'))
              )
            ORDER BY u.expiry_date ASC, u.unit_id ASC;
        """
        cursor.execute(query, (req_group,))
        return [dict(row) for row in cursor.fetchall()]
    finally:
        conn.close()


def allocate_units(request_id: int, max_units: Optional[int] = None) -> Dict[str, Any]:
    """
    Executes transaction matching Slides 4 & 5:
    conn.execute("BEGIN IMMEDIATE")
    - Validates compatible, unexpired, quality-cleared units
    - Conditionally claims each unit with:
        UPDATE blood_unit SET status = 'ISSUED' WHERE unit_id = ? AND status = 'AVAILABLE';
      and requires rowcount == 1 (aborts on race condition)
    - Inserts allocation records
    - Commits on success, rolls back on any error
    """
    conn = get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("BEGIN IMMEDIATE")
        try:
            # 1. Validate request
            cursor.execute("SELECT blood_group, units_needed, status FROM blood_request WHERE request_id = ?", (request_id,))
            req = cursor.fetchone()
            if not req:
                raise ValueError(f"Request #{request_id} does not exist.")
            
            req_group = req["blood_group"]
            units_needed = req["units_needed"]
            req_status = req["status"]

            if req_status in ('FULFILLED', 'CANCELLED'):
                raise ValueError(f"Request #{request_id} is already {req_status}.")

            # 2. Check remaining needed
            cursor.execute("SELECT COUNT(*) FROM allocation WHERE request_id = ?", (request_id,))
            already_allocated = cursor.fetchone()[0]
            remaining_needed = units_needed - already_allocated
            if remaining_needed <= 0:
                cursor.execute("UPDATE blood_request SET status = 'FULFILLED' WHERE request_id = ?", (request_id,))
                conn.commit()
                return {"request_id": request_id, "allocated_units": [], "message": "Request already fully fulfilled."}

            limit = remaining_needed if max_units is None else min(remaining_needed, max_units)

            # 3. Query eligible FEFO units (Slide 8)
            fefo_query = """
                SELECT u.unit_id, u.blood_group, u.expiry_date
                FROM blood_unit u
                JOIN compatibility c ON c.donor_group = u.blood_group
                WHERE c.recipient_group = ?
                  AND u.status = 'AVAILABLE'
                  AND u.expiry_date > DATE('now')
                  AND EXISTS (
                      SELECT 1 FROM blood_quality_check qc
                      WHERE qc.unit_id = u.unit_id
                        AND qc.quality_status = 'PASSED'
                  )
                  AND NOT EXISTS (
                      SELECT 1 FROM blood_quality_check qc
                      WHERE qc.unit_id = u.unit_id
                        AND (qc.quality_status != 'PASSED' OR qc.action_taken IN ('QUARANTINED', 'DISCARDED'))
                  )
                ORDER BY u.expiry_date ASC, u.unit_id ASC
                LIMIT ?
            """
            cursor.execute(fefo_query, (req_group, limit))
            eligible = cursor.fetchall()

            if not eligible:
                conn.commit()
                return {
                    "request_id": request_id,
                    "allocated_units": [],
                    "allocated_count": 0,
                    "message": "No eligible compatible, unexpired, quality-cleared units currently available."
                }

            # 4. Atomic claim per unit with optimistic verification (Slide 5)
            allocated_records = []
            for unit in eligible:
                unit_id = unit["unit_id"]
                cursor.execute(
                    "UPDATE blood_unit SET status = 'ISSUED' WHERE unit_id = ? AND status = 'AVAILABLE'",
                    (unit_id,)
                )
                if cursor.rowcount != 1:
                    raise RuntimeError(f"Concurrency Conflict: Unit #{unit_id} was claimed concurrently. Rolling back transaction.")

                cursor.execute(
                    "INSERT INTO allocation (request_id, unit_id, allocated_on) VALUES (?, ?, datetime('now'))",
                    (request_id, unit_id)
                )
                allocated_records.append({
                    "unit_id": unit_id,
                    "blood_group": unit["blood_group"],
                    "expiry_date": unit["expiry_date"]
                })

            # Trigger trg_update_request_status_on_allocation will automatically update request status
            conn.commit()

            # Retrieve updated request status
            cursor.execute("SELECT status FROM blood_request WHERE request_id = ?", (request_id,))
            updated_status = cursor.fetchone()["status"]

            return {
                "request_id": request_id,
                "allocated_units": allocated_records,
                "allocated_count": len(allocated_records),
                "remaining_needed": units_needed - (already_allocated + len(allocated_records)),
                "request_status": updated_status,
                "message": f"Successfully allocated {len(allocated_records)} unit(s) using FEFO criteria."
            }
        except Exception:
            conn.rollback()
            raise
    finally:
        conn.close()


def get_allocations_for_request(request_id: int) -> List[Dict[str, Any]]:
    """Returns details of all units allocated to a specific request."""
    conn = get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT 
                a.alloc_id,
                a.allocated_on,
                u.unit_id,
                u.blood_group,
                u.expiry_date,
                d.donated_on,
                dn.full_name as donor_name
            FROM allocation a
            JOIN blood_unit u ON a.unit_id = u.unit_id
            JOIN donation d ON u.donation_id = d.donation_id
            JOIN donor dn ON d.donor_id = dn.donor_id
            WHERE a.request_id = ?
            ORDER BY a.allocated_on DESC
        """, (request_id,))
        return [dict(row) for row in cursor.fetchall()]
    finally:
        conn.close()


# -----------------------------------------------------------------------------
# 6. SLIDE 9 ANALYTICAL REPORTS & SUMMARY
# -----------------------------------------------------------------------------
def get_inventory_report() -> List[Dict[str, Any]]:
    """
    Inventory report: available units grouped by blood group.
    """
    conn = get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT 
                u.blood_group,
                COUNT(u.unit_id) as total_units,
                SUM(d.volume_ml) as total_volume_ml,
                MIN(u.expiry_date) as earliest_expiry,
                COUNT(CASE WHEN qc.quality_status = 'PASSED' THEN 1 END) as quality_cleared_units
            FROM blood_unit u
            JOIN donation d ON u.donation_id = d.donation_id
            LEFT JOIN blood_quality_check qc ON qc.check_id = (
                SELECT check_id FROM blood_quality_check 
                WHERE unit_id = u.unit_id 
                ORDER BY check_id DESC LIMIT 1
            )
            WHERE u.status = 'AVAILABLE'
              AND u.expiry_date > DATE('now')
            GROUP BY u.blood_group
            ORDER BY u.blood_group ASC
        """)
        return [dict(row) for row in cursor.fetchall()]
    finally:
        conn.close()


def get_expiry_report() -> List[Dict[str, Any]]:
    """
    Expiry report: eligible units approaching expiry prioritized using FEFO.
    Categorized into EXPIRED, CRITICAL (<= 3 days), APPROACHING (<= 7 days), and GOOD.
    """
    conn = get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT 
                u.unit_id,
                u.blood_group,
                u.expiry_date,
                u.status,
                d.donated_on,
                dn.full_name as donor_name,
                CAST(ROUND(julianday(u.expiry_date) - julianday('now')) AS INTEGER) as days_remaining,
                CASE 
                    WHEN julianday(u.expiry_date) <= julianday('now') THEN 'EXPIRED'
                    WHEN julianday(u.expiry_date) - julianday('now') <= 3 THEN 'CRITICAL (<=3 days)'
                    WHEN julianday(u.expiry_date) - julianday('now') <= 7 THEN 'APPROACHING (<=7 days)'
                    ELSE 'SAFE (>7 days)'
                END as urgency_category
            FROM blood_unit u
            JOIN donation d ON u.donation_id = d.donation_id
            JOIN donor dn ON d.donor_id = dn.donor_id
            WHERE u.status = 'AVAILABLE'
            ORDER BY u.expiry_date ASC, u.unit_id ASC
        """)
        return [dict(row) for row in cursor.fetchall()]
    finally:
        conn.close()


def get_quality_report() -> Dict[str, Any]:
    """
    Quality report: pending checks, failed checks, quarantined units, and action history.
    """
    conn = get_connection()
    try:
        cursor = conn.cursor()
        # Summary counts
        cursor.execute("""
            SELECT 
                (SELECT COUNT(*) FROM blood_unit u WHERE u.status = 'AVAILABLE' AND NOT EXISTS (
                    SELECT 1 FROM blood_quality_check qc WHERE qc.unit_id = u.unit_id
                )) as pending_initial_check,
                (SELECT COUNT(*) FROM blood_unit WHERE status = 'QUARANTINED') as quarantined_count,
                (SELECT COUNT(*) FROM blood_unit WHERE status = 'DISCARDED') as discarded_count,
                (SELECT COUNT(*) FROM blood_quality_check WHERE quality_status = 'PASSED') as total_passed_checks
        """)
        summary = dict(cursor.fetchone())

        # Detailed inspection log
        cursor.execute("""
            SELECT 
                qc.check_id,
                qc.unit_id,
                u.blood_group,
                u.status as unit_status,
                qc.checked_on,
                qc.checked_by,
                qc.quality_status,
                qc.defect_detected,
                qc.abnormality_details,
                qc.action_taken
            FROM blood_quality_check qc
            JOIN blood_unit u ON qc.unit_id = u.unit_id
            ORDER BY qc.check_id DESC
            LIMIT 50
        """)
        inspections = [dict(row) for row in cursor.fetchall()]
        summary["inspections"] = inspections
        return summary
    finally:
        conn.close()


def get_request_report() -> List[Dict[str, Any]]:
    """
    Request report: requested quantity compared with allocated quantity.
    """
    conn = get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT 
                r.request_id,
                h.name as hospital_name,
                h.city as hospital_city,
                r.blood_group,
                r.units_needed,
                COUNT(a.alloc_id) as units_allocated,
                (r.units_needed - COUNT(a.alloc_id)) as units_unfulfilled,
                ROUND((CAST(COUNT(a.alloc_id) AS REAL) / r.units_needed) * 100, 1) as fulfillment_percentage,
                r.urgency,
                r.status,
                r.requested_on
            FROM blood_request r
            JOIN hospital h ON r.hospital_id = h.hospital_id
            LEFT JOIN allocation a ON r.request_id = a.request_id
            GROUP BY r.request_id
            ORDER BY r.request_id DESC
        """)
        return [dict(row) for row in cursor.fetchall()]
    finally:
        conn.close()


def get_dashboard_stats() -> Dict[str, Any]:
    """Provides high-level KPI cards and stats for the dashboard."""
    conn = get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT 
                (SELECT COUNT(*) FROM blood_unit WHERE status = 'AVAILABLE' AND expiry_date > DATE('now')) as available_units,
                (SELECT COUNT(*) FROM blood_request WHERE status IN ('PENDING', 'PARTIALLY_FULFILLED')) as pending_requests,
                (SELECT COUNT(*) FROM donor) as total_donors,
                (SELECT COUNT(*) FROM blood_unit WHERE status = 'AVAILABLE' AND expiry_date > DATE('now') AND (julianday(expiry_date) - julianday('now')) <= 7) as nearing_expiry_count,
                (SELECT COUNT(*) FROM allocation) as total_allocations
        """)
        return dict(cursor.fetchone())
    finally:
        conn.close()


def get_compatibility_matrix() -> List[Dict[str, str]]:
    """Returns the full compatibility matrix."""
    conn = get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT recipient_group, donor_group FROM compatibility ORDER BY recipient_group, donor_group")
        return [dict(row) for row in cursor.fetchall()]
    finally:
        conn.close()
