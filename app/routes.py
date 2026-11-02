"""
Flask web server and REST API for Smart Blood Bank Management System.
Connects the UI to relational queries, transaction management, and reporting.

Author: Siddhesh Srinivasan (24BYB0035)
"""

from flask import Flask, render_template, request, jsonify
from app import queries
from seed_data import seed_database
from test_concurrency import run_concurrency_race_condition_test

app = Flask(__name__, template_folder="../templates", static_folder="../static")


# -----------------------------------------------------------------------------
# HTML PAGE ROUTE
# -----------------------------------------------------------------------------
@app.route("/")
def index():
    return render_template("index.html")


# -----------------------------------------------------------------------------
# REST API: DASHBOARD & STATS
# -----------------------------------------------------------------------------
@app.route("/api/stats", methods=["GET"])
def get_stats():
    return jsonify(queries.get_dashboard_stats())


# -----------------------------------------------------------------------------
# REST API: DONORS
# -----------------------------------------------------------------------------
@app.route("/api/donors", methods=["GET"])
def list_donors():
    return jsonify(queries.get_donors())


@app.route("/api/donors", methods=["POST"])
def add_donor():
    data = request.get_json() or {}
    try:
        full_name = data.get("full_name")
        blood_group = data.get("blood_group")
        phone = data.get("phone")
        if not full_name or not blood_group or not phone:
            return jsonify({"error": "Missing required fields"}), 400
        donor_id = queries.register_donor(full_name, blood_group, phone)
        return jsonify({"success": True, "donor_id": donor_id}), 201
    except Exception as e:
        return jsonify({"error": str(e)}), 400


@app.route("/api/donors/<int:donor_id>", methods=["GET"])
def get_donor(donor_id):
    details = queries.get_donor_details(donor_id)
    if not details:
        return jsonify({"error": "Donor not found"}), 404
    return jsonify(details)


# -----------------------------------------------------------------------------
# REST API: DONATIONS & BLOOD UNITS
# -----------------------------------------------------------------------------
@app.route("/api/donations", methods=["POST"])
def add_donation():
    data = request.get_json() or {}
    try:
        donor_id = int(data.get("donor_id"))
        volume_ml = int(data.get("volume_ml", 450))
        hb_level = float(data.get("hb_level", 13.5))
        donated_on = data.get("donated_on")
        shelf_life_days = int(data.get("shelf_life_days", 42))

        result = queries.record_donation(
            donor_id=donor_id,
            volume_ml=volume_ml,
            hb_level=hb_level,
            donated_on=donated_on,
            shelf_life_days=shelf_life_days
        )
        return jsonify({"success": True, "data": result}), 201
    except Exception as e:
        return jsonify({"error": str(e)}), 400


@app.route("/api/units", methods=["GET"])
def list_units():
    status = request.args.get("status")
    blood_group = request.args.get("blood_group")
    return jsonify(queries.get_blood_units(status_filter=status, blood_group_filter=blood_group))


# -----------------------------------------------------------------------------
# REST API: QUALITY INSPECTIONS (Slide 2 & 3)
# -----------------------------------------------------------------------------
@app.route("/api/quality-checks", methods=["POST"])
def add_quality_check():
    data = request.get_json() or {}
    try:
        unit_id = int(data.get("unit_id"))
        checked_by = data.get("checked_by", "Staff Pathologist")
        quality_status = data.get("quality_status", "PASSED")
        defect_detected = int(data.get("defect_detected", 0))
        abnormality_details = data.get("abnormality_details")
        action_taken = data.get("action_taken", "RELEASED")

        check_id = queries.record_quality_check(
            unit_id=unit_id,
            checked_by=checked_by,
            quality_status=quality_status,
            defect_detected=defect_detected,
            abnormality_details=abnormality_details,
            action_taken=action_taken
        )
        return jsonify({"success": True, "check_id": check_id}), 201
    except Exception as e:
        return jsonify({"error": str(e)}), 400


@app.route("/api/quality-checks/<int:unit_id>", methods=["GET"])
def get_unit_checks(unit_id):
    return jsonify(queries.get_quality_checks_for_unit(unit_id))


