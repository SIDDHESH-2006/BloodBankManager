// Smart Blood Bank Management System - Frontend Controller
// Author: Siddhesh Srinivasan (24BYB0035)

let selectedRequestId = null;
let currentPendingRequests = [];

// Initialize on page load
document.addEventListener("DOMContentLoaded", () => {
  loadDashboardData();
  loadUnitsTable();
  loadDonors();
  loadHospitals();
  loadQualityUnitsDropdown();
  loadQualityHistory();
  loadSlide9Reports();
});

// -----------------------------------------------------------------------------
// TAB NAVIGATION
// -----------------------------------------------------------------------------
function switchTab(tabName) {
  document.querySelectorAll(".tab-view").forEach(el => el.classList.add("hidden"));
  document.querySelectorAll("header button[id^='tab-btn-']").forEach(btn => {
    btn.classList.remove("tab-active", "border-b-2", "border-brand-500");
  });

  const targetView = document.getElementById(`view-${tabName}`);
  const targetBtn = document.getElementById(`tab-btn-${tabName}`);

  if (targetView) targetView.classList.remove("hidden");
  if (targetBtn) targetBtn.classList.add("tab-active");

  lucide.createIcons();

  if (tabName === "allocation") {
    loadPendingRequestsForAllocation();
  } else if (tabName === "quality") {
    loadQualityUnitsDropdown();
    loadQualityHistory();
  } else if (tabName === "donors") {
    loadDonors();
  } else if (tabName === "requests") {
    loadRequestsTable();
    loadHospitals();
  } else if (tabName === "reports") {
    loadSlide9Reports();
  } else if (tabName === "dashboard") {
    loadDashboardData();
    loadUnitsTable();
  }
}

function switchReportTab(reportId) {
  document.querySelectorAll(".report-section").forEach(el => el.classList.add("hidden"));
  document.querySelectorAll("button[id^='rep-btn-']").forEach(btn => {
    btn.classList.remove("border-brand-600", "text-brand-600");
    btn.classList.add("border-transparent", "text-slate-500");
  });

  const section = document.getElementById(reportId);
  const btn = document.getElementById(reportId.replace("rep-", "rep-btn-"));

  if (section) section.classList.remove("hidden");
  if (btn) {
    btn.classList.remove("border-transparent", "text-slate-500");
    btn.classList.add("border-brand-600", "text-brand-600");
  }
}

// -----------------------------------------------------------------------------
// 1. DASHBOARD & INVENTORY
// -----------------------------------------------------------------------------
async function loadDashboardData() {
  try {
    const res = await fetch("/api/stats");
    const stats = await res.json();

    document.getElementById("stat-available-units").textContent = stats.available_units ?? 0;
    document.getElementById("stat-pending-requests").textContent = stats.pending_requests ?? 0;
    document.getElementById("stat-total-donors").textContent = stats.total_donors ?? 0;
    document.getElementById("stat-nearing-expiry").textContent = stats.nearing_expiry_count ?? 0;
    document.getElementById("stat-total-allocations").textContent = stats.total_allocations ?? 0;

    await loadInventory();
  } catch (err) {
    console.error("Error loading dashboard data:", err);
  }
}

async function loadInventory() {
  try {
    const res = await fetch("/api/reports/inventory");
    const data = await res.json();
    const container = document.getElementById("blood-group-cards-container");
    container.innerHTML = "";

    const allGroups = ["O+", "O-", "A+", "A-", "B+", "B-", "AB+", "AB-"];
    const stockMap = {};
    data.forEach(item => {
      stockMap[item.blood_group] = item;
    });

    allGroups.forEach(grp => {
      const item = stockMap[grp] || { total_units: 0, total_volume_ml: 0 };
      const isLow = item.total_units === 0;
      const isUniversal = grp === "O-" ? "Universal Donor" : grp === "AB+" ? "Universal Recipient" : "";

      const card = document.createElement("div");
      card.className = `p-3 rounded-xl border text-center transition ${isLow ? 'bg-red-50/50 border-red-200' : 'bg-white border-slate-200 shadow-sm'}`;
      card.innerHTML = `
        <div class="text-xs font-bold text-brand-700 flex justify-between items-center px-1">
          <span class="text-base">${grp}</span>
          ${isUniversal ? `<span class="text-[9px] px-1 py-0.5 rounded bg-brand-100 text-brand-800">${isUniversal.split(" ")[0]}</span>` : ''}
        </div>
        <div class="text-2xl font-black text-slate-900 my-1">${item.total_units} <span class="text-xs font-normal text-slate-500">units</span></div>
        <div class="text-[11px] text-slate-500">${item.total_volume_ml || 0} mL</div>
      `;
      container.appendChild(card);
    });
  } catch (err) {
    console.error("Error loading inventory:", err);
  }
}

