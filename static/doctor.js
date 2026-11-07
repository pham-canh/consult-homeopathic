const $ = (selector, root = document) => root.querySelector(selector);
const $$ = (selector, root = document) => Array.from(root.querySelectorAll(selector));

const VIEW_META = {
  overview: ["Overview", "Clinic activity at a glance"],
  cases: ["Cases", "Review, search and approve patient cases"],
  "follow-ups": ["Follow-ups", "Scheduled check-ins and patient replies"],
  outbox: ["Outbox", "Every message the clinic has sent"],
  settings: ["Settings", "Runtime, delivery and access configuration"],
};

const state = {
  view: "overview",
  overview: null,
  health: null,
  me: { enabled: false, authenticated: true, user: "doctor" },
  cases: [],
  caseTotal: 0,
  caseQuery: { q: "", status: "", urgency: "" },
  followups: [],
  followState: "",
  emails: [],
  activeEmailId: null,
  activeCase: null,
  activeTab: "summary",
  draft: null,
};

let searchTimer = 0;
let toastTimer = 0;

const escapeHtml = (value) => String(value ?? "")
  .replaceAll("&", "&amp;")
  .replaceAll("<", "&lt;")
  .replaceAll(">", "&gt;")
  .replaceAll('"', "&quot;")
  .replaceAll("'", "&#39;");

async function api(path, options = {}) {
  const headers = { "Content-Type": "application/json", ...(options.headers || {}) };
  const response = await fetch(path, {
    ...options,
    headers,
    credentials: "same-origin",
  });
  if (response.status === 401) {
    const next = encodeURIComponent(location.pathname + location.search + location.hash);
    location.replace(`/login?next=${next}`);
    throw new Error("Your session expired. Sign in again.");
  }
  const data = await response.json().catch(() => ({}));
  if (!response.ok) {
    const detail = Array.isArray(data.detail)
      ? data.detail.map((item) => item.msg || String(item)).join("; ")
      : data.detail;
    throw new Error(detail || `HTTP ${response.status}`);
  }
  return data;
}

function toast(message, kind = "") {
  const el = $("#toast");
  el.textContent = message;
  el.className = `toast show ${kind}`.trim();
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => {
    el.className = "toast";
  }, 3400);
}

function fmtDate(value, withTime = true) {
  if (!value) return "—";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return String(value);
  const options = { month: "short", day: "numeric" };
  if (withTime) {
    options.hour = "2-digit";
    options.minute = "2-digit";
  }
  return date.toLocaleString(undefined, options);
}

function fmtRelative(value) {
  if (!value) return "—";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return String(value);
  const seconds = Math.round((Date.now() - date.getTime()) / 1000);
  if (seconds < 60) return "just now";
  if (seconds < 3600) return `${Math.round(seconds / 60)}m ago`;
  if (seconds < 86400) return `${Math.round(seconds / 3600)}h ago`;
  return fmtDate(value, false);
}

function fmtDuration(seconds) {
  if (seconds === null || seconds === undefined) return "—";
  if (seconds < 1) return "<1s";
  if (seconds < 90) return `${seconds}s`;
  if (seconds < 5400) return `${Math.round(seconds / 60)}m`;
  return `${(seconds / 3600).toFixed(1)}h`;
}

function patientName(item) {
  return (item.patient && item.patient.name) || "Unnamed patient";
}

function summaryText(item) {
  if (typeof item.summary === "string") {
    return item.summary || item.chief_complaint || "No summary yet";
  }
  return (item.summary && item.summary.one_liner)
    || item.chief_complaint
    || "No summary yet";
}

function caseRef(item) {
  return item.case_id || "";
}

function statusPill(status) {
  const labels = {
    intake: "intake",
    emergency: "emergency",
    pending_review: "pending review",
    delivered: "delivered",
  };
  const tone = status === "emergency" ? "red"
    : status === "pending_review" ? "amber"
      : status === "delivered" ? "" : "grey";
  return `<span class="pill ${tone}">${escapeHtml(labels[status] || status || "unknown")}</span>`;
}

function urgencyPill(value) {
  if (!value) return '<span class="muted small">—</span>';
  const tone = ["emergency", "urgent", "routine"].includes(value) ? value : "";
  return `<span class="urgency ${tone}">${escapeHtml(value)}</span>`;
}

function tags(values, tone = "") {
  const list = (values || [])
    .map((value) => (value && typeof value === "object")
      ? (value.label || JSON.stringify(value))
      : value)
    .filter(Boolean);
  if (!list.length) return '<span class="muted small">none</span>';
  return `<div class="tags">${list.map((value) =>
    `<span class="tag ${tone}">${escapeHtml(value)}</span>`).join("")}</div>`;
}

function setBadge(element, count, red = false) {
  if (!element) return;
  element.textContent = String(count);
  element.classList.toggle("hidden", !count);
  element.classList.toggle("red", Boolean(red && count));
}

function updateBadges() {
  const pending = (state.overview && state.overview.cases)
    ? state.overview.cases.pending_review : 0;
  const due = (state.overview && state.overview.followups)
    ? state.overview.followups.due : 0;
  setBadge($("#nav-pending"), pending);
  setBadge($("#nav-due"), due, true);
}

function updateVersion() {
  if (state.health && state.health.version) {
    $("#side-version").textContent = `v${state.health.version}`;
  }
}

function updateUser() {
  const enabled = Boolean(state.me && state.me.enabled);
  $("#user-chip").classList.toggle("hidden", !enabled);
  $("#logout-btn").classList.toggle("hidden", !enabled);
  if (!enabled) return;
  const name = state.me.user || "doctor";
  $("#user-name").textContent = name;
  $("#user-initial").textContent = name.slice(0, 1).toUpperCase();
}

