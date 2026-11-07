/* Doctor dashboard: list cases, review one, approve and email the plan. */
const $ = (id) => document.getElementById(id);
let activeCase = null;
let currentStatus = "pending_review";

const escapeHtml = (value) => String(value ?? "")
  .replaceAll("&", "&amp;").replaceAll("<", "&lt;").replaceAll(">", "&gt;")
  .replaceAll('"', "&quot;");

async function api(path, options = {}) {
  const res = await fetch(path, {
    headers: { "Content-Type": "application/json" }, ...options,
  });
  const data = await res.json().catch(() => ({}));
  if (!res.ok) {
    const detail = Array.isArray(data.detail)
      ? data.detail.map((item) => item.msg || String(item)).join("; ")
      : data.detail;
    throw new Error(detail || `HTTP ${res.status}`);
  }
  return data;
}

const statusPill = (status) => {
  const labels = { intake: "intake", emergency: "emergency",
    pending_review: "pending review", delivered: "delivered" };
  const cls = status === "emergency" ? "red" :
    status === "pending_review" ? "amber" : status === "delivered" ? "" : "grey";
  return `<span class="pill ${cls}">${labels[status] || status}</span>`;
};

async function loadCases() {
  const query = currentStatus ? `?status=${encodeURIComponent(currentStatus)}` : "";
  try {
    const data = await api(`/api/doctor/cases${query}`);
    const list = $("case-list");
    if (!data.cases.length) {
      list.innerHTML = `<p class="muted small">No cases in this view.</p>`;
      return;
    }
    list.innerHTML = data.cases.map((c) => `
      <button class="case-item ${activeCase?.case_id === c.case_id ? "active" : ""}"
              data-id="${escapeHtml(c.case_id)}">
        <div class="id">${escapeHtml(c.case_id)} · ${escapeHtml(c.created_at)}</div>
        <b>${escapeHtml(c.summary?.one_liner || c.chief_complaint || "New case")}</b>
        <div class="sub">
          ${statusPill(c.status)}
          <span>${escapeHtml(c.patient?.name || "unnamed")}</span>
          <span>${escapeHtml(c.selected_option || "")}</span>
        </div>
      </button>`).join("");
    list.querySelectorAll(".case-item").forEach((el) => {
      el.onclick = () => selectCase(el.dataset.id);
    });
  } catch (err) {
    $("case-list").innerHTML =
      `<p class="muted small">Ledger unavailable: ${escapeHtml(err.message)}</p>`;
  }
}

function tags(values, cls = "") {
  if (!values?.length) return `<span class="muted small">none</span>`;
  return `<div class="tags">${values.map((v) =>
    `<span class="tag ${cls}">${escapeHtml(v)}</span>`).join("")}</div>`;
}

function transcript(caseData) {
  return (caseData.transcript || []).map((entry) => `
    <div class="t ${entry.role === "patient" ? "patient" : ""}">
      <b>${escapeHtml(entry.role)}</b>
      <span class="muted small">${escapeHtml((entry.at || "").slice(11, 19))}</span><br>
      ${escapeHtml(entry.text)}
    </div>`).join("");
}

function audit(caseData) {
  return (caseData.audit || []).map((a) => `
    <div class="a"><time>${escapeHtml((a.at || "").slice(11, 19))}</time>
      <span><b>${escapeHtml(a.actor)}</b> ${escapeHtml(a.action)} — ${escapeHtml(a.detail)}</span>
    </div>`).join("");
}

async function selectCase(caseId) {
  try {
    const data = await api(`/api/cases/${caseId}`);
    activeCase = data.case;
    renderDetail(activeCase);
    loadCases();
    const url = new URL(location.href);
    url.searchParams.set("case", caseId);
    history.replaceState(null, "", url);
  } catch (err) {
    $("detail").innerHTML = `<p class="muted">Could not load case: ${escapeHtml(err.message)}</p>`;
  }
}