async function loadUnitsTable() {
  const status = document.getElementById("unit-filter-status").value;
  const bloodGroup = document.getElementById("unit-filter-group").value;
  const tbody = document.getElementById("units-table-body");
  tbody.innerHTML = `<tr><td colspan="9" class="text-center py-4 text-slate-400">Loading units...</td></tr>`;

  try {
    const params = new URLSearchParams();
    if (status) params.append("status", status);
    if (bloodGroup) params.append("blood_group", bloodGroup);

    const res = await fetch(`/api/units?${params.toString()}`);
    const units = await res.json();

    if (!units || units.length === 0) {
      tbody.innerHTML = `<tr><td colspan="9" class="text-center py-4 text-slate-400">No matching blood units found.</td></tr>`;
      return;
    }

    tbody.innerHTML = "";
    units.forEach(u => {
      const days = u.days_to_expiry;
      let countdownBadge = "";
      if (u.status !== "AVAILABLE") {
        countdownBadge = `<span class="px-2 py-0.5 rounded text-[10px] bg-slate-100 text-slate-600">N/A</span>`;
      } else if (days <= 0) {
        countdownBadge = `<span class="px-2 py-0.5 rounded text-[10px] bg-red-100 text-red-800 font-bold">Expired</span>`;
      } else if (days <= 3) {
        countdownBadge = `<span class="px-2 py-0.5 rounded text-[10px] bg-red-100 text-red-800 font-bold">${days}d (Critical)</span>`;
      } else if (days <= 7) {
        countdownBadge = `<span class="px-2 py-0.5 rounded text-[10px] bg-amber-100 text-amber-800 font-medium">${days}d (Nearing)</span>`;
      } else {
        countdownBadge = `<span class="px-2 py-0.5 rounded text-[10px] bg-emerald-100 text-emerald-800 font-medium">${days} days</span>`;
      }

      let qcBadge = "";
      if (u.latest_quality_status === "PASSED") {
        qcBadge = `<span class="px-1.5 py-0.5 rounded text-[10px] bg-emerald-100 text-emerald-800 font-semibold">PASSED</span>`;
      } else if (u.latest_quality_status === "FAILED") {
        qcBadge = `<span class="px-1.5 py-0.5 rounded text-[10px] bg-red-100 text-red-800 font-semibold">FAILED</span>`;
      } else if (u.latest_quality_status === "PENDING") {
        qcBadge = `<span class="px-1.5 py-0.5 rounded text-[10px] bg-amber-100 text-amber-800 font-semibold">PENDING</span>`;
      } else {
        qcBadge = `<span class="px-1.5 py-0.5 rounded text-[10px] bg-slate-100 text-slate-500">UNCHECKED</span>`;
      }

      const tr = document.createElement("tr");
      tr.className = "hover:bg-slate-50 transition";
      tr.innerHTML = `
        <td class="py-2 px-3 font-mono font-bold text-slate-800">#${u.unit_id}</td>
        <td class="py-2 px-3 font-bold text-brand-700">${u.blood_group}</td>
        <td class="py-2 px-3 text-slate-700">${u.donor_name}</td>
        <td class="py-2 px-3 text-slate-600">${u.donated_on}</td>
        <td class="py-2 px-3 text-slate-600">${u.volume_ml} mL</td>
        <td class="py-2 px-3 font-mono text-slate-700">${u.expiry_date}</td>
        <td class="py-2 px-3">${countdownBadge}</td>
        <td class="py-2 px-3">${qcBadge}</td>
        <td class="py-2 px-3"><span class="px-2 py-0.5 rounded text-[10px] font-bold badge-${u.status.toLowerCase()}">${u.status}</span></td>
      `;
      tbody.appendChild(tr);
    });
  } catch (err) {
    console.error("Error loading units table:", err);
  }
}