function bindCaseOpen(root) {
  $$("[data-case-open]", root).forEach((element) => {
    element.addEventListener("click", (event) => {
      event.preventDefault();
      openCase(element.dataset.caseOpen);
    });
  });
}

function setView(view) {
  if (!VIEW_META[view]) view = "overview";
  state.view = view;
  $$(".nav-item").forEach((item) => {
    item.classList.toggle("active", item.dataset.view === view);
  });
  $$(".view").forEach((section) => {
    section.classList.toggle("hidden", section.id !== `view-${view}`);
  });
  const [title, subtitle] = VIEW_META[view];
  $("#page-title").textContent = title;
  $("#page-sub").textContent = subtitle;
  const url = new URL(location.href);
  url.hash = view;
  history.replaceState(null, "", url);
  if (view === "overview") loadOverview();
  if (view === "cases") loadCases();
  if (view === "follow-ups") loadFollowups();
  if (view === "outbox") loadOutbox();
  if (view === "settings") loadSettings();
}

async function loadOverview() {
  try {
    const [overview, health] = await Promise.allSettled([
      api("/api/dashboard"),
      api("/healthz"),
    ]);
    if (overview.status !== "fulfilled") throw overview.reason;
    state.overview = overview.value;
    if (health.status === "fulfilled") {
      state.health = health.value;
      updateVersion();
    }
    renderOverview();
    updateBadges();
  } catch (err) {
    $("#overview-stats").innerHTML = `
      <div class="stat-card alert">
        <span class="stat-label">Unavailable</span>
        <b>—</b>
        <span class="stat-sub">${escapeHtml(err.message)}</span>
      </div>`;
  }
}

function renderOverview() {
  const data = state.overview;
  if (!data) return;
  const cases = data.cases || {};
  const followups = data.followups || {};
  const today = data.today || {};
  const stats = [
    ["Total cases", cases.total || 0, `${today.new_cases || 0} new today`, ""],
    ["Needs review", cases.pending_review || 0, "awaiting clinician", "warn"],
    ["Emergencies", cases.emergency || 0,
      `${cases.needs_attention || 0} flagged overall`, "alert"],
    ["Follow-ups due", followups.due || 0,
      `${followups.scheduled || 0} scheduled ahead`, "warn"],
    ["Delivered", cases.delivered || 0,
      `${today.approved || 0} approved today`, ""],
    ["Avg review", fmtDuration(data.avg_review_seconds), "intake to approval", ""],
  ];
  $("#overview-stats").innerHTML = stats.map(([label, value, sub, tone]) => `
    <div class="stat-card ${tone}">
      <span class="stat-label">${escapeHtml(label)}</span>
      <b>${escapeHtml(value)}</b>
      <span class="stat-sub">${escapeHtml(sub)}</span>
    </div>`).join("");

  const trend = data.trend || [];
  const max = Math.max(1, ...trend.map((day) => day.count || 0));
  $("#trend").innerHTML = trend.map((day, index) => `
    <div class="trend-col ${index === trend.length - 1 ? "today" : ""}">
      <span class="trend-count">${Number(day.count) || 0}</span>
      <div class="trend-track">
        <div class="trend-bar" style="height:${Math.max(4, Math.round((day.count || 0) / max * 100))}%"></div>
      </div>
      <span class="trend-label">${escapeHtml(day.label || "")}</span>
    </div>`).join("");

  const attention = data.attention || [];
  const attentionTotal = cases.needs_attention || attention.length;
  $("#attention-count").textContent = String(attentionTotal);
  $("#attention-count").classList.toggle("hidden", !attentionTotal);
  $("#attention-list").innerHTML = attention.length ? attention.map((item) => `
    <button class="attention-item" data-case-open="${escapeHtml(caseRef(item))}">
      <b>${escapeHtml(patientName(item))} · ${escapeHtml(caseRef(item))}</b>
      <span>${escapeHtml(summaryText(item))}</span>
      <span>${statusPill(item.status)}
        ${urgencyPill(item.urgency)}
        ${escapeHtml((item.red_flags || []).slice(0, 2).join(", "))}</span>
    </button>`).join("")
    : '<p class="empty">Nothing needs attention.</p>';

  const recent = data.recent || [];
  $("#recent-table").innerHTML = recent.length ? `
    <table class="data">
      <thead><tr><th>Case</th><th>Patient</th><th>Status</th><th>Updated</th></tr></thead>
      <tbody>${recent.map((item) => `
        <tr class="clickable" data-case-open="${escapeHtml(caseRef(item))}">
          <td class="case-ref">${escapeHtml(caseRef(item))}</td>
          <td class="strong">${escapeHtml(patientName(item))}</td>
          <td>${statusPill(item.status)}</td>
          <td class="nowrap">${escapeHtml(fmtRelative(item.updated_at))}</td>
        </tr>`).join("")}</tbody>
    </table>` : '<p class="empty">No cases yet. Start with a patient intake.</p>';

  const health = state.health || {};
  const scheduler = health.followups || {};
  const rows = [
    ["Status", health.status || "unknown"],
    ["Version", health.version || "—"],
    ["Provider", `${health.provider || "—"} / ${health.model || "rules"}`],
    ["Engine", health.engine || "—"],
    ["Model key", health.llm_key ? "configured" : "not set"],
    ["Email", health.email || "—"],
    ["Dashboard auth", health.dashboard_auth ? "password on" : "open (demo)"],
    ["Cases / pending",
      `${(health.storage && health.storage.cases) ?? 0} / ${(health.storage && health.storage.pending_review) ?? 0}`],
    ["Follow-ups due", (health.storage && health.storage.followups_due) ?? 0],
    ["Scheduler", scheduler.running ? "running" : "stopped"],
  ];
  $("#system-card").innerHTML = `<div class="kv-card">${rows.map(([key, value]) => `
    <div class="kv-row"><span>${escapeHtml(key)}</span><b>${escapeHtml(value)}</b></div>`).join("")}</div>`;

  bindCaseOpen($("#view-overview"));
}

