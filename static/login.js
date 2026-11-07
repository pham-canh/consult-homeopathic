const form = document.getElementById("login-form");
const password = document.getElementById("password");
const errorBox = document.getElementById("login-error");
const submit = document.getElementById("login-btn");
const toggle = document.getElementById("toggle-password");

function destination() {
  const next = new URLSearchParams(location.search).get("next") || "/doctor";
  if (!next.startsWith("/") || next.startsWith("//")) return "/doctor";
  return next;
}

toggle.onclick = () => {
  const showing = password.type === "text";
  password.type = showing ? "password" : "text";
  toggle.textContent = showing ? "Show" : "Hide";
};

form.onsubmit = async (event) => {
  event.preventDefault();
  errorBox.classList.add("hidden");
  submit.disabled = true;
  submit.textContent = "Signing in…";
  try {
    const response = await fetch("/api/auth/login", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ password: password.value }),
    });
    const data = await response.json().catch(() => ({}));
    if (!response.ok) {
      throw new Error(data.detail || "Sign in failed.");
    }
    location.replace(destination());
  } catch (err) {
    errorBox.textContent = err.message;
    errorBox.classList.remove("hidden");
    password.select();
    submit.disabled = false;
    submit.textContent = "Sign in";
  }
};
