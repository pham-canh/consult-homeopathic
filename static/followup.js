/* Public follow-up page: the token in the URL is the only credential. */
const $ = (id) => document.getElementById(id);
const token = location.pathname.split("/").filter(Boolean).pop();
const escapeHtml = (value) => String(value ?? "")
  .replaceAll("&", "&amp;").replaceAll("<", "&lt;").replaceAll(">", "&gt;")
  .replaceAll('"', "&quot;");

const COPY = {
  title: "How are you feeling?",
  intro: "This is a scheduled check-in for case",
  advice: "Your doctor's advice",
  placeholder: "Describe how you feel today…",
  send: "Send update",
  sent: "Thank you. The clinic has been notified.",
  escalated: "Your report contains a warning sign. Please seek emergency care now.",
  missing: "This check-in link is not valid.",
};

async function load() {
  const card = $("followup-card");
  try {
    const res = await fetch(`/api/follow-up/${encodeURIComponent(token)}`);
    if (!res.ok) throw new Error("invalid");
    const data = await res.json();
    const item = data.follow_up;
    card.innerHTML = `
      <span class="pill">${escapeHtml(item.case_id)}</span>
      <h1>${escapeHtml(COPY.title)}</h1>
      <p class="muted">${escapeHtml(COPY.intro)} ${escapeHtml(item.case_id)}.</p>
      <div class="card pad soft">
        <div class="small muted">${escapeHtml(COPY.advice)}</div>
        <p>${escapeHtml(item.advice || "—")}</p>
        ${item.prescription ? `<div class="small muted">Prescription</div>
          <p>${escapeHtml(item.prescription)}</p>` : ""}
      </div>
      <div class="field">
        <label>${escapeHtml(COPY.title)}</label>
        <textarea id="report" placeholder="${escapeHtml(COPY.placeholder)}"></textarea>
      </div>
      <div class="spacer"></div>
      <button class="btn" id="send">${escapeHtml(COPY.send)}</button>
      <p class="small" id="result"></p>`;
    $("send").onclick = async () => {
      const text = $("report").value.trim();
      if (!text) return;
      $("send").disabled = true;
      try {
        const response = await fetch(`/api/follow-up/${encodeURIComponent(token)}`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ report: text }),
        });
        const body = await response.json().catch(() => ({}));
        if (!response.ok) {
          const detail = Array.isArray(body.detail)
            ? body.detail.map((item) => item.msg || String(item)).join("; ")
            : body.detail;
          throw new Error(detail || "send failed");
        }
        const status = body.follow_up.status;
        $("result").textContent = status === "emergency" ? COPY.escalated : COPY.sent;
        $("result").className = status === "emergency" ? "small warn" : "small";
        $("report").disabled = true;
      } catch (err) {
        $("result").textContent = err.message;
        $("send").disabled = false;
      }
    };
  } catch {
    card.innerHTML = `<h1>${escapeHtml(COPY.missing)}</h1>
      <p class="muted">Ask the clinic to send a new check-in link.</p>`;
  }
}

load();