// -----------------------------------------------------------------------------
// 2. SMART ALLOCATION ENGINE (Slides 4, 5, 8)
// -----------------------------------------------------------------------------
async function loadPendingRequestsForAllocation() {
  const container = document.getElementById("allocation-requests-list");
  container.innerHTML = `<div class="p-4 text-center text-slate-400 text-xs">Loading requests...</div>`;

  try {
    const res = await fetch("/api/requests");
    const requests = await res.json();
    currentPendingRequests = requests.filter(r => r.status === "PENDING" || r.status === "PARTIALLY_FULFILLED");

    if (currentPendingRequests.length === 0) {
      container.innerHTML = `<div class="p-6 text-center text-slate-400 text-xs bg-slate-50 rounded-lg">No pending blood requests. All hospitals fulfilled!</div>`;
      return;
    }

    container.innerHTML = "";
    currentPendingRequests.forEach(req => {
      const card = document.createElement("div");
      card.id = `req-card-${req.request_id}`;
      card.className = `p-3 rounded-lg border cursor-pointer transition ${selectedRequestId === req.request_id ? 'border-brand-600 bg-brand-50' : 'border-slate-200 bg-white hover:bg-slate-50'}`;
      card.onclick = () => selectRequestForAllocation(req.request_id);

      card.innerHTML = `
        <div class="flex justify-between items-center">
          <span class="text-[10px] font-bold px-1.5 py-0.5 rounded uppercase badge-${req.urgency.toLowerCase()}">${req.urgency}</span>
          <span class="text-xs text-slate-500 font-mono">Req #${req.request_id}</span>
        </div>
        <div class="font-bold text-slate-900 text-xs mt-1">${req.hospital_name} (${req.hospital_city})</div>
        <div class="flex justify-between items-center text-xs mt-1.5 text-slate-600">
          <span>Blood Group: <strong class="text-brand-700">${req.blood_group}</strong></span>
          <span>Needed: <strong class="text-slate-900">${req.units_remaining}</strong> / ${req.units_needed}</span>
        </div>
      `;
      container.appendChild(card);
    });

    if (selectedRequestId) {
      selectRequestForAllocation(selectedRequestId);
    } else if (currentPendingRequests.length > 0) {
      selectRequestForAllocation(currentPendingRequests[0].request_id);
    }
  } catch (err) {
    console.error("Error loading requests for allocation:", err);
  }
}