async function loadCases() {
  const params = new URLSearchParams();
  if (state.caseQuery.q) params.set("q", state.caseQuery.q);
  if (state.caseQuery.status) params.set("status", state.caseQuery.status);
  if (state.caseQuery.urgency) params.set("urgency", state.caseQuery.urgency);
  params.set("limit", "100");
  try {
    const data = await api(`/api/doctor/cases?${params.toString()}`);
    state.cases = data.cases || [];
    state.caseTotal = data.total || state.cases.length;
    renderCases();
  } catch (err) {
    $("#case-table").innerHTML = `<p class="empty">Could not load cases: ${escapeHtml(err.message)}</p>`;
  }
}

function renderCases() {
  const total = state.caseTotal;
  $("#cases-count").textContent = `${total} case${total === 1 ? "" : "s"}`;
  if (!state.cases.length) {
    $("#case-table").innerHTML = '<p class="empty">No cases match these filters.</p>';
    return;
  }
  $("#case-table").innerHTML = `
    <table class="data">
      <thead><tr>
        <th>Case</th><th>Patient</th><th>Summary</th>
        <th>Status</th><th>Urgency</th><th>Updated</th>
      </tr></thead>
      <tbody>${state.cases.map((item) => `
        <tr class="clickable" data-case-open="${escapeHtml(caseRef(item))}">
          <td class="case-ref">${escapeHtml(caseRef(item))}</td>
          <td class="strong">${escapeHtml(patientName(item))}<br>
            <span class="muted small">${escapeHtml((item.patient && item.patient.email) || "no email")}</span></td>
          <td class="summary-cell">${escapeHtml(summaryText(item))}</td>
          <td>${statusPill(item.status)}</td>
          <td>${urgencyPill(item.urgency)}</td>
          <td class="nowrap">${escapeHtml(fmtRelative(item.updated_at || item.created_at))}</td>
        </tr>`).join("")}</tbody>
    </table>`;
  bindCaseOpen($("#case-table"));
}

async function openCase(caseId) {
  if (!caseId) return;
  try {
    const data = await api(`/api/cases/${encodeURIComponent(caseId)}`);
    state.activeCase = data.case;
    state.activeTab = "summary";
    state.draft = null;
    renderDrawer();
    $("#case-overlay").classList.remove("hidden");
    document.body.style.overflow = "hidden";
    const url = new URL(location.href);
    url.searchParams.set("case", caseId);
    history.replaceState(null, "", url);
    $("#drawer-close").focus();
  } catch (err) {
    toast(`Could not open case: ${err.message}`, "error");
  }
}

function closeCase() {
  $("#case-overlay").classList.add("hidden");
  document.body.style.overflow = "";
  state.activeCase = null;
  state.draft = null;
  const url = new URL(location.href);
  url.searchParams.delete("case");
  history.replaceState(null, "", url);
}

function captureDraft() {
  const advice = $("#advice");
  if (!advice) return;
  state.draft = {
    advice: advice.value,
    prescription: $("#prescription") ? $("#prescription").value : "",
    notes: $("#notes") ? $("#notes").value : "",
    doctor: $("#doctor") ? $("#doctor").value : "",
    followup: $("#followup") ? $("#followup").value : "",
  };
}

function renderDrawer() {
  const item = state.activeCase;
  if (!item) return;
  $("#drawer-id").textContent = `${caseRef(item)} · created ${fmtDate(item.created_at)}`;
  $("#drawer-name").textContent = patientName(item);
  $("#drawer-status").innerHTML = statusPill(item.status);
  $$(".drawer-tab").forEach((tab) => {
    tab.classList.toggle("active", tab.dataset.tab === state.activeTab);
  });

  let body = "";
  if (state.activeTab === "summary") body = renderSummary(item);
  if (state.activeTab === "reports") body = renderReports(item);
  if (state.activeTab === "conversation") body = renderConversation(item);
  if (state.activeTab === "decision") body = renderDecision(item);
  if (state.activeTab === "audit") body = renderAudit(item);
  $("#drawer-body").innerHTML = body;
  bindDecision();
}

function renderPayment(item) {
  const payment = item.payment || {};
  if (!payment.amount_display) return "";
  const paid = payment.status === "paid_demo";
  return `
    <div class="detail-card">
      <h3>Consultation fee <span class="small muted">demo only</span></h3>
      <dl class="kv">
        <dt>Amount</dt><dd>${escapeHtml(payment.amount_display)}</dd>
        <dt>Status</dt><dd><span class="state ${paid ? "sent" : "due"}">${paid ? "Paid (demo)" : "Unpaid"}</span></dd>
        <dt>Method</dt><dd>${escapeHtml(payment.method_label || "—")}</dd>
        <dt>Paid at</dt><dd>${escapeHtml(payment.paid_at ? fmtDate(payment.paid_at) : "—")}</dd>
      </dl>
      <p class="small muted">${escapeHtml(payment.note || "")}</p>
      ${payment.link ? `<p class="small"><a href="${escapeHtml(payment.link)}" target="_blank" rel="noopener">Open demo payment page</a></p>` : ""}
    </div>`;
}