function renderDetail(c) {
  const canReview = c.status === "pending_review";
  const patient = c.patient || {};
  const warnings = [...(c.allergy_warnings || []), ...(c.interaction_warnings || [])];
  $("detail").innerHTML = `
    <div style="display:flex;justify-content:space-between;align-items:flex-start;gap:12px">
      <div>
        <div class="small muted">${escapeHtml(c.case_id)} · engine: ${escapeHtml(c.engine || "—")}</div>
        <h2 style="margin:4px 0">${escapeHtml(patient.name || "Unnamed patient")}</h2>
      </div>
      ${statusPill(c.status)}
    </div>

    <dl class="kv">
      <dt>Email</dt><dd>${escapeHtml(patient.email || "—")}</dd>
      <dt>Age / sex</dt><dd>${escapeHtml(patient.age ?? "—")} · ${escapeHtml(patient.sex || "—")}</dd>
      <dt>Chief complaint</dt><dd>${escapeHtml(c.chief_complaint || "—")}</dd>
      <dt>Symptoms</dt><dd>${tags(c.symptoms)}</dd>
      <dt>Duration</dt><dd>${c.duration_days ?? "—"} day(s)</dd>
      <dt>Severity / urgency</dt><dd>${escapeHtml(c.severity || "—")} · ${escapeHtml(c.urgency || "—")}</dd>
      <dt>Allergies</dt><dd>${tags(patient.allergies, "warn")}</dd>
      <dt>Medications</dt><dd>${tags(patient.medications)}</dd>
      <dt>History</dt><dd>${escapeHtml(patient.history || "—")}</dd>
      <dt>Red flags</dt><dd>${tags((c.red_flags || []).map((f) =>
        typeof f === "object" ? (f.label || JSON.stringify(f)) : f), "red")}</dd>
      <dt>Chosen option</dt><dd>${escapeHtml(c.selected_option || "—")}</dd>
    </dl>

    <div class="card pad" style="box-shadow:none;background:#f6faf8">
      <h3>AI-prepared case summary</h3>
      <p style="margin:0 0 8px"><b>${escapeHtml(c.summary?.one_liner || "—")}</b></p>
      <div class="small muted">Key findings</div>${tags(c.summary?.key_findings)}
      <div class="spacer"></div>
      <div class="small muted">Safety notes</div>${tags(c.summary?.safety_notes, "warn")}
    </div>

    ${c.needs_attention ? `
      <div class="emergency-banner" style="margin:0">
        Needs attention: the follow-up reported a red flag. Contact the patient now.
      </div>` : ""}

    ${warnings.length ? `
      <div class="emergency-banner" style="margin:0">
        Safety check: ${escapeHtml(warnings.join("; "))}
      </div>` : ""}

    <div>
      <h3>Uploaded reports</h3>
      ${(c.reports || []).length ? (c.reports || []).map((r) => `
        <div class="card pad soft" style="margin-bottom:8px">
          <b>${escapeHtml(r.filename)}</b>
          <div class="small muted">${escapeHtml(r.uploaded_at)} · ${escapeHtml(r.summary)}</div>
          ${(r.findings || []).length ? `
          <table class="labs">
            <thead><tr><th>Test</th><th>Value</th><th>Reference</th><th></th></tr></thead>
            <tbody>${r.findings.map((f) => `
              <tr><td>${escapeHtml(f.test)}</td>
                  <td>${escapeHtml(f.value)} ${escapeHtml(f.unit || "")}</td>
                  <td>${escapeHtml(f.reference || "")}</td>
                  <td>${f.flag ? `<span class="pill ${f.flag === "high" ? "red" : "amber"}">${escapeHtml(f.flag)}</span>` : ""}</td>
              </tr>`).join("")}</tbody>
          </table>` : ""}
        </div>`).join("") : `<p class="muted small">No reports attached.</p>`}
    </div>

    <div>
      <h3>Conversation</h3>
      <div class="transcript">${transcript(c) || "<p class='muted small'>No messages.</p>"}</div>
    </div>

    <div>
      <h3>Doctor decision</h3>
      ${canReview ? `
      <div class="field"><label>Advice to the patient</label>
        <textarea id="advice">${escapeHtml(c.doctor?.advice || "")}</textarea></div>
      <div class="spacer"></div>
      <div class="field"><label>Prescription (optional — doctor only)</label>
        <textarea id="prescription">${escapeHtml(c.doctor?.prescription || "")}</textarea></div>
      <div class="spacer"></div>
      <div class="field"><label>Private notes (optional)</label>
        <textarea id="notes">${escapeHtml(c.doctor?.notes || "")}</textarea></div>
      <div class="spacer"></div>
      <div class="row">
        <div class="field"><label>Approved by</label>
          <input id="doctor" value="${escapeHtml(c.doctor?.approved_by || "Dr. Demo")}"></div>
        <div style="display:flex;align-items:flex-end">
          <button class="btn" id="approve-btn" style="width:100%">Approve &amp; email plan</button>
        </div>
      </div>
      <p class="small muted">The patient is emailed only after this approval.
      ${c.patient?.email ? "" : "No email on file; delivery uses a demo address."}</p>
      ` : `
      <dl class="kv">
        <dt>Approved by</dt><dd>${escapeHtml(c.doctor?.approved_by || "—")}</dd>
        <dt>Approved at</dt><dd>${escapeHtml(c.doctor?.approved_at || "—")}</dd>
        <dt>Advice</dt><dd>${escapeHtml(c.doctor?.advice || "—")}</dd>
        <dt>Prescription</dt><dd>${escapeHtml(c.doctor?.prescription || "—")}</dd>
        <dt>Email</dt><dd>${escapeHtml(c.email?.mode || "—")} → ${escapeHtml(c.email?.to || "—")}</dd>
      </dl>
      <div class="spacer"></div>
      <div class="card pad soft" style="margin-bottom:10px">
        <div class="small muted">Follow-up agent</div>
        ${c.follow_up?.link ? `<div class="small">Public check-in link:
          <a href="${escapeHtml(c.follow_up.link)}" target="_blank" rel="noopener">
          ${escapeHtml(c.follow_up.link)}</a></div>` : ""}
        <div class="small">Due: ${escapeHtml(c.follow_up?.due_at || "—")} ·
          sent: ${escapeHtml(c.follow_up?.sent_at || "not yet")}</div>
        ${c.status === "delivered" && c.follow_up?.link ?
          `<div class="spacer"></div><button class="btn ghost small" id="send-followup-btn">
             Send check-in email now</button>` : ""}
      </div>
      <div class="field"><label>Follow-up report (patient says how they feel)</label>
        <textarea id="followup" placeholder="Still coughing, but the fever is gone."></textarea></div>
      <div class="spacer"></div>
      <button class="btn ghost" id="followup-btn">Log follow-up</button>
      `}
    </div>

    <div>
      <h3>Audit trail</h3>
      <div class="audit">${audit(c) || "<span class='muted small'>No actions.</span>"}</div>
    </div>
  `;

  const approve = $("approve-btn");
  if (approve) approve.onclick = approveCase;
  const follow = $("followup-btn");
  if (follow) follow.onclick = sendFollowUp;
  const sendNow = $("send-followup-btn");
  if (sendNow) sendNow.onclick = sendFollowUpNow;
}

