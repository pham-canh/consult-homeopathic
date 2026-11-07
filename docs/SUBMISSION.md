# Lablab submission copy

## Project title

Consult Homeopathic Physicians

## One-line pitch

AI prepares the case; a licensed doctor makes the decision and approves the plan.

## Challenge

Challenge 2 — Powering the Future of Work (Vultr: Agent Rush Hackathon)

## Short description

Consult Homeopathic Physicians is an AI intake agent with a doctor in the loop.
It collects symptoms and history in English, reads an uploaded lab
report, stops emergencies with a deterministic red-flag gate, suggests care
options, and prepares a structured case. A doctor reviews and approves the plan
on a dashboard; only then is it emailed to the patient. A follow-up agent checks
in later and escalates automatically on a red flag. The AI never diagnoses or
prescribes.

## Long description

Clinics lose time on routine information gathering, and patients delay care
because an appointment takes hours. This build separates the information work
from the medical judgment.

The patient talks to an intake agent in English. The agent asks short follow-up questions,
checks for red flags, extracts a structured case in English for the doctor, and
proposes two or three care paths. The patient can attach a text or PDF lab
report; numeric values are parsed and abnormal results are flagged for review.
When the patient chooses a path, the case moves to the doctor dashboard. The
doctor reads the summary, sees allergy and drug-interaction warnings, the report
findings, and the full conversation, then edits and approves the plan. The
approved plan is emailed, and a follow-up check-in is scheduled. If the patient
reports a red flag on the public check-in link, the case escalates and the clinic
is alerted.

Safety is structural, not a prompt: a regex red-flag list runs before every model
call and cannot be overridden; a reply guard blocks explicit dosing instructions;
the approval endpoint is the only path that sends email and is single-use;
prescriptions are entered by the doctor; every action is written to an audit
trail. The app is a prototype with synthetic data and is not a medical device.

Vultr is the central backend. A dedicated Vultr Cloud Compute VM runs the FastAPI
app, SQLite store, dashboard, report storage, and email pipeline. The submitted
demo calls Vultr Serverless Inference (OpenAI-compatible), with an offline rule
fallback that is always labelled. No model ID is hard-coded: the same build also
supports OpenAI, Anthropic, Gemini, and any OpenAI-compatible endpoint, so the
team can supply its own key and model. The VM, firewall group, and SSH key are
created by `deploy/vultr_provision.py`.

## Built with

Python, FastAPI, SQLite, vanilla HTML/CSS/JS, Vultr Cloud Compute,
Vultr Serverless Inference (plus OpenAI, Anthropic, Gemini, and
OpenAI-compatible endpoints), Caddy, systemd, Docker (optional).

## Links

- Live app: https://consult-homeopathic.207.148.72.102.sslip.io/
- Doctor dashboard: https://consult-homeopathic.207.148.72.102.sslip.io/doctor
- Health: https://consult-homeopathic.207.148.72.102.sslip.io/healthz
- Source: this repository
- This is a code-only submission; no video is included.

## Tags

`healthcare`, `agentic-workflow`, `human-in-the-loop`, `fastapi`, `vultr`,
`serverless-inference`, `patient-intake`, `safety`

## Demo accounts / data

No login is needed for the hackathon demo. All records are synthetic. The doctor
dashboard is intentionally open for judges; a production deployment would add
authentication and consent management.

## What is complete

- Patient intake, emergency gate, care options, structured summary
- Lab report upload and value parsing
- Doctor review, edit, approve, allergy and interaction checks
- Email delivery (real SMTP when configured; otherwise a labelled `.eml` outbox)
- Follow-up scheduling, public token check-in, automatic escalation
- Audit trail and health reporting
- Provider-agnostic inference with a hidden-prompt CLI for team keys
- 70 automated tests, Dockerfile, systemd unit, Caddy config, Vultr provisioner
- Dedicated Vultr VM deployment

## Honest limitations

- Email uses a simulated outbox unless SMTP credentials are supplied.
- No real patient data, no video calls, no payments, no doctor verification.
- The allergy and interaction lists are small and explicit, not a clinical
  database. The model summary is assistance, not a diagnosis.
- Image-based lab reports are rejected; only text and PDF are parsed.
- A production version needs authentication, encryption at rest, consent, and
  health-data compliance.