function renderSummary(item) {
  const patient = item.patient || {};
  const follow = item.follow_up || {};
  const warnings = [...(item.allergy_warnings || []), ...(item.interaction_warnings || [])];
  const flags = (item.red_flags || []).map((flag) =>
    (flag && typeof flag === "object") ? (flag.label || JSON.stringify(flag)) : flag);
  return `
    <div class="detail-card soft">
      <h3>Human review required</h3>
      <p>The AI prepared this case; it did not diagnose or prescribe. Review the
      record, edit the plan and approve. Nothing is emailed before approval.</p>
    </div>
    ${item.needs_attention ? `
      <div class="detail-card alert">
        <h3>Needs attention</h3>
        <p>A follow-up reported a red flag. Contact the patient now.</p>
      </div>` : ""}
    ${warnings.length ? `
      <div class="detail-card warn">
        <h3>Safety check</h3>
        <p>${escapeHtml(warnings.join("; "))}</p>
      </div>` : ""}
    <div class="detail-card">
      <h3>Patient</h3>
      <dl class="kv">
        <dt>Name</dt><dd>${escapeHtml(patient.name || "—")}</dd>
        <dt>Email</dt><dd>${escapeHtml(patient.email || "—")}</dd>
        <dt>Age / sex</dt><dd>${escapeHtml(patient.age ?? "—")} · ${escapeHtml(patient.sex || "—")}</dd>
        <dt>Allergies</dt><dd>${tags(patient.allergies, "warn")}</dd>
        <dt>Medications</dt><dd>${tags(patient.medications)}</dd>
        <dt>History</dt><dd>${escapeHtml(patient.history || "—")}</dd>
        <dt>Diet</dt><dd>${escapeHtml(patient.diet || "—")}</dd>
      </dl>
    </div>
    ${(item.prior_cases || []).length ? `
    <div class="detail-card">
      <h3>Previous visits</h3>
      <div class="timeline">${(item.prior_cases || []).map((prior) => `
        <div class="timeline-item">
          <time>${escapeHtml((prior.created_at || "").slice(0, 10))}</time>
          <span><b>${escapeHtml(prior.case_id || "")}</b>
            ${escapeHtml(prior.chief_complaint || prior.summary || "No complaint recorded")}
            ${prior.doctor_advice ? ` — ${escapeHtml(prior.doctor_advice)}` : ""}</span>
        </div>`).join("")}</div>
    </div>` : ""}
    ${renderPayment(item)}
    <div class="detail-card">
      <h3>Case</h3>
      <dl class="kv">
        <dt>Chief complaint</dt><dd>${escapeHtml(item.chief_complaint || "—")}</dd>
        <dt>Symptoms</dt><dd>${tags(item.symptoms)}</dd>
        <dt>Duration</dt><dd>${escapeHtml(item.duration_days ?? "—")} day(s)</dd>
        <dt>Severity / urgency</dt><dd>${escapeHtml(item.severity || "—")} · ${escapeHtml(item.urgency || "—")}</dd>
        <dt>Red flags</dt><dd>${tags(flags, "red")}</dd>
        <dt>Chosen option</dt><dd>${escapeHtml(item.selected_option || "—")}</dd>
        <dt>Engine</dt><dd>${escapeHtml(item.engine || "—")}</dd>
      </dl>
    </div>
    <div class="detail-card">
      <h3>AI-prepared summary</h3>
      <p><b>${escapeHtml((item.summary && item.summary.one_liner) || "—")}</b></p>
      <div class="small muted">Key findings</div>
      ${tags(item.summary && item.summary.key_findings)}
      <div class="spacer"></div>
      <div class="small muted">Safety notes</div>
      ${tags(item.summary && item.summary.safety_notes, "warn")}
    </div>
    <div class="detail-card">
      <h3>Follow-up</h3>
      <dl class="kv">
        <dt>Due</dt><dd>${escapeHtml(fmtDate(follow.due_at))}</dd>
        <dt>Sent</dt><dd>${escapeHtml(follow.sent_at ? fmtDate(follow.sent_at) : "not yet")}</dd>
      </dl>
      ${follow.link ? `
        <p class="small">Public check-in link:
          <a href="${escapeHtml(follow.link)}" target="_blank" rel="noopener">${escapeHtml(follow.link)}</a>
        </p>` : '<p class="small muted">No check-in link yet.</p>'}
    </div>`;
}

function renderReports(item) {
  const reports = item.reports || [];
  if (!reports.length) {
    return '<div class="detail-card"><p class="muted small">No documents attached.</p></div>';
  }
  return reports.map((report, index) => {
    const findings = report.findings || [];
    return `
      <div class="report-card">
        <b>${escapeHtml(report.filename || "Document")}</b>
        <div class="small muted">${escapeHtml(fmtDate(report.uploaded_at))}</div>
        <p class="small">
          <a href="/api/cases/${encodeURIComponent(item.case_id)}/reports/${index}/file"
             target="_blank" rel="noopener">Open original document</a>
        </p>
        <p class="small">${escapeHtml(report.summary || "")}</p>
        ${findings.length ? `
          <table class="labs">
            <thead><tr><th>Test</th><th>Value</th><th>Reference</th><th></th></tr></thead>
            <tbody>${findings.map((finding) => `
              <tr>
                <td>${escapeHtml(finding.test)}</td>
                <td>${escapeHtml(finding.value)} ${escapeHtml(finding.unit || "")}</td>
                <td>${escapeHtml(finding.reference || "")}</td>
                <td>${finding.flag ? `<span class="pill ${finding.flag === "high" ? "red" : "amber"}">${escapeHtml(finding.flag)}</span>` : ""}</td>
              </tr>`).join("")}</tbody>
          </table>` : ""}
      </div>`;
  }).join("");
}

