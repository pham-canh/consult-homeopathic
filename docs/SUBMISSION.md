# Lablab submission copy

## Project title

Consult Homeopathic Physicians

## One-line pitch

AI prepares the case; a licensed doctor makes the decision and approves the plan.

## Challenge

Challenge 2 — Powering the Future of Work (Vultr: Agent Rush Hackathon)

## Short description

Consult Homeopathic Physicians is an AI intake agent with a doctor in the loop.
It collects symptoms and history, stops emergencies with a deterministic red-flag
gate, suggests care options, and prepares a structured case. A doctor reviews and
approves the plan on a dashboard; only then is it emailed to the patient. The AI
never diagnoses or prescribes.

## Long description

Clinics lose time on routine information gathering, and patients delay care
because an appointment takes hours. This prototype separates the information
work from the medical judgment.

The patient talks to an intake agent in plain language. The agent asks short
follow-up questions, checks for red flags, extracts a structured case (symptoms,
duration, severity, allergies, medications, history), and proposes two or three
care paths. When the patient chooses one, the case moves to a doctor dashboard.
The doctor reads the summary, sees allergy warnings and the full conversation,
edits the advice or prescription, and approves. The approved plan is emailed to
the patient, and a follow-up check escalates automatically if the patient reports
a red flag.

Safety is structural, not a prompt: a regex red-flag list runs before every model
call and cannot be overridden; the approval endpoint is the only path that sends
email; prescriptions are entered by the doctor; every action is written to an
audit trail. The app is a prototype with synthetic data and is not a medical
device.

Vultr is the central backend. A Vultr Cloud Compute VM runs the FastAPI app,
SQLite case store, dashboard, and email pipeline. Every model call goes through
Vultr Serverless Inference (OpenAI-compatible) using a DeepSeek model.

## Built with

Python, FastAPI, SQLite, vanilla HTML/CSS/JS, Vultr Cloud Compute,
Vultr Serverless Inference, Caddy, systemd.

## Links

- Live app: https://consult.139.180.147.61.sslip.io/
- Doctor dashboard: https://consult.139.180.147.61.sslip.io/doctor
- Health: https://consult.139.180.147.61.sslip.io/healthz
- Source: https://github.com/pham-canh/consult-homeopathic
- Screenshots: `docs/ui.png`, `docs/doctor.png`

## Tags

`healthcare`, `agentic-workflow`, `human-in-the-loop`, `fastapi`, `vultr`,
`serverless-inference`, `patient-intake`, `safety`

## Demo accounts / data

No login is needed for the hackathon demo. All records are synthetic. The doctor
dashboard is intentionally open for judges; a production deployment would add
authentication and consent management.

## What is complete

- Patient intake, emergency gate, care options, structured summary
- Doctor review, edit, approve, allergy check
- Email delivery (real SMTP when configured; otherwise a labelled `.eml` outbox)
- Audit trail, follow-up escalation
- 17 automated tests
- Live deployment with HTTPS on a Vultr VM

## Honest limitations

- Email uses a simulated outbox unless SMTP credentials are supplied.
- No real patient data, no video calls, no payments, no doctor verification.
- The allergy check is a small explicit cross-reactivity list, not a clinical
  interaction database.
- A production version needs authentication, encryption at rest, consent, and
  health-data compliance.