async function selectRequestForAllocation(requestId) {
  selectedRequestId = requestId;
  const req = currentPendingRequests.find(r => r.request_id === requestId);
  if (!req) return;

  // Highlight card
  document.querySelectorAll("[id^='req-card-']").forEach(el => {
    el.classList.remove("border-brand-600", "bg-brand-50");
    el.classList.add("border-slate-200", "bg-white");
  });
  const activeCard = document.getElementById(`req-card-${requestId}`);
  if (activeCard) {
    activeCard.classList.remove("border-slate-200", "bg-white");
    activeCard.classList.add("border-brand-600", "bg-brand-50");
  }

  document.getElementById("allocation-empty-state").classList.add("hidden");
  const detailsCard = document.getElementById("allocation-details-card");
  detailsCard.classList.remove("hidden");

  document.getElementById("alloc-detail-urgency").textContent = req.urgency;
  document.getElementById("alloc-detail-urgency").className = `text-[10px] font-bold px-2 py-0.5 rounded uppercase badge-${req.urgency.toLowerCase()}`;
  document.getElementById("alloc-detail-hospital").textContent = req.hospital_name;
  document.getElementById("alloc-detail-sub").innerHTML = `Request #${req.request_id} &bull; Recipient Group: <strong class="text-brand-600">${req.blood_group}</strong>`;
  document.getElementById("alloc-detail-group").textContent = req.blood_group;
  document.getElementById("alloc-detail-units").textContent = req.units_remaining;

  // Hide past log
  document.getElementById("alloc-transaction-log").classList.add("hidden");

  // Fetch eligible units (Slide 8 FEFO)
  try {
    const res = await fetch(`/api/requests/${requestId}/eligible-units`);
    const data = await res.json();
    const eligibleUnits = data.eligible_units || [];

    document.getElementById("alloc-compatible-count").textContent = `${eligibleUnits.length} compatible unit(s) found`;
    const tbody = document.getElementById("alloc-eligible-table-body");
    tbody.innerHTML = "";

    if (eligibleUnits.length === 0) {
      tbody.innerHTML = `<tr><td colspan="5" class="py-4 text-center text-slate-400">No compatible, unexpired, quality-cleared units available in inventory.</td></tr>`;
      document.getElementById("btn-execute-allocation").disabled = true;
      document.getElementById("btn-execute-allocation").classList.add("opacity-50", "cursor-not-allowed");
    } else {
      document.getElementById("btn-execute-allocation").disabled = false;
      document.getElementById("btn-execute-allocation").classList.remove("opacity-50", "cursor-not-allowed");

      eligibleUnits.forEach((u, idx) => {
        const tr = document.createElement("tr");
        tr.className = idx === 0 ? "bg-emerald-50/60 font-semibold" : "";
        tr.innerHTML = `
          <td class="py-2 px-3 font-mono">#${u.unit_id}</td>
          <td class="py-2 px-3 text-brand-700">${u.blood_group}</td>
          <td class="py-2 px-3 font-mono">${u.expiry_date}</td>
          <td class="py-2 px-3">${u.days_to_expiry} days remaining</td>
          <td class="py-2 px-3">
            ${idx === 0 ? '<span class="px-2 py-0.5 rounded text-[10px] bg-emerald-600 text-white font-bold">1st Priority (FEFO)</span>' : `<span class="text-slate-500">Priority #${idx + 1}</span>`}
          </td>
        `;
        tbody.appendChild(tr);
      });
    }

    // Load past allocations
    const allocRes = await fetch(`/api/requests/${requestId}/allocations`);
    const pastAllocs = await allocRes.json();
    const pastContainer = document.getElementById("past-allocations-list");
    if (!pastAllocs || pastAllocs.length === 0) {
      pastContainer.innerHTML = `<span class="text-slate-400 italic">None yet.</span>`;
    } else {
      pastContainer.innerHTML = pastAllocs.map(a => `
        <div class="flex justify-between items-center bg-slate-50 p-2 rounded border border-slate-200">
          <span>Unit #${a.unit_id} (${a.blood_group}) - Donor: ${a.donor_name}</span>
          <span class="font-mono text-slate-400">${a.allocated_on}</span>
        </div>
      `).join("");
    }
  } catch (err) {
    console.error("Error fetching eligible units:", err);
  }
}

async function submitAllocation() {
  if (!selectedRequestId) return;
  const btn = document.getElementById("btn-execute-allocation");
  btn.disabled = true;
  btn.innerHTML = `<i data-lucide="loader-2" class="w-4 h-4 animate-spin"></i> Executing Atomic Transaction...`;
  lucide.createIcons();

  try {
    const res = await fetch(`/api/requests/${selectedRequestId}/allocate`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({})
    });
    const result = await res.json();

    const logPanel = document.getElementById("alloc-transaction-log");
    const logContent = document.getElementById("alloc-log-content");
    logPanel.classList.remove("hidden");

    if (result.success) {
      const data = result.data;
      logContent.innerHTML = `
        &gt; conn.execute("BEGIN IMMEDIATE") [Acquired SQLite WAL Exclusive Write Lock]<br>
        &gt; Evaluated Slide 8 FEFO matching: Checked compatibility, expiry &gt; DATE('now'), quality clearance.<br>
        &gt; Claimed ${data.allocated_count} unit(s): ${data.allocated_units.map(u => `#${u.unit_id} (${u.blood_group})`).join(", ")}<br>
        &gt; Verified rowcount == 1 on conditional UPDATE for each unit.<br>
        &gt; Inserted into ALLOCATION; Trigger updated request status to '${data.request_status}'.<br>
        &gt; conn.commit() SUCCESSFUL! (ACID Guarantee: Atomicity + Isolation Verified)
      `;
      await loadDashboardData();
      await loadPendingRequestsForAllocation();
      await loadUnitsTable();
    } else {
      logContent.innerHTML = `<span class="text-red-400">&gt; TRANSACTION ABORTED &amp; ROLLED BACK: ${result.error}</span>`;
    }
  } catch (err) {
    alert("Allocation error: " + err);
  } finally {
    btn.disabled = false;
    btn.innerHTML = `<i data-lucide="check-check" class="w-4 h-4"></i> Commit Atomic Allocation (BEGIN IMMEDIATE)`;
    lucide.createIcons();
  }
}

// -----------------------------------------------------------------------------
// 3. QUALITY LAB CLEARANCE
// -----------------------------------------------------------------------------
async function loadQualityUnitsDropdown() {
  try {
    const res = await fetch("/api/units");
    const units = await res.json();
    const select = document.getElementById("qc-unit-id");
    select.innerHTML = `<option value="">Select blood unit to inspect...</option>`;

    units.forEach(u => {
      const opt = document.createElement("option");
      opt.value = u.unit_id;
      opt.textContent = `Unit #${u.unit_id} (${u.blood_group}) - Donor: ${u.donor_name} [${u.status}]`;
      select.appendChild(opt);
    });
  } catch (err) {
    console.error("Error loading quality units dropdown:", err);
  }
}

async function loadQualityHistory() {
  try {
    const res = await fetch("/api/reports/quality");
    const report = await res.json();
    const tbody = document.getElementById("qc-history-table-body");
    tbody.innerHTML = "";

    const inspections = report.inspections || [];
    if (inspections.length === 0) {
      tbody.innerHTML = `<tr><td colspan="6" class="text-center py-4 text-slate-400">No inspection records.</td></tr>`;
      return;
    }

    inspections.forEach(item => {
      const tr = document.createElement("tr");
      tr.innerHTML = `
        <td class="py-2 px-3 font-mono font-bold">#${item.unit_id} (${item.blood_group})</td>
        <td class="py-2 px-3 font-mono text-slate-600">${item.checked_on}</td>
        <td class="py-2 px-3 text-slate-700">${item.checked_by}</td>
        <td class="py-2 px-3">
          <span class="px-2 py-0.5 rounded text-[10px] font-bold ${item.quality_status === 'PASSED' ? 'bg-emerald-100 text-emerald-800' : 'bg-red-100 text-red-800'}">
            ${item.quality_status}
          </span>
        </td>
        <td class="py-2 px-3">
          <span class="px-2 py-0.5 rounded text-[10px] font-semibold ${item.action_taken === 'RELEASED' ? 'bg-emerald-50 text-emerald-700' : 'bg-amber-100 text-amber-800'}">
            ${item.action_taken}
          </span>
        </td>
        <td class="py-2 px-3 text-slate-500">${item.abnormality_details || 'Morphology clear'}</td>
      `;
      tbody.appendChild(tr);
    });
  } catch (err) {
    console.error("Error loading quality history:", err);
  }
}

async function submitQualityCheck(e) {
  e.preventDefault();
  const unitId = document.getElementById("qc-unit-id").value;
  const checkedBy = document.getElementById("qc-checked-by").value;
  const status = document.getElementById("qc-status").value;
  const action = document.getElementById("qc-action").value;
  const defect = document.getElementById("qc-defect").value;
  const notes = document.getElementById("qc-notes").value;

  try {
    const res = await fetch("/api/quality-checks", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        unit_id: unitId,
        checked_by: checkedBy,
        quality_status: status,
        defect_detected: parseInt(defect),
        abnormality_details: notes,
        action_taken: action
      })
    });
    const data = await res.json();
    if (data.success) {
      alert(`Quality inspection #${data.check_id} recorded! Trigger automatically synced blood unit status.`);
      document.getElementById("qc-notes").value = "";
      await loadQualityHistory();
      await loadUnitsTable();
      await loadDashboardData();
    } else {
      alert("Error: " + data.error);
    }
  } catch (err) {
    alert("Network error: " + err);
  }
}