async function approveCase() {
  if (!activeCase) return;
  const body = {
    advice: $("advice").value,
    prescription: $("prescription").value,
    notes: $("notes").value,
    doctor: $("doctor").value,
  };
  if (!body.advice.trim()) {
    alert("Enter the advice that will be sent to the patient.");
    return;
  }
  const btn = $("approve-btn");
  btn.disabled = true;
  btn.textContent = "Sending…";
  try {
    const data = await api(`/api/cases/${activeCase.case_id}/approve`, {
      method: "POST", body: JSON.stringify(body),
    });
    activeCase = data.case;
    renderDetail(activeCase);
    loadCases();
    loadMailbox();
  } catch (err) {
    alert(`Could not approve: ${err.message}`);
    btn.disabled = false;
    btn.textContent = "Approve & email plan";
  }
}

async function sendFollowUp() {
  if (!activeCase) return;
  try {
    const data = await api(`/api/cases/${activeCase.case_id}/follow-up`, {
      method: "POST",
      body: JSON.stringify({ report: $("followup").value }),
    });
    activeCase = data.case;
    renderDetail(activeCase);
    loadCases();
  } catch (err) {
    alert(`Could not log follow-up: ${err.message}`);
  }
}

async function sendFollowUpNow() {
  if (!activeCase) return;
  const btn = $("send-followup-btn");
  btn.disabled = true;
  btn.textContent = "Sending…";
  try {
    const data = await api(`/api/cases/${activeCase.case_id}/follow-up/send`,
      { method: "POST" });
    activeCase = data.case;
    renderDetail(activeCase);
    loadMailbox();
  } catch (err) {
    alert(`Could not send the check-in: ${err.message}`);
    btn.disabled = false;
    btn.textContent = "Send check-in email now";
  }
}

async function loadMailbox() {
  try {
    const data = await api("/api/mailbox");
    const box = $("mailbox");
    if (!data.emails.length) {
      box.innerHTML = `<p class="muted small">No emails yet.</p>`;
      return;
    }
    box.innerHTML = data.emails.map((m) => `
      <button class="mail" data-id="${escapeHtml(m.id)}"
              style="text-align:left;cursor:pointer">
        <b>${escapeHtml(m.subject)}</b>
        <div class="small muted">${escapeHtml(m.at)} · ${escapeHtml(m.mode)} · to ${escapeHtml(m.to_addr)}</div>
      </button>`).join("");
    box.querySelectorAll(".mail").forEach((el) => {
      el.onclick = () => showEmail(el.dataset.id);
    });
  } catch { /* mailbox is optional */ }
}

async function showEmail(emailId) {
  try {
    const data = await api(`/api/emails/${emailId}`);
    const pre = $("email-preview");
    pre.textContent = data.content;
    pre.classList.remove("hidden");
    pre.scrollIntoView({ behavior: "smooth", block: "nearest" });
  } catch (err) {
    alert(err.message);
  }
}

$("refresh-btn").onclick = () => { loadCases(); loadMailbox(); };
document.querySelectorAll("#tabs .tab").forEach((tab) => {
  tab.onclick = () => {
    document.querySelectorAll("#tabs .tab").forEach((t) => t.classList.remove("active"));
    tab.classList.add("active");
    currentStatus = tab.dataset.status;
    activeCase = null;
    $("detail").innerHTML = `<p class="muted">Select a case on the left to review it.</p>`;
    loadCases();
  };
});

loadCases();
loadMailbox();
const deepLink = new URLSearchParams(location.search).get("case");
if (deepLink) selectCase(deepLink);
