/* Patient intake flow. Talks only to the same-origin FastAPI app. */
const $ = (id) => document.getElementById(id);
let caseId = null;
let finished = false;
let mediaRecorder = null;
let mediaStream = null;
let voiceChunks = [];
let voiceBusy = false;
let voiceEnabled = false;

const escapeHtml = (value) => String(value ?? "")
  .replaceAll("&", "&amp;").replaceAll("<", "&lt;").replaceAll(">", "&gt;")
  .replaceAll('"', "&quot;");

async function api(path, options = {}) {
  const res = await fetch(path, {
    headers: { "Content-Type": "application/json" },
    ...options,
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

function addMessage(text, role = "agent", meta = "") {
  const box = document.createElement("div");
  box.className = `msg ${role}`;
  box.innerHTML = escapeHtml(text) +
    (meta ? `<span class="meta">${escapeHtml(meta)}</span>` : "");
  $("chat-log").appendChild(box);
  $("chat-log").scrollTop = $("chat-log").scrollHeight;
}

function playAudio(base64, mime = "audio/mpeg") {
  if (!base64) return;
  const audio = new Audio(`data:${mime};base64,${base64}`);
  audio.play().catch(() => {
    const btn = document.createElement("button");
    btn.className = "chip";
    btn.type = "button";
    btn.textContent = "Play voice reply";
    btn.onclick = () => audio.play().catch(() => {});
    $("chat-log").appendChild(btn);
    $("chat-log").scrollTop = $("chat-log").scrollHeight;
  });
}

function applyTurn(data) {
  setStatus(data.case);
  if (data.emergency) {
    showEmergency();
    return;
  }
  if (data.case.care_options?.length && data.case.status === "intake") {
    renderOptions(data.case.care_options);
  }
  if (data.audio) playAudio(data.audio, data.audio_mime);
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
    btn.innerHTML = `<b>${escapeHtml(option.label || option.name)}</b><span>${escapeHtml(option.why || "")}</span>`;
    btn.onclick = () => choose(option.name, option.label || option.name);
    box.appendChild(btn);
  });
}

function showEmergency() {
  finished = true;
  const slot = $("emergency-slot");
  slot.innerHTML = `<div class="emergency-banner">Intake stopped for safety.
    Follow the emergency guidance above now.</div>`;
  $("chat-text").disabled = true;
  $("send-btn").disabled = true;
  $("attach-btn").disabled = true;
  $("mic-btn").disabled = true;
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
    applyTurn(data);
  } catch (err) {
    addMessage(`The intake service returned an error: ${err.message}`, "emergency");
  } finally {
    $("send-btn").disabled = false;
  }
}

async function choose(option, label = option) {
  if (!caseId || finished) return;
  $("options").innerHTML = "";
  addMessage(`I choose: ${label}`, "patient", "you");
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
    $("attach-btn").disabled = true;
    $("mic-btn").disabled = true;
  } catch (err) {
    addMessage(`Could not submit the choice: ${err.message}`, "emergency");
  }
}

$("start-btn").onclick = start;
$("chat-form").onsubmit = (event) => {
  event.preventDefault();
  send($("chat-text").value);
};

async function uploadReport(file) {
  if (!caseId || finished || !file) return;
  const note = $("upload-note");
  note.textContent = `Reading ${file.name}…`;
  const body = new FormData();
  body.append("file", file);
  try {
    const res = await fetch(`/api/intake/${caseId}/report`, {
      method: "POST", body,
    });
    const data = await res.json().catch(() => ({}));
    if (!res.ok) throw new Error(data.detail || `HTTP ${res.status}`);
    const report = data.case.reports[data.case.reports.length - 1];
    setStatus(data.case);
    addMessage(data.reply || `Report received: ${report.filename}. ${report.summary}`,
      "agent", "document-reader");
    note.textContent = `Read ${report.filename}: ${report.findings.length} value(s) found.`;
  } catch (err) {
    note.textContent = `Could not read the report: ${err.message}`;
  } finally {
    $("report-file").value = "";
  }
}