function renderConversation(item) {
  const transcript = item.transcript || [];
  if (!transcript.length) {
    return '<div class="detail-card"><p class="muted small">No messages recorded.</p></div>';
  }
  return `
    <div class="detail-card">
      <h3>Conversation</h3>
      <div class="transcript">${transcript.map((entry) => `
        <div class="t ${entry.role === "patient" ? "patient" : ""}">
          <b>${escapeHtml(entry.role || "system")}</b>
          <span class="muted small">${escapeHtml((entry.at || "").slice(11, 19))}</span><br>
          ${escapeHtml(entry.text || "")}
        </div>`).join("")}</div>
    </div>`;
}

function renderAudit(item) {
  const audit = item.audit || [];
  if (!audit.length) {
    return '<div class="detail-card"><p class="muted small">No audit entries.</p></div>';
  }
  return `
    <div class="detail-card">
      <h3>Audit trail</h3>
      <div class="timeline">${audit.map((entry) => `
        <div class="timeline-item">
          <time>${escapeHtml((entry.at || "").slice(11, 19))}</time>
          <span><b>${escapeHtml(entry.actor || "")}</b>
            ${escapeHtml(entry.action || "")} — ${escapeHtml(entry.detail || "")}</span>
        </div>`).join("")}</div>
    </div>`;
}

function renderDecision(item) {
  const doctor = item.doctor || {};
  const follow = item.follow_up || {};
  if (item.status === "pending_review") {
    const draft = state.draft || {};
    const advice = draft.advice ?? doctor.advice ?? "";
    const prescription = draft.prescription ?? doctor.prescription ?? "";
    const notes = draft.notes ?? doctor.notes ?? "";
    const signer = draft.doctor ?? doctor.approved_by ?? (state.me && state.me.user) ?? "Dr. Demo";
    return `
      <div class="detail-card warn">
        <h3>Doctor approval</h3>
        <p>Edit the plan below. The patient is emailed only after you approve.
        ${item.patient && item.patient.email ? "" : "No email is on file; delivery uses a demo address."}</p>
      </div>
      <div class="detail-card">
        <div class="field"><label for="advice">Advice to the patient</label>
          <textarea id="advice">${escapeHtml(advice)}</textarea></div>
        <div class="spacer"></div>
        <div class="field"><label for="prescription">Prescription (optional, doctor only)</label>
          <textarea id="prescription">${escapeHtml(prescription)}</textarea></div>
        <div class="spacer"></div>
        <div class="field"><label for="notes">Private notes (optional)</label>
          <textarea id="notes">${escapeHtml(notes)}</textarea></div>
        <div class="spacer"></div>
        <div class="field"><label for="doctor">Approved by</label>
          <input id="doctor" value="${escapeHtml(signer)}"></div>
        <div class="form-actions">
          <button class="btn" id="approve-btn">Approve and email plan</button>
        </div>
      </div>`;
  }

  const followUpReports = follow.reports || [];
  const canFollowUp = Boolean(doctor.approved_at)
    && ["delivered", "emergency"].includes(item.status);
  const selfReport = (state.draft && state.draft.followup) || "";
  return `
    ${item.status === "emergency" ? `
      <div class="detail-card alert">
        <h3>Escalated case</h3>
        <p>This case is flagged for clinician attention. Contact the patient
        directly if you have not already done so.</p>
      </div>` : ""}
    <div class="detail-card">
      <h3>Doctor decision</h3>
      <dl class="kv">
        <dt>Approved by</dt><dd>${escapeHtml(doctor.approved_by || "—")}</dd>
        <dt>Approved at</dt><dd>${escapeHtml(fmtDate(doctor.approved_at))}</dd>
        <dt>Advice</dt><dd>${escapeHtml(doctor.advice || "—")}</dd>
        <dt>Prescription</dt><dd>${escapeHtml(doctor.prescription || "—")}</dd>
        <dt>Private notes</dt><dd>${escapeHtml(doctor.notes || "—")}</dd>
        <dt>Email</dt><dd>${escapeHtml((item.email && item.email.mode) || "—")} → ${escapeHtml((item.email && item.email.to) || "—")}</dd>
      </dl>
    </div>
    <div class="detail-card soft">
      <h3>Follow-up</h3>
      <dl class="kv">
        <dt>Due</dt><dd>${escapeHtml(fmtDate(follow.due_at))}</dd>
        <dt>Sent</dt><dd>${escapeHtml(follow.sent_at ? fmtDate(follow.sent_at) : "not yet")}</dd>
      </dl>
      ${follow.link ? `
        <p class="small">Public check-in link:
          <a href="${escapeHtml(follow.link)}" target="_blank" rel="noopener">${escapeHtml(follow.link)}</a>
        </p>` : ""}
      ${item.status === "delivered" && follow.link && !follow.sent_at ? `
        <div class="form-actions" style="justify-content:flex-start">
          <button class="btn ghost small" id="send-followup-btn">Send check-in email now</button>
        </div>` : ""}
    </div>
    ${canFollowUp ? `
      <div class="detail-card">
        <h3>Patient check-in</h3>
        <div class="field"><label for="followup">What did the patient report?</label>
          <textarea id="followup" placeholder="Still coughing, but the fever is gone.">${escapeHtml(selfReport)}</textarea></div>
        <div class="form-actions">
          <button class="btn ghost" id="followup-btn">Log follow-up</button>
        </div>
      </div>` : `
      <div class="detail-card">
        <p class="muted small">Follow-up check-ins open after a doctor delivers a plan.</p>
      </div>`}
    ${followUpReports.length ? `
      <div class="detail-card">
        <h3>Check-in history</h3>
        <div class="timeline">${followUpReports.map((entry) => `
          <div class="timeline-item">
            <time>${escapeHtml(fmtDate(entry.at, false))}</time>
            <span>${escapeHtml(entry.text || "")}
              ${(entry.red_flags || []).length ? `<br><span class="small warn">Red flags: ${escapeHtml(entry.red_flags.join(", "))}</span>` : ""}
            </span>
          </div>`).join("")}</div>
      </div>` : ""}`;
}

