const $ = (id) => document.getElementById(id);
const token = decodeURIComponent((location.pathname.split("/").pop() || "").trim());

function showError(message) {
  $("pay-body").innerHTML = "";
  const p = document.createElement("p");
  p.className = "emergency-banner";
  p.textContent = message;
  $("pay-body").appendChild(p);
}

function renderReceipt(payment, caseInfo) {
  $("pay-meta").textContent = `${caseInfo.case_id} · ${caseInfo.patient_name || "patient"}`;
  $("pay-amount").textContent = payment.amount_display;
  $("pay-body").innerHTML = "";
  const box = document.createElement("div");
  box.className = "pay-receipt";
  const status = document.createElement("span");
  status.className = "pill";
  status.textContent = "Paid (demo)";
  const line = document.createElement("p");
  line.innerHTML = "<b></b> · <span></span>";
  line.querySelector("b").textContent = payment.amount_display;
  line.querySelector("span").textContent = payment.method_label || "demo method";
  const when = document.createElement("p");
  when.className = "small muted";
  when.textContent = payment.paid_at
    ? `Recorded ${new Date(payment.paid_at).toLocaleString()}`
    : "Recorded just now";
  box.append(status, line, when);
  $("pay-body").appendChild(box);
}

function renderForm(payment, caseInfo) {
  $("pay-meta").textContent = `${caseInfo.case_id} · ${caseInfo.patient_name || "patient"}`;
  $("pay-amount").textContent = payment.amount_display;
  $("pay-body").innerHTML = "";

  const form = document.createElement("form");
  form.id = "pay-form";
  const legend = document.createElement("p");
  legend.className = "small";
  legend.innerHTML = "<b>Choose a demo payment method</b>";
  form.appendChild(legend);

  const methods = document.createElement("div");
  methods.className = "pay-methods";
  (payment.methods || []).forEach((method, index) => {
    const label = document.createElement("label");
    label.className = "pay-method";
    const input = document.createElement("input");
    input.type = "radio";
    input.name = "method";
    input.value = method.value;
    input.required = true;
    if (index === 0) input.checked = true;
    const span = document.createElement("span");
    span.textContent = method.label;
    label.append(input, span);
    methods.appendChild(label);
  });
  form.appendChild(methods);

  const button = document.createElement("button");
  button.className = "btn";
  button.type = "submit";
  button.textContent = `Pay ${payment.amount_display} (demo)`;
  form.appendChild(button);

  const note = document.createElement("p");
  note.className = "small muted";
  note.textContent = payment.note || "";
  form.appendChild(note);

  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    const selected = form.querySelector('input[name="method"]:checked');
    if (!selected) return;
    button.disabled = true;
    button.textContent = "Recording demo payment…";
    try {
      const response = await fetch(`/api/pay/${encodeURIComponent(token)}`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ method: selected.value }),
      });
      const data = await response.json().catch(() => ({}));
      if (!response.ok) throw new Error(data.detail || `HTTP ${response.status}`);
      renderReceipt(data.payment, caseInfo);
    } catch (error) {
      button.disabled = false;
      button.textContent = `Pay ${payment.amount_display} (demo)`;
      showError(`Could not record the demo payment: ${error.message}`);
    }
  });

  $("pay-body").appendChild(form);
}

async function load() {
  if (!token) {
    showError("This payment link is incomplete.");
    return;
  }
  try {
    const response = await fetch(`/api/pay/${encodeURIComponent(token)}`);
    const data = await response.json().catch(() => ({}));
    if (!response.ok) throw new Error(data.detail || `HTTP ${response.status}`);
    const payment = data.payment || {};
    const caseInfo = data.case || {};
    if (payment.status === "paid_demo") {
      renderReceipt(payment, caseInfo);
    } else {
      renderForm(payment, caseInfo);
    }
  } catch (error) {
    $("pay-meta").textContent = "";
    $("pay-amount").textContent = "—";
    showError(error.message || "Could not load this payment link.");
  }
}

load();