// -----------------------------------------------------------------------------
// 4. DONORS & DONATIONS
// -----------------------------------------------------------------------------
async function loadDonors() {
  try {
    const res = await fetch("/api/donors");
    const donors = await res.json();
    const tbody = document.getElementById("donors-table-body");
    const donationSelect = document.getElementById("donation-donor-id");

    tbody.innerHTML = "";
    donationSelect.innerHTML = `<option value="">Select donor...</option>`;

    donors.forEach(d => {
      const tr = document.createElement("tr");
      tr.innerHTML = `
        <td class="py-2 px-3 font-mono text-slate-700">#${d.donor_id}</td>
        <td class="py-2 px-3 font-bold text-slate-900">${d.full_name}</td>
        <td class="py-2 px-3 font-bold text-brand-700">${d.blood_group}</td>
        <td class="py-2 px-3 text-slate-600">${d.phone}</td>
        <td class="py-2 px-3 font-mono text-slate-600">${d.last_donated || 'Never'}</td>
        <td class="py-2 px-3 text-slate-700 font-semibold">${d.total_donations}</td>
      `;
      tbody.appendChild(tr);

      const opt = document.createElement("option");
      opt.value = d.donor_id;
      opt.textContent = `${d.full_name} (${d.blood_group}) - Last: ${d.last_donated || 'Never'}`;
      donationSelect.appendChild(opt);
    });
  } catch (err) {
    console.error("Error loading donors:", err);
  }
}

async function submitRegisterDonor(e) {
  e.preventDefault();
  const name = document.getElementById("donor-name").value;
  const group = document.getElementById("donor-group").value;
  const phone = document.getElementById("donor-phone").value;

  try {
    const res = await fetch("/api/donors", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ full_name: name, blood_group: group, phone })
    });
    const data = await res.json();
    if (data.success) {
      alert(`Donor #${data.donor_id} (${name}) registered successfully!`);
      document.getElementById("donor-name").value = "";
      document.getElementById("donor-phone").value = "";
      await loadDonors();
      await loadDashboardData();
    } else {
      alert("Error: " + data.error);
    }
  } catch (err) {
    alert("Error: " + err);
  }
}

async function submitRecordDonation(e) {
  e.preventDefault();
  const donorId = document.getElementById("donation-donor-id").value;
  const volume = document.getElementById("donation-volume").value;
  const hb = document.getElementById("donation-hb").value;

  try {
    const res = await fetch("/api/donations", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        donor_id: donorId,
        volume_ml: parseInt(volume),
        hb_level: parseFloat(hb)
      })
    });
    const data = await res.json();
    if (data.success) {
      const unit = data.data;
      alert(`Donation recorded! Unit #${unit.unit_id} (${unit.blood_group}) created with expiry ${unit.expiry_date}. Trigger updated donor last_donated date.`);
      await loadDonors();
      await loadUnitsTable();
      await loadDashboardData();
      await loadQualityUnitsDropdown();
    } else {
      alert("Validation Error: " + data.error);
    }
  } catch (err) {
    alert("Error: " + err);
  }
}