$("attach-btn").onclick = () => $("report-file").click();
$("report-file").onchange = () => uploadReport($("report-file").files[0]);

function preferredMime() {
  const types = ["audio/webm;codecs=opus", "audio/webm", "audio/mp4",
    "audio/ogg;codecs=opus"];
  return types.find((type) => window.MediaRecorder &&
    MediaRecorder.isTypeSupported(type)) || "";
}

async function startVoice() {
  if (!voiceEnabled) {
    addMessage("Voice input is not configured on this server.", "agent");
    return;
  }
  if (!caseId || finished || voiceBusy) return;
  if (mediaRecorder && mediaRecorder.state === "recording") {
    mediaRecorder.stop();
    return;
  }
  if (!navigator.mediaDevices?.getUserMedia || !window.MediaRecorder) {
    addMessage("This browser does not support microphone recording.", "agent");
    return;
  }
  try {
    mediaStream = await navigator.mediaDevices.getUserMedia({ audio: true });
    voiceChunks = [];
    const mime = preferredMime();
    mediaRecorder = mime
      ? new MediaRecorder(mediaStream, { mimeType: mime })
      : new MediaRecorder(mediaStream);
    mediaRecorder.ondataavailable = (event) => {
      if (event.data && event.data.size) voiceChunks.push(event.data);
    };
    mediaRecorder.onstop = async () => {
      const type = mediaRecorder.mimeType || "audio/webm";
      if (mediaStream) {
        mediaStream.getTracks().forEach((track) => track.stop());
        mediaStream = null;
      }
      $("mic-btn").classList.remove("recording");
      $("mic-btn").textContent = "Mic";
      const blob = new Blob(voiceChunks, { type });
      voiceChunks = [];
      if (blob.size) await sendVoice(blob);
    };
    mediaRecorder.start();
    $("mic-btn").classList.add("recording");
    $("mic-btn").textContent = "Stop";
    $("upload-note").textContent = "Listening… click Stop when you finish.";
  } catch (err) {
    addMessage(`Microphone unavailable: ${err.message}`, "agent");
    $("upload-note").textContent = "";
  }
}

async function sendVoice(blob) {
  voiceBusy = true;
  $("mic-btn").disabled = true;
  $("upload-note").textContent = "Transcribing…";
  const extension = blob.type.includes("mp4") ? "m4a" : "webm";
  const body = new FormData();
  body.append("file", blob, `voice.${extension}`);
  try {
    const res = await fetch(`/api/intake/${caseId}/voice`, {
      method: "POST", body,
    });
    const data = await res.json().catch(() => ({}));
    if (!res.ok) throw new Error(data.detail || `HTTP ${res.status}`);
    addMessage(data.transcript || "(voice message)", "patient", "you · voice");
    addMessage(data.reply, data.emergency ? "emergency" : "agent",
      data.engine || "voice");
    $("upload-note").textContent = data.audio
      ? "Spoken reply ready." : "Voice reply text ready.";
    applyTurn(data);
  } catch (err) {
    addMessage(`Voice error: ${err.message}`, "emergency");
    $("upload-note").textContent = "";
  } finally {
    voiceBusy = false;
    if (!finished) $("mic-btn").disabled = false;
  }
}

$("mic-btn").onclick = startVoice;

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
    const voice = health.voice || {};
    voiceEnabled = Boolean(voice.enabled);
    $("mic-btn").disabled = !voiceEnabled;
    $("mic-btn").title = voiceEnabled
      ? "Record a voice message"
      : "Voice requires a configured voice provider on the server";
    $("engine-pill").textContent =
      `LLM: ${health.llm_key ? health.model : "no key"} · ${health.mode}` +
      (voiceEnabled ? " · voice" : "");
    $("engine-pill").className = "pill" + (health.llm_key ? "" : " amber");
  } catch {
    $("engine-pill").textContent = "engine offline";
    $("engine-pill").className = "pill red";
    $("mic-btn").disabled = true;
  }
})();