# -----------------------------------------------------------------------------
# REST API: HOSPITALS & REQUESTS
# -----------------------------------------------------------------------------
@app.route("/api/hospitals", methods=["GET"])
def list_hospitals():
    return jsonify(queries.get_hospitals())


@app.route("/api/hospitals", methods=["POST"])
def add_hospital():
    data = request.get_json() or {}
    try:
        name = data.get("name")
        city = data.get("city")
        phone = data.get("phone")
        if not name or not city or not phone:
            return jsonify({"error": "Missing required fields"}), 400
        hospital_id = queries.register_hospital(name, city, phone)
        return jsonify({"success": True, "hospital_id": hospital_id}), 201
    except Exception as e:
        return jsonify({"error": str(e)}), 400


@app.route("/api/requests", methods=["GET"])
def list_requests():
    status = request.args.get("status")
    return jsonify(queries.get_blood_requests(status_filter=status))


@app.route("/api/requests", methods=["POST"])
def add_request():
    data = request.get_json() or {}
    try:
        hospital_id = int(data.get("hospital_id"))
        blood_group = data.get("blood_group")
        units_needed = int(data.get("units_needed", 1))
        urgency = data.get("urgency", "NORMAL")

        request_id = queries.create_blood_request(hospital_id, blood_group, units_needed, urgency)
        return jsonify({"success": True, "request_id": request_id}), 201
    except Exception as e:
        return jsonify({"error": str(e)}), 400


@app.route("/api/requests/<int:request_id>/cancel", methods=["POST"])
def cancel_request_endpoint(request_id):
    try:
        queries.cancel_blood_request(request_id)
        return jsonify({"success": True})
    except Exception as e:
        return jsonify({"error": str(e)}), 400


# -----------------------------------------------------------------------------
# REST API: SMART ALLOCATION ENGINE (Slides 4, 5, 8)
# -----------------------------------------------------------------------------
@app.route("/api/requests/<int:request_id>/eligible-units", methods=["GET"])
def preview_eligible_units(request_id):
    try:
        units = queries.find_eligible_units_for_request(request_id)
        return jsonify({"request_id": request_id, "eligible_units": units})
    except Exception as e:
        return jsonify({"error": str(e)}), 400


@app.route("/api/requests/<int:request_id>/allocate", methods=["POST"])
def execute_allocation(request_id):
    data = request.get_json() or {}
    max_units = data.get("max_units")
    if max_units is not None:
        max_units = int(max_units)
    try:
        result = queries.allocate_units(request_id, max_units=max_units)
        return jsonify({"success": True, "data": result})
    except Exception as e:
        return jsonify({"error": str(e)}), 400


@app.route("/api/requests/<int:request_id>/allocations", methods=["GET"])
def get_request_allocations(request_id):
    return jsonify(queries.get_allocations_for_request(request_id))


# -----------------------------------------------------------------------------
# REST API: SLIDE 9 REPORTS
# -----------------------------------------------------------------------------
@app.route("/api/reports/inventory", methods=["GET"])
def report_inventory():
    return jsonify(queries.get_inventory_report())


@app.route("/api/reports/expiry", methods=["GET"])
def report_expiry():
    return jsonify(queries.get_expiry_report())


@app.route("/api/reports/quality", methods=["GET"])
def report_quality():
    return jsonify(queries.get_quality_report())


@app.route("/api/reports/requests", methods=["GET"])
def report_requests():
    return jsonify(queries.get_request_report())


@app.route("/api/compatibility", methods=["GET"])
def report_compatibility():
    return jsonify(queries.get_compatibility_matrix())


# -----------------------------------------------------------------------------
# REST API: CONCURRENCY TEST & RESET
# -----------------------------------------------------------------------------
@app.route("/api/concurrency-test", methods=["POST"])
def run_concurrency_test():
    try:
        report = run_concurrency_race_condition_test()
        return jsonify({"success": True, "report": report})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/reset-seed", methods=["POST"])
def reset_seed():
    try:
        seed_database()
        return jsonify({"success": True, "message": "Database reset and seeded successfully!"})
    except Exception as e:
        return jsonify({"error": str(e)}), 500