// -----------------------------------------------------------------------------
// 5. HOSPITALS & REQUESTS
// -----------------------------------------------------------------------------
async function loadHospitals() {
  try {
    const res = await fetch("/api/hospitals");
    const hospitals = await res.json();
    const select = document.getElementById("req-hospital-id");
    select.innerHTML = `<option value="">Select hospital...</option>`;

    hospitals.forEach(h => {
      const opt = document.createElement("option");
      opt.value = h.hospital_id;
      opt.textContent = `${h.name} (${h.city})`;
      select.appendChild(opt);
    });
  } catch (err) {
    console.error("Error loading hospitals:", err);
  }
}

async function loadRequestsTable() {
  try {
    const res = await fetch("/api/requests");
    const requests = await res.json();
    const tbody = document.getElementById("requests-table-body");
    tbody.innerHTML = "";

    if (requests.length === 0) {
      tbody.innerHTML = `<tr><td colspan="8" class="text-center py-4 text-slate-400">No requests filed.</td></tr>`;
      return;
    }

    requests.forEach(r => {
      const tr = document.createElement("tr");
      tr.innerHTML = `
        <td class="py-2 px-3 font-mono font-bold">#${r.request_id}</td>
        <td class="py-2 px-3 text-slate-800 font-semibold">${r.hospital_name}</td>
        <td class="py-2 px-3 font-bold text-brand-700">${r.blood_group}</td>
        <td class="py-2 px-3"><span class="px-1.5 py-0.5 rounded text-[10px] font-bold badge-${r.urgency.toLowerCase()}">${r.urgency}</span></td>
        <td class="py-2 px-3 font-bold text-slate-800">${r.units_needed}</td>
        <td class="py-2 px-3 text-emerald-700 font-bold">${r.units_allocated}</td>
        <td class="py-2 px-3"><span class="px-2 py-0.5 rounded text-[10px] font-bold ${r.status === 'FULFILLED' ? 'bg-emerald-100 text-emerald-800' : 'bg-amber-100 text-amber-800'}">${r.status}</span></td>
        <td class="py-2 px-3">
          ${r.status === 'PENDING' || r.status === 'PARTIALLY_FULFILLED' ? `
            <button onclick="switchTab('allocation'); selectRequestForAllocation(${r.request_id});" class="px-2 py-1 bg-emerald-600 hover:bg-emerald-700 text-white rounded text-[10px] font-bold">
              Allocate
            </button>
          ` : '<span class="text-slate-400 text-[10px]">Complete</span>'}
        </td>
      `;
      tbody.appendChild(tr);
    });
  } catch (err) {
    console.error("Error loading requests table:", err);
  }
}

async function submitRegisterHospital(e) {
  e.preventDefault();
  const name = document.getElementById("hosp-name").value;
  const city = document.getElementById("hosp-city").value;
  const phone = document.getElementById("hosp-phone").value;

  try {
    const res = await fetch("/api/hospitals", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ name, city, phone })
    });
    const data = await res.json();
    if (data.success) {
      alert(`Hospital #${data.hospital_id} registered successfully!`);
      document.getElementById("hosp-name").value = "";
      document.getElementById("hosp-phone").value = "";
      await loadHospitals();
    } else {
      alert("Error: " + data.error);
    }
  } catch (err) {
    alert("Error: " + err);
  }
}

async function submitCreateRequest(e) {
  e.preventDefault();
  const hospitalId = document.getElementById("req-hospital-id").value;
  const bloodGroup = document.getElementById("req-blood-group").value;
  const units = document.getElementById("req-units").value;
  const urgency = document.getElementById("req-urgency").value;

  try {
    const res = await fetch("/api/requests", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        hospital_id: hospitalId,
        blood_group: bloodGroup,
        units_needed: parseInt(units),
        urgency: urgency
      })
    });
    const data = await res.json();
    if (data.success) {
      alert(`Blood Request #${data.request_id} created successfully!`);
      await loadRequestsTable();
      await loadDashboardData();
      await loadPendingRequestsForAllocation();
    } else {
      alert("Error: " + data.error);
    }
  } catch (err) {
    alert("Error: " + err);
  }
}