function bindDecision() {
  const approve = $("#approve-btn");
  if (approve) approve.addEventListener("click", approveCase);
  const followup = $("#followup-btn");
  if (followup) followup.addEventListener("click", sendFollowUp);
  const sendNow = $("#send-followup-btn");
  if (sendNow) sendNow.addEventListener("click", sendFollowUpNow);
}

async function approveCase() {
  const item = state.activeCase;
  if (!item) return;
  const body = {
    advice: $("#advice") ? $("#advice").value : "",
    prescription: $("#prescription") ? $("#prescription").value : "",
    notes: $("#notes") ? $("#notes").value : "",
    doctor: $("#doctor") ? $("#doctor").value : "Dr. Demo",
  };
  if (!body.advice.trim()) {
    toast("Enter the advice that will be sent to the patient.", "error");
    return;
  }
  const button = $("#approve-btn");
  button.disabled = true;
  button.textContent = "Sending…";
  try {
    const data = await api(`/api/cases/${encodeURIComponent(item.case_id)}/approve`, {
      method: "POST",
      body: JSON.stringify(body),
    });
    state.activeCase = data.case;
    state.draft = null;
    renderDrawer();
    toast("Plan approved and queued for email.");
    loadOverview();
    loadCases();
    if (state.view === "outbox") loadOutbox();
  } catch (err) {
    toast(`Could not approve: ${err.message}`, "error");
    button.disabled = false;
    button.textContent = "Approve and email plan";
  }
}

async function sendFollowUp() {
  const item = state.activeCase;
  if (!item) return;
  const field = $("#followup");
  if (!field || !field.value.trim()) {
    toast("Enter the patient's follow-up report.", "error");
    return;
  }
  const button = $("#followup-btn");
  button.disabled = true;
  button.textContent = "Saving…";
  try {
    const data = await api(`/api/cases/${encodeURIComponent(item.case_id)}/follow-up`, {
      method: "POST",
      body: JSON.stringify({ report: field.value }),
    });
    state.activeCase = data.case;
    state.draft = null;
    renderDrawer();
    toast("Follow-up report logged.");
    loadOverview();
    loadCases();
    if (state.view === "follow-ups") loadFollowups();
  } catch (err) {
    toast(`Could not log follow-up: ${err.message}`, "error");
    button.disabled = false;
    button.textContent = "Log follow-up";
  }
}

async function sendFollowUpNow() {
  const item = state.activeCase;
  if (!item) return;
  const button = $("#send-followup-btn");
  button.disabled = true;
  button.textContent = "Sending…";
  try {
    const data = await api(`/api/cases/${encodeURIComponent(item.case_id)}/follow-up/send`, {
      method: "POST",
    });
    state.activeCase = data.case;
    renderDrawer();
    toast("Check-in email queued.");
    loadOverview();
    if (state.view === "outbox") loadOutbox();
  } catch (err) {
    toast(`Could not send the check-in: ${err.message}`, "error");
    button.disabled = false;
    button.textContent = "Send check-in email now";
  }
}

async function loadFollowups() {
  try {
    const data = await api("/api/followups");
    state.followups = data.follow_ups || [];
    renderFollowups();
  } catch (err) {
    $("#followup-table").innerHTML = `<p class="empty">Could not load follow-ups: ${escapeHtml(err.message)}</p>`;
  }
}

function renderFollowups() {
  const labels = { "": "All", due: "Due", scheduled: "Scheduled", sent: "Sent" };
  const counts = { "": state.followups.length, due: 0, scheduled: 0, sent: 0 };
  state.followups.forEach((row) => {
    if (counts[row.state] !== undefined) counts[row.state] += 1;
  });
  $$("#followup-filters .filter-chip").forEach((chip) => {
    const key = chip.dataset.state || "";
    chip.textContent = `${labels[key]} (${counts[key] || 0})`;
    chip.classList.toggle("active", key === state.followState);
  });
  const rows = state.followState
    ? state.followups.filter((row) => row.state === state.followState)
    : state.followups;
  $("#followups-count").textContent =
    `${rows.length} of ${state.followups.length} check-in${state.followups.length === 1 ? "" : "s"}`;
  if (!rows.length) {
    $("#followup-table").innerHTML = '<p class="empty">No check-ins in this view.</p>';
    return;
  }
  $("#followup-table").innerHTML = `
    <table class="data">
      <thead><tr>
        <th>Patient</th><th>Case</th><th>Summary</th>
        <th>Due / sent</th><th>State</th><th>Actions</th>
      </tr></thead>
      <tbody>${rows.map((row) => `
        <tr>
          <td class="strong">${escapeHtml(patientName(row))}<br>
            <span class="muted small">${escapeHtml((row.patient && row.patient.email) || "no email")}</span></td>
          <td class="case-ref">${escapeHtml(row.case_id)}</td>
          <td class="summary-cell">${escapeHtml(row.summary || "—")}</td>
          <td class="nowrap">${escapeHtml(fmtDate(row.due_at))}<br>
            <span class="muted small">${escapeHtml(row.sent_at ? `sent ${fmtDate(row.sent_at)}` : "not sent")}</span></td>
          <td><span class="state ${escapeHtml(row.state)}">${escapeHtml(row.state)}</span></td>
          <td><div class="row-actions">
            <button class="link-btn" data-case-open="${escapeHtml(row.case_id)}">Open case</button>
            ${row.link ? `<button class="link-btn" data-copy="${escapeHtml(row.link)}">Copy link</button>` : ""}
          </div></td>
        </tr>`).join("")}</tbody>
    </table>`;
  bindCaseOpen($("#followup-table"));
  $$("[data-copy]", $("#followup-table")).forEach((button) => {
    button.addEventListener("click", () => copyText(button.dataset.copy));
  });
}

