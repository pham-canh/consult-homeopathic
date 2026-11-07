# Lablab submission copy

## Project title

Consult Homeopathic Physicians

## One-line pitch

AI prepares the case; a licensed doctor makes the decision and approves the plan.

## Challenge

Challenge 2 — Powering the Future of Work (Vultr: Agent Rush Hackathon)

## Short description

Consult Homeopathic Physicians is an AI intake agent with a doctor in the loop.
It collects symptoms and history in English by text or push-to-talk voice,
reads an uploaded document, stops emergencies with a deterministic red-flag gate, suggests care
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
proposes two or three care paths. The patient can attach a text, CSV or PDF
document; numeric values are parsed, abnormal results are flagged, and the agent asks whether the document is related to the current symptoms. The doctor can open the original file.
When the patient chooses a path, the case moves to the clinic dashboard: an
operations console with volume and attention metrics, a searchable case queue,
tabbed case records (summary, documents, conversation, decision, audit), a
follow-up queue, the full outbox, and runtime settings. The doctor reads the
summary, sees allergy and drug-interaction warnings, the document findings, and the
full conversation, then edits and approves the plan. The approved plan is
emailed, and a follow-up check-in is scheduled. The email also includes a
clearly labelled demo consultation-fee link; it records a local receipt and
never collects card details or contacts a payment provider. If the patient
reports a red flag
on the public check-in link, the case escalates and the clinic is alerted.
Prior visits are linked by the email the patient supplied and shown as context
for the doctor. The follow-up check-in asks about appetite and diet when
relevant. Staff access uses a shared-password session; patient intake and
follow-up links stay public.

Safety is structural, not a prompt: a regex red-flag list runs before every model
call and cannot be overridden; a reply guard blocks explicit dosing instructions;
the approval endpoint is the only path that sends email and is single-use;
prescriptions are entered by the doctor; every action is written to an audit
trail. The app is a prototype with synthetic data and is not a medical device.

Vultr is the central backend. A dedicated Vultr Cloud Compute VM runs the FastAPI
app, SQLite store, dashboard, document storage, and email pipeline. The submitted
demo calls Vultr Serverless Inference (OpenAI-compatible), with an offline rule
fallback that is always labelled. Voice transcription and synthesis use the
Gemini audio API (`gemini-3.5-transcribe` and `gemini-3.8-flash-tts`); clinical
reasoning and case state stay on the Vultr-hosted app. No model ID is hard-coded: the same build also
supports OpenAI, Anthropic, Gemini, and any OpenAI-compatible endpoint, so the
team can supply its own key and model. The VM, firewall group, and SSH key are
created by `deploy/vultr_provision.py`.

## Business value

The buyer is a small independent clinic or telehealth team with 1–15 clinicians
that needs doctor oversight but cannot staff a full intake and documentation
team. Today, new-patient intake, history capture, lab-value transcription and
follow-up chasing consume clinical and front-desk time; urgent cases compete for
the same attention, and a missed red flag is the expensive failure.

The US has roughly 220,000–260,000 physician practices, and about 73% of
physician offices have fewer than 50 employees. At an initial price of $99 per
clinic per month, the US-only software ceiling is roughly $190M–$225M ARR before
expansion into telehealth and other English-speaking markets. This is a
conservative bottom-up planning assumption, not a forecast.

The model is clinic SaaS at $99–$299 per month depending on clinician count,
plus a usage tier for high-volume telehealth. The practice owner or operations
manager buys it; the clinician and front desk use it daily. If the product saves
10 minutes of intake and documentation per new patient, a clinic seeing 20 new
patients per week saves about 3.3 staff hours per week, before counting fewer
missed follow-ups and a complete audit trail.

AI is required because intake must understand free-form language, choose the
next question, extract a structured history and read an unstructured document.
A fixed form cannot do that, and a rules-only chatbot cannot handle the variety.
The model drafts, the deterministic safety gate blocks emergencies, and the
doctor makes the final decision.

## Built with

Python, FastAPI, SQLite, vanilla HTML/CSS/JS, Vultr Cloud Compute,
Vultr Serverless Inference (plus OpenAI, Anthropic, Gemini, and
OpenAI-compatible endpoints), Gemini audio API, Caddy, systemd, Docker (optional).

## Links

- Live app: https://consult-homeopathic.207.148.72.102.sslip.io/
- Doctor dashboard: https://consult-homeopathic.207.148.72.102.sslip.io/doctor
- Health: https://consult-homeopathic.207.148.72.102.sslip.io/healthz
- Source: this repository
- Cover: `docs/cover.png`
- Slide deck: `docs/pitch.pdf`
- This is a code-only submission; no video is included.

## Tags

`healthcare`, `agentic-workflow`, `human-in-the-loop`, `fastapi`, `vultr`,
`serverless-inference`, `patient-intake`, `safety`

## Demo accounts / data

All records are synthetic. Open the live dashboard at
https://consult-homeopathic.207.148.72.102.sslip.io/doctor and sign in with user
`doctor`. The shared demo password is set server-side through
`CONSULT_DASHBOARD_PASSWORD`; it is shared with judges in the submission access
notes and is not committed to the repository. Patient intake, care-option choice
and public follow-up links need no login. A production deployment would add
per-user identity, MFA, and consent management.

## What is complete

- Patient intake, emergency gate, care options, structured summary
- Document upload, value parsing, document-aware follow-up and doctor download
- Push-to-talk voice intake with spoken replies (Gemini audio; OpenAI fallback)
- Prior-visit history keyed by patient email, plus diet/appetite follow-up
- Doctor review, edit, approve, allergy and interaction checks
- Operations dashboard: overview, search/filters, case drawers, follow-up queue,
  outbox, runtime settings, shared-password sessions
- Email delivery (real SMTP when configured; otherwise a labelled `.eml` outbox)
- Follow-up scheduling, public token check-in, automatic escalation
- Demo-only consultation fee with a local `paid_demo` receipt and dashboard status
- Audit trail and health reporting
- Provider-agnostic inference with a hidden-prompt CLI for team keys
- 85 automated tests, Dockerfile, systemd unit, Caddy config, Vultr provisioner
- Dedicated Vultr VM deployment

## Honest limitations

- Email uses a simulated outbox unless SMTP credentials are supplied.
- No real patient data, no video calls, no real payment processing, no doctor verification. The consultation fee is a demo receipt only.
- The allergy and interaction lists are small and explicit, not a clinical
  database. The model summary is assistance, not a diagnosis.
- Image-based documents are rejected; only text, CSV and PDF are parsed.
- Voice is push-to-talk, not full-duplex, and needs browser microphone permission.
- Patient history is keyed by the supplied email, not a verified patient identity.
- Dashboard auth is one shared clinic password, not per-user identity or MFA.
- A production version needs per-user authentication, encryption at rest,
  consent, and health-data compliance.