// -----------------------------------------------------------------------------
// 6. SLIDE 9 ANALYTICAL REPORTS
// -----------------------------------------------------------------------------
async function loadSlide9Reports() {
  try {
    // 1. Inventory Report
    const invRes = await fetch("/api/reports/inventory");
    const invData = await invRes.json();
    const invBody = document.getElementById("rep-inventory-body");
    invBody.innerHTML = "";
    invData.forEach(row => {
      const tr = document.createElement("tr");
      tr.innerHTML = `
        <td class="py-2.5 px-3 font-bold text-brand-700">${row.blood_group}</td>
        <td class="py-2.5 px-3 font-bold text-slate-800">${row.total_units}</td>
        <td class="py-2.5 px-3 text-slate-600">${row.total_volume_ml} mL</td>
        <td class="py-2.5 px-3 font-mono text-slate-600">${row.earliest_expiry}</td>
        <td class="py-2.5 px-3 text-emerald-700 font-semibold">${row.quality_cleared_units}</td>
      `;
      invBody.appendChild(tr);
    });

    // 2. Expiry Report (FEFO)
    const expRes = await fetch("/api/reports/expiry");
    const expData = await expRes.json();
    const expBody = document.getElementById("rep-expiry-body");
    expBody.innerHTML = "";
    expData.forEach(row => {
      const tr = document.createElement("tr");
      tr.innerHTML = `
        <td class="py-2.5 px-3 font-mono font-bold">#${row.unit_id}</td>
        <td class="py-2.5 px-3 font-bold text-brand-700">${row.blood_group}</td>
        <td class="py-2.5 px-3 text-slate-700">${row.donor_name}</td>
        <td class="py-2.5 px-3 font-mono">${row.expiry_date}</td>
        <td class="py-2.5 px-3 font-bold">${row.days_remaining} days</td>
        <td class="py-2.5 px-3">
          <span class="px-2 py-0.5 rounded text-[10px] font-bold ${row.urgency_category.includes('CRITICAL') ? 'bg-red-100 text-red-800' : row.urgency_category.includes('APPROACHING') ? 'bg-amber-100 text-amber-800' : 'bg-emerald-100 text-emerald-800'}">
            ${row.urgency_category}
          </span>
        </td>
      `;
      expBody.appendChild(tr);
    });

    // 3. Quality Report
    const qcRes = await fetch("/api/reports/quality");
    const qcData = await qcRes.json();
    document.getElementById("rep-qc-pending").textContent = qcData.pending_initial_check ?? 0;
    document.getElementById("rep-qc-quarantined").textContent = qcData.quarantined_count ?? 0;
    document.getElementById("rep-qc-discarded").textContent = qcData.discarded_count ?? 0;
    document.getElementById("rep-qc-passed").textContent = qcData.total_passed_checks ?? 0;

    // 4. Request Fulfillment Report
    const reqRes = await fetch("/api/reports/requests");
    const reqData = await reqRes.json();
    const reqBody = document.getElementById("rep-requests-body");
    reqBody.innerHTML = "";
    reqData.forEach(row => {
      const tr = document.createElement("tr");
      tr.innerHTML = `
        <td class="py-2.5 px-3 font-mono font-bold">#${row.request_id}</td>
        <td class="py-2.5 px-3 font-bold text-slate-800">${row.hospital_name}</td>
        <td class="py-2.5 px-3 text-slate-600">${row.hospital_city}</td>
        <td class="py-2.5 px-3 font-bold text-brand-700">${row.blood_group}</td>
        <td class="py-2.5 px-3 font-bold text-slate-800">${row.units_needed}</td>
        <td class="py-2.5 px-3 text-emerald-700 font-bold">${row.units_allocated}</td>
        <td class="py-2.5 px-3 text-red-600 font-bold">${row.units_unfulfilled}</td>
        <td class="py-2.5 px-3">
          <div class="flex items-center gap-2">
            <div class="w-16 bg-slate-200 rounded-full h-2">
              <div class="bg-emerald-600 h-2 rounded-full" style="width: ${Math.min(100, row.fulfillment_percentage)}%"></div>
            </div>
            <span class="text-[11px] font-semibold text-slate-700">${row.fulfillment_percentage}%</span>
          </div>
        </td>
        <td class="py-2.5 px-3"><span class="px-2 py-0.5 rounded text-[10px] font-bold ${row.status === 'FULFILLED' ? 'bg-emerald-100 text-emerald-800' : 'bg-amber-100 text-amber-800'}">${row.status}</span></td>
      `;
      reqBody.appendChild(tr);
    });
  } catch (err) {
    console.error("Error loading slide 9 reports:", err);
  }
}

// -----------------------------------------------------------------------------
// 7. ACID & CONCURRENCY LAB (Slides 4, 5, 6)
// -----------------------------------------------------------------------------
function runConcurrencyTestModal() {
  switchTab("concurrency");
  executeConcurrencyTestLive();
}