async function loadOutbox() {
  try {
    const data = await api("/api/mailbox");
    state.emails = data.emails || [];
    renderMailList();
    if (!state.emails.length) {
      state.activeEmailId = null;
      $("#mail-preview").innerHTML = `
        <div class="empty-state">
          <strong>No messages yet</strong>
          <span>Approve a plan to create the first email.</span>
        </div>`;
      return;
    }
    const keep = state.emails.some((mail) => String(mail.id) === String(state.activeEmailId))
      ? state.activeEmailId : state.emails[0].id;
    await showEmail(keep);
  } catch (err) {
    $("#mail-list").innerHTML = `<p class="empty">Could not load mailbox: ${escapeHtml(err.message)}</p>`;
  }
}

function renderMailList() {
  const list = $("#mail-list");
  if (!state.emails.length) {
    list.innerHTML = '<p class="empty">No messages yet. Approve a plan to create the first email.</p>';
    return;
  }
  list.innerHTML = state.emails.map((mail) => `
    <button class="mail-item ${String(mail.id) === String(state.activeEmailId) ? "active" : ""}"
            data-email="${escapeHtml(mail.id)}">
      <b>${escapeHtml(mail.subject)}</b>
      <span>${escapeHtml(mail.to_addr || "no recipient")} · ${escapeHtml(mail.mode || "file")}</span>
      <span>${escapeHtml(fmtDate(mail.at))}</span>
    </button>`).join("");
  $$(".mail-item", list).forEach((button) => {
    button.addEventListener("click", () => showEmail(button.dataset.email));
  });
}

async function showEmail(emailId) {
  state.activeEmailId = emailId;
  renderMailList();
  try {
    const data = await api(`/api/emails/${encodeURIComponent(emailId)}`);
    const row = state.emails.find((mail) => String(mail.id) === String(emailId)) || {};
    const preview = $("#mail-preview");
    preview.innerHTML = `
      <div class="mail-preview-head">
        <div>
          <h3>${escapeHtml(row.subject || "Message")}</h3>
          <span class="small muted">${escapeHtml(row.to_addr || "no recipient")} · ${escapeHtml(fmtDate(row.at))} · ${escapeHtml(row.mode || "file")}</span>
        </div>
        <button class="link-btn" data-case-open="${escapeHtml(data.case_id || row.case_id || "")}">Open case</button>
      </div>`;
    const pre = document.createElement("pre");
    pre.textContent = data.body || data.content || "";
    preview.appendChild(pre);
    bindCaseOpen(preview);
  } catch (err) {
    $("#mail-preview").innerHTML = `<p class="empty">Could not load message: ${escapeHtml(err.message)}</p>`;
  }
}

async function loadSettings() {
  try {
    const [health, me] = await Promise.allSettled([
      api("/healthz"),
      api("/api/auth/me"),
    ]);
    if (health.status === "fulfilled") {
      state.health = health.value;
      updateVersion();
    }
    if (me.status === "fulfilled") {
      state.me = me.value;
      updateUser();
    }
    if (health.status !== "fulfilled" && me.status !== "fulfilled") {
      throw health.reason || me.reason;
    }
    renderSettings();
  } catch (err) {
    $("#settings-runtime").innerHTML = `<p class="empty">Could not load settings: ${escapeHtml(err.message)}</p>`;
  }
}

