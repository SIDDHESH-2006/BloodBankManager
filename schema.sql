-- ============================================================================
-- DATABASE SYSTEMS COURSE PROJECT | REVIEW 2
-- Smart Blood Bank Management System
-- Presented by: Siddhesh Srinivasan (24BYB0035)
-- Under the guidance of: Dr. Thanga Mariappan L
-- Relational Schema (3NF Normalization, Referential Integrity & Constraints)
-- ============================================================================

PRAGMA foreign_keys = ON;

-- ----------------------------------------------------------------------------
-- 1. DONOR
-- ----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS donor (
    donor_id INTEGER PRIMARY KEY AUTOINCREMENT,
    full_name TEXT NOT NULL,
    blood_group TEXT NOT NULL CHECK(blood_group IN ('A+', 'A-', 'B+', 'B-', 'AB+', 'AB-', 'O+', 'O-')),
    phone TEXT NOT NULL,
    last_donated DATE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- ----------------------------------------------------------------------------
-- 2. DONATION (1:N from DONOR)
-- ----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS donation (
    donation_id INTEGER PRIMARY KEY AUTOINCREMENT,
    donor_id INTEGER NOT NULL REFERENCES donor(donor_id) ON DELETE RESTRICT,
    donated_on DATE NOT NULL DEFAULT (DATE('now')),
    volume_ml INTEGER NOT NULL CHECK(volume_ml > 0),
    hb_level REAL NOT NULL CHECK(hb_level >= 12.0),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- ----------------------------------------------------------------------------
-- 3. BLOOD_UNIT (1:N from DONATION)
-- ----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS blood_unit (
    unit_id INTEGER PRIMARY KEY AUTOINCREMENT,
    donation_id INTEGER NOT NULL REFERENCES donation(donation_id) ON DELETE RESTRICT,
    blood_group TEXT NOT NULL CHECK(blood_group IN ('A+', 'A-', 'B+', 'B-', 'AB+', 'AB-', 'O+', 'O-')),
    expiry_date DATE NOT NULL,
    status TEXT NOT NULL DEFAULT 'AVAILABLE' CHECK(status IN ('AVAILABLE', 'ISSUED', 'EXPIRED', 'DISCARDED', 'QUARANTINED')),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- ----------------------------------------------------------------------------
-- 4. BLOOD_QUALITY_CHECK (1:N from BLOOD_UNIT)
-- Stores repeatable inspection history; failed or unresolved checks block release.
-- ----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS blood_quality_check (
    check_id INTEGER PRIMARY KEY AUTOINCREMENT,
    unit_id INTEGER NOT NULL REFERENCES blood_unit(unit_id) ON DELETE CASCADE,
    checked_on DATE NOT NULL DEFAULT (DATE('now')),
    checked_by TEXT NOT NULL,
    quality_status TEXT NOT NULL CHECK(quality_status IN ('PASSED', 'FAILED', 'PENDING')),
    defect_detected INTEGER NOT NULL DEFAULT 0 CHECK(defect_detected IN (0, 1)),
    abnormality_details TEXT,
    action_taken TEXT NOT NULL DEFAULT 'RELEASED' CHECK(action_taken IN ('RELEASED', 'QUARANTINED', 'DISCARDED', 'RETEST_REQUIRED')),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- ----------------------------------------------------------------------------
-- 5. HOSPITAL
-- ----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS hospital (
    hospital_id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    city TEXT NOT NULL,
    phone TEXT NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- ----------------------------------------------------------------------------
-- 6. BLOOD_REQUEST (1:N from HOSPITAL)
-- ----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS blood_request (
    request_id INTEGER PRIMARY KEY AUTOINCREMENT,
    hospital_id INTEGER NOT NULL REFERENCES hospital(hospital_id) ON DELETE RESTRICT,
    blood_group TEXT NOT NULL CHECK(blood_group IN ('A+', 'A-', 'B+', 'B-', 'AB+', 'AB-', 'O+', 'O-')),
    units_needed INTEGER NOT NULL CHECK(units_needed > 0),
    urgency TEXT NOT NULL DEFAULT 'NORMAL' CHECK(urgency IN ('CRITICAL', 'URGENT', 'NORMAL')),
    status TEXT NOT NULL DEFAULT 'PENDING' CHECK(status IN ('PENDING', 'PARTIALLY_FULFILLED', 'FULFILLED', 'CANCELLED')),
    requested_on TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- ----------------------------------------------------------------------------
-- 7. ALLOCATION (1:N from BLOOD_REQUEST, 1:1 from BLOOD_UNIT)
-- ----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS allocation (
    alloc_id INTEGER PRIMARY KEY AUTOINCREMENT,
    request_id INTEGER NOT NULL REFERENCES blood_request(request_id) ON DELETE RESTRICT,
    unit_id INTEGER NOT NULL UNIQUE REFERENCES blood_unit(unit_id) ON DELETE RESTRICT,
    allocated_on TIMESTAMP DEFAULT CURRENT_TIMESTAMP NOT NULL
);

-- ----------------------------------------------------------------------------
-- 8. COMPATIBILITY (Composite Primary Key)
-- ----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS compatibility (
    recipient_group TEXT NOT NULL CHECK(recipient_group IN ('A+', 'A-', 'B+', 'B-', 'AB+', 'AB-', 'O+', 'O-')),
    donor_group TEXT NOT NULL CHECK(donor_group IN ('A+', 'A-', 'B+', 'B-', 'AB+', 'AB-', 'O+', 'O-')),
    PRIMARY KEY (recipient_group, donor_group)
);

-- ----------------------------------------------------------------------------
-- INDEXES FOR PERFORMANCE & FEFO OPTIMIZATION
-- ----------------------------------------------------------------------------
CREATE INDEX IF NOT EXISTS idx_blood_unit_status_expiry ON blood_unit(status, expiry_date);
CREATE INDEX IF NOT EXISTS idx_blood_unit_group_status ON blood_unit(blood_group, status);
CREATE INDEX IF NOT EXISTS idx_blood_quality_unit ON blood_quality_check(unit_id, checked_on);
CREATE INDEX IF NOT EXISTS idx_blood_request_status_urgency ON blood_request(status, urgency);
CREATE INDEX IF NOT EXISTS idx_allocation_request ON allocation(request_id);
CREATE INDEX IF NOT EXISTS idx_donation_donor ON donation(donor_id);

-- ----------------------------------------------------------------------------
-- TRIGGERS FOR DATA INTEGRITY (Slide 9)
-- ----------------------------------------------------------------------------

-- Trigger 1: Automatically update donor's last_donated date on new donation
CREATE TRIGGER IF NOT EXISTS trg_update_donor_last_donated
AFTER INSERT ON donation
BEGIN
    UPDATE donor
    SET last_donated = NEW.donated_on
    WHERE donor_id = NEW.donor_id;
END;

-- Trigger 2: Keep unit status in sync with allocation insertion
CREATE TRIGGER IF NOT EXISTS trg_sync_unit_status_on_allocation
AFTER INSERT ON allocation
BEGIN
    UPDATE blood_unit
    SET status = 'ISSUED'
    WHERE unit_id = NEW.unit_id;
END;

-- Trigger 3: Prevent allocation of ineligible or unverified blood units
CREATE TRIGGER IF NOT EXISTS trg_prevent_ineligible_allocation
BEFORE INSERT ON allocation
BEGIN
    -- Check 1: Unit must not be expired
    SELECT CASE
        WHEN (SELECT expiry_date FROM blood_unit WHERE unit_id = NEW.unit_id) <= DATE('now')
        THEN RAISE(ABORT, 'Integrity Violation: Cannot allocate an expired blood unit')
    END;

    -- Check 2: Unit must have at least one PASSED quality check
    SELECT CASE
        WHEN NOT EXISTS (
            SELECT 1 FROM blood_quality_check
            WHERE unit_id = NEW.unit_id AND quality_status = 'PASSED'
        )
        THEN RAISE(ABORT, 'Integrity Violation: Blood unit has not passed mandatory quality check')
    END;

    -- Check 3: Unit must NOT have any failed or quarantined quality check
    SELECT CASE
        WHEN EXISTS (
            SELECT 1 FROM blood_quality_check
            WHERE unit_id = NEW.unit_id AND (quality_status != 'PASSED' OR action_taken IN ('QUARANTINED', 'DISCARDED'))
        )
        THEN RAISE(ABORT, 'Integrity Violation: Blood unit has an active hold or failed quality inspection')
    END;
END;

-- Trigger 4: Update request status on allocation
CREATE TRIGGER IF NOT EXISTS trg_update_request_status_on_allocation
AFTER INSERT ON allocation
BEGIN
    UPDATE blood_request
    SET status = CASE
        WHEN (SELECT COUNT(*) FROM allocation WHERE request_id = NEW.request_id) >= (SELECT units_needed FROM blood_request WHERE request_id = NEW.request_id)
        THEN 'FULFILLED'
        ELSE 'PARTIALLY_FULFILLED'
    END
    WHERE request_id = NEW.request_id;
END;

-- Trigger 5: Sync unit status when a quality check fails or quarantines
CREATE TRIGGER IF NOT EXISTS trg_sync_unit_status_on_quality_check
AFTER INSERT ON blood_quality_check
BEGIN
    UPDATE blood_unit
    SET status = CASE
        WHEN NEW.quality_status = 'FAILED' OR NEW.action_taken = 'DISCARDED' THEN 'DISCARDED'
        WHEN NEW.action_taken = 'QUARANTINED' THEN 'QUARANTINED'
        ELSE status
    END
    WHERE unit_id = NEW.unit_id;
END;