async function executeConcurrencyTestLive() {
  const btn = document.getElementById("btn-run-race-test");
  btn.disabled = true;
  btn.innerHTML = `<i data-lucide="loader-2" class="w-4 h-4 animate-spin"></i> Running Race Simulation...`;
  lucide.createIcons();

  const panel = document.getElementById("concurrency-results-panel");
  panel.classList.remove("hidden");

  try {
    const res = await fetch("/api/concurrency-test", { method: "POST" });
    const data = await res.json();
    const report = data.report;

    const banner = document.getElementById("concurrency-verdict-banner");
    if (report.acid_properties_verified) {
      banner.className = "p-4 rounded-xl border border-emerald-300 bg-emerald-50 text-emerald-900 font-semibold text-sm flex items-center gap-3";
      banner.innerHTML = `
        <i data-lucide="check-circle" class="w-6 h-6 text-emerald-600 shrink-0"></i>
        <div>
          <div class="font-bold text-emerald-800">ACID Isolation Guarantee Verified: No Double-Allocation!</div>
          <div class="text-xs text-emerald-700 mt-0.5">${report.summary}</div>
        </div>
      `;
    } else {
      banner.className = "p-4 rounded-xl border border-red-300 bg-red-50 text-red-900 font-semibold text-sm flex items-center gap-3";
      banner.innerHTML = `<i data-lucide="x-circle" class="w-6 h-6 text-red-600 shrink-0"></i> <div>${report.summary}</div>`;
    }

    const logContainer = document.getElementById("concurrency-threads-log");
    logContainer.innerHTML = report.thread_results.map(t => `
      <div class="p-2 rounded bg-black/40 border border-slate-700">
        <div class="flex justify-between">
          <strong class="${t.success ? 'text-emerald-400' : 'text-amber-400'}">${t.staff}</strong>
          <span class="text-slate-400">${t.time_ms} ms</span>
        </div>
        <div class="text-slate-300 text-[11px] mt-1">
          Outcome: ${t.success ? `<span class="text-emerald-300 font-bold">Successfully Claimed Unit #${t.allocated_units}</span>` : `<span class="text-red-300 font-bold">Blocked / Stock Depleted</span>`}<br>
          Message: ${t.message || t.error}
        </div>
      </div>
    `).join("");

    const stateContainer = document.getElementById("concurrency-db-state");
    stateContainer.innerHTML = `
      <div class="flex justify-between py-1 border-b border-slate-200">
        <span>Target Unit Tested:</span>
        <strong class="font-mono">#${report.test_target_unit_id} (${report.target_blood_group})</strong>
      </div>
      <div class="flex justify-between py-1 border-b border-slate-200">
        <span>Competing Worker Threads:</span>
        <strong class="font-mono">${report.total_competing_threads} threads</strong>
      </div>
      <div class="flex justify-between py-1 border-b border-slate-200">
        <span>Successful Unit Claims:</span>
        <strong class="font-mono text-emerald-700">${report.successful_claims}</strong>
      </div>
      <div class="flex justify-between py-1 border-b border-slate-200">
        <span>Prevented Duplicate Claims:</span>
        <strong class="font-mono text-amber-700">${report.prevented_duplicate_claims}</strong>
      </div>
      <div class="flex justify-between py-1 border-b border-slate-200">
        <span>Final Unit Status in DB:</span>
        <strong class="font-mono text-indigo-700">${report.final_unit_status}</strong>
      </div>
      <div class="flex justify-between py-1">
        <span>Total Allocation Records Inserted:</span>
        <strong class="font-mono text-slate-900">${report.db_allocation_record_count} (Unique Guarantee)</strong>
      </div>
    `;

    lucide.createIcons();
  } catch (err) {
    alert("Concurrency test error: " + err);
  } finally {
    btn.disabled = false;
    btn.innerHTML = `<i data-lucide="play" class="w-4 h-4 fill-slate-950"></i> Run Live Concurrency Race Test`;
    lucide.createIcons();
  }
}

// -----------------------------------------------------------------------------
// RESET SEED DATA
// -----------------------------------------------------------------------------
async function resetSeedData() {
  if (!confirm("Reset database to initial Review 2 sample dataset?")) return;
  try {
    const res = await fetch("/api/reset-seed", { method: "POST" });
    const data = await res.json();
    if (data.success) {
      alert("Database reset and seeded successfully!");
      selectedRequestId = null;
      await loadDashboardData();
      await loadUnitsTable();
      await loadDonors();
      await loadHospitals();
      await loadQualityUnitsDropdown();
      await loadQualityHistory();
      await loadRequestsTable();
      await loadSlide9Reports();
      await loadPendingRequestsForAllocation();
    }
  } catch (err) {
    alert("Reset error: " + err);
  }
}