function renderSettings() {
  const health = state.health || {};
  const me = state.me || {};
  const storage = health.storage || {};
  const rows = [
    ["Service", health.service || "consult-homeopathic"],
    ["Status", health.status || "unknown"],
    ["Version", health.version || "—"],
    ["Provider", health.provider || "—"],
    ["Model", health.model || "rules"],
    ["Engine", health.engine || "—"],
    ["Mode", health.mode || "—"],
    ["Model key", health.llm_key ? "configured" : "not set"],
    ["Email delivery", health.email || "—"],
    ["Dashboard auth", health.dashboard_auth ? "password on" : "open (demo)"],
    ["Database", storage.database || "—"],
    ["Cases stored", storage.cases ?? 0],
    ["Pending review", storage.pending_review ?? 0],
    ["Follow-ups due", storage.followups_due ?? 0],
  ];
  $("#settings-runtime").innerHTML = `<div class="kv-card">${rows.map(([key, value]) => `
    <div class="kv-row"><span>${escapeHtml(key)}</span><b>${escapeHtml(value)}</b></div>`).join("")}</div>`;

  $("#settings-env").innerHTML = `
    <div class="config-list">
      <p><code>CONSULT_DASHBOARD_PASSWORD</code> turns on the sign-in page and protects staff APIs. Empty means open demo mode.</p>
      <p><code>CONSULT_SESSION_SECRET</code> signs session cookies. Derived from the password when unset.</p>
      <p><code>CONSULT_PUBLIC_URL</code> builds patient follow-up and email links.</p>
      <p><code>CONSULT_DOCTOR_EMAIL</code> receives escalation alerts when a check-in reports a red flag.</p>
      <p><code>SMTP_HOST</code> and <code>SMTP_FROM</code> switch delivery from local <code>.eml</code> files to real email.</p>
      <p><code>VULTR_API_KEY</code> and <code>VULTR_MODEL</code> configure the inference provider; keys stay server-side.</p>
      <p>These values are read on the server and are never exposed to patient pages.</p>
    </div>`;

  const enabled = Boolean(me.enabled);
  $("#settings-access").innerHTML = `
    <div class="detail-card ${enabled ? "soft" : "warn"}">
      <h3>${enabled ? "Dashboard password enabled" : "Dashboard is open (demo)"}</h3>
      <p>${enabled
        ? `Signed in as <b>${escapeHtml(me.user || "doctor")}</b>. Sessions last 8 hours and are signed with an HMAC cookie.`
        : "Set <code>CONSULT_DASHBOARD_PASSWORD</code> on the server to require a shared clinic password before staff APIs and case records are available."}</p>
      ${enabled ? '<div class="form-actions" style="justify-content:flex-start"><button class="btn ghost small" id="settings-logout">Sign out</button></div>' : ""}
    </div>`;
  const settingsLogout = $("#settings-logout");
  if (settingsLogout) settingsLogout.addEventListener("click", logout);
}

async function copyText(value) {
  if (!value) {
    toast("No follow-up link to copy.", "error");
    return;
  }
  try {
    await navigator.clipboard.writeText(value);
    toast("Follow-up link copied.");
  } catch (err) {
    const field = document.createElement("textarea");
    field.value = value;
    field.style.position = "fixed";
    field.style.opacity = "0";
    document.body.appendChild(field);
    field.select();
    document.execCommand("copy");
    field.remove();
    toast("Follow-up link copied.");
  }
}

async function logout() {
  try {
    await fetch("/api/auth/logout", { method: "POST", credentials: "same-origin" });
  } catch (err) {
    toast("Could not sign out. Try again.", "error");
    return;
  }
  location.replace("/login");
}

function refreshCurrent() {
  if (state.view === "overview") loadOverview();
  if (state.view === "cases") loadCases();
  if (state.view === "follow-ups") loadFollowups();
  if (state.view === "outbox") loadOutbox();
  if (state.view === "settings") loadSettings();
}

function bindChrome() {
  $$(".nav-item").forEach((item) => {
    item.addEventListener("click", () => setView(item.dataset.view));
  });
  $$("[data-goto]").forEach((element) => {
    element.addEventListener("click", () => setView(element.dataset.goto));
  });
  $$(".drawer-tab").forEach((tab) => {
    tab.addEventListener("click", () => {
      if (state.activeTab === "decision") captureDraft();
      state.activeTab = tab.dataset.tab;
      renderDrawer();
    });
  });
  $("#drawer-close").addEventListener("click", closeCase);
  $("#case-overlay").addEventListener("click", (event) => {
    if (event.target === $("#case-overlay")) closeCase();
  });
  document.addEventListener("keydown", (event) => {
    if (event.key === "Escape" && !$("#case-overlay").classList.contains("hidden")) {
      closeCase();
    }
  });

  $("#dash-refresh").addEventListener("click", refreshCurrent);
  $("#system-refresh").addEventListener("click", loadOverview);
  $("#cases-refresh").addEventListener("click", loadCases);
  $("#followups-refresh").addEventListener("click", loadFollowups);
  $("#outbox-refresh").addEventListener("click", loadOutbox);
  $("#settings-refresh").addEventListener("click", loadSettings);
  $("#logout-btn").addEventListener("click", logout);

  $("#case-search").addEventListener("input", (event) => {
    clearTimeout(searchTimer);
    const value = event.target.value;
    searchTimer = setTimeout(() => {
      state.caseQuery.q = value.trim();
      loadCases();
    }, 250);
  });
  $("#case-status").addEventListener("change", (event) => {
    state.caseQuery.status = event.target.value;
    loadCases();
  });
  $("#case-urgency").addEventListener("change", (event) => {
    state.caseQuery.urgency = event.target.value;
    loadCases();
  });
  $$("#followup-filters .filter-chip").forEach((chip) => {
    chip.addEventListener("click", () => {
      state.followState = chip.dataset.state || "";
      renderFollowups();
    });
  });
  window.addEventListener("hashchange", () => {
    const view = location.hash.slice(1);
    if (VIEW_META[view] && view !== state.view) setView(view);
  });
}

async function boot() {
  bindChrome();
  try {
    state.me = await api("/api/auth/me");
  } catch (err) {
    return;
  }
  updateUser();
  if (state.me.enabled && !state.me.authenticated) {
    location.replace(`/login?next=${encodeURIComponent("/doctor")}`);
    return;
  }
  const requested = location.hash.slice(1);
  setView(VIEW_META[requested] ? requested : "overview");
  if (state.view !== "overview") loadOverview();
  const deepCase = new URLSearchParams(location.search).get("case");
  if (deepCase) {
    setView("cases");
    openCase(deepCase);
  }
}

boot();
