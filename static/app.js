/* Patient intake flow. Talks only to the same-origin FastAPI app. */
const $ = (id) => document.getElementById(id);
let caseId = null;
let finished = false;

const escapeHtml = (value) => String(value ?? "")
  .replaceAll("&", "&amp;").replaceAll("<", "&lt;").replaceAll(">", "&gt;")
  .replaceAll('"', "&quot;");

async function api(path, options = {}) {
  const res = await fetch(path, {
    headers: { "Content-Type": "application/json" },
    ...options,
  });
  const data = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(data.detail || `HTTP ${res.status}`);
  return data;
}

function addMessage(text, role = "agent", meta = "") {
  const box = document.createElement("div");
  box.className = `msg ${role}`;
  box.innerHTML = escapeHtml(text) +
    (meta ? `<span class="meta">${escapeHtml(meta)}</span>` : "");
  $("chat-log").appendChild(box);
  $("chat-log").scrollTop = $("chat-log").scrollHeight;
}

function setStatus(caseData) {
  const status = caseData?.status || "new";
  const labels = {
    intake: "intake", emergency: "emergency", pending_review: "pending doctor",
    delivered: "delivered", new: "new",
  };
  const pill = $("case-status");
  pill.textContent = labels[status] || status;
  pill.className = "pill" + (status === "emergency" ? " red" :
    status === "pending_review" ? " amber" : "");
  if (caseData?.case_id) {
    $("status-line").textContent = `${caseData.case_id} · ${caseData.engine || "intake"}`;
  }
}

function renderOptions(options) {
  const box = $("options");
  box.innerHTML = "";
  (options || []).forEach((option) => {
    const btn = document.createElement("button");
    btn.className = "option";
    btn.innerHTML = `<b>${escapeHtml(option.name)}</b><span>${escapeHtml(option.why || "")}</span>`;
    btn.onclick = () => choose(option.name);
    box.appendChild(btn);
  });
}

function showEmergency(text) {
  finished = true;
  const slot = $("emergency-slot");
  slot.innerHTML = `<div class="emergency-banner">${escapeHtml(text)}</div>`;
  $("chat-text").disabled = true;
  $("send-btn").disabled = true;
  $("options").innerHTML = "";
}

async function start() {
  const name = $("name").value.trim();
  const email = $("email").value.trim();
  $("start-btn").disabled = true;
  try {
    const data = await api("/api/intake/start", {
      method: "POST",
      body: JSON.stringify({ name, email }),
    });
    caseId = data.case.case_id;
    $("start-form").classList.add("hidden");
    $("chat-area").classList.remove("hidden");
    addMessage(data.reply, "agent", "intake assistant");
    setStatus(data.case);
    const pending = sessionStorage.getItem("consult_sample");
    if (pending) {
      sessionStorage.removeItem("consult_sample");
      $("chat-text").value = pending;
      $("chat-form").requestSubmit();
    }
  } catch (err) {
    addMessage(`Could not start the intake: ${err.message}`, "agent");
    $("start-btn").disabled = false;
  }
}

async function send(text) {
  if (!caseId || finished || !text.trim()) return;
  addMessage(text, "patient", "you");
  $("chat-text").value = "";
  $("send-btn").disabled = true;
  try {
    const data = await api(`/api/intake/${caseId}/message`, {
      method: "POST",
      body: JSON.stringify({ text }),
    });
    addMessage(data.reply, data.emergency ? "emergency" : "agent", data.engine || "");
    setStatus(data.case);
    if (data.emergency) {
      showEmergency("Automated intake stopped. Please seek emergency care now.");
      return;
    }
    if (data.case.care_options?.length && data.case.status === "intake") {
      renderOptions(data.case.care_options);
    }
  } catch (err) {
    addMessage(`The intake service returned an error: ${err.message}`, "emergency");
  } finally {
    $("send-btn").disabled = false;
  }
}

async function choose(option) {
  if (!caseId || finished) return;
  $("options").innerHTML = "";
  addMessage(`I choose: ${option}`, "patient", "you");
  try {
    const data = await api(`/api/cases/${caseId}/choose`, {
      method: "POST",
      body: JSON.stringify({ option }),
    });
    setStatus(data.case);
    addMessage(`Your case ${data.case.case_id} is now with the doctor. ` +
      `You can watch the review on the doctor dashboard; the approved plan ` +
      `will be emailed to ${data.case.patient.email || "you"}.`,
      "agent", "workflow");
    finished = true;
    $("chat-text").disabled = true;
    $("send-btn").disabled = true;
  } catch (err) {
    addMessage(`Could not submit the choice: ${err.message}`, "emergency");
  }
}

$("start-btn").onclick = start;
$("chat-form").onsubmit = (event) => {
  event.preventDefault();
  send($("chat-text").value);
};

document.querySelectorAll("[data-sample]").forEach((chip) => {
  chip.onclick = () => {
    const kind = chip.dataset.sample;
    const routine = "I have had a cough and a mild fever for 5 days. " +
      "I am allergic to penicillin. My email is alex@example.test.";
    const emergency = "I have chest pain and shortness of breath.";
    $("name").value = $("name").value || "Alex Nguyen";
    $("email").value = $("email").value || "alex@example.test";
    if (caseId) {
      $("chat-text").value = kind === "emergency" ? emergency : routine;
      $("chat-form").requestSubmit();
    } else {
      sessionStorage.setItem("consult_sample",
        kind === "emergency" ? emergency : routine);
      start();
    }
  };
});

(async () => {
  try {
    const health = await api("/healthz");
    $("engine-pill").textContent =
      `LLM: ${health.llm_key ? health.model : "no key"} · ${health.mode}`;
    $("engine-pill").className = "pill" + (health.llm_key ? "" : " amber");
  } catch {
    $("engine-pill").textContent = "engine offline";
    $("engine-pill").className = "pill red";
  }
})();
