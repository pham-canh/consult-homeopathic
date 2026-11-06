# Consult Homeopathic Physicians

**AI-assisted patient intake with a doctor in the loop.**

Event: [Vultr: Agent Rush Hackathon](https://lablab.ai/ai-hackathons/vultr-hackathon)
Challenge: **2 — Powering the Future of Work**

**Live demo:** <https://consult.139.180.147.61.sslip.io/> ·
**Doctor dashboard:** <https://consult.139.180.147.61.sslip.io/doctor> ·
**Health:** <https://consult.139.180.147.61.sslip.io/healthz>

![Patient intake](docs/ui.png)

The agent collects symptoms and history in a short conversation, screens for
emergency red flags, proposes care options, and prepares a structured case. A
licensed doctor reviews that case on a dashboard, edits the plan, and approves
it. Only then is the plan emailed to the patient. The agent never diagnoses and
never prescribes.

## Why this fits Challenge 2

Challenge 2 is an enterprise multi-step workflow, not a code sandbox. This app is
four actors and seven steps in one public product:

```
Patient browser ─┐
                 ├─ FastAPI on a Vultr VM ── Vultr Serverless Inference
Doctor browser  ─┘        │
                          ├── SQLite case store + audit trail
                          └── email delivery (SMTP or local mailbox)
```

1. Patient intake conversation
2. Deterministic emergency gate
3. Structured case extraction
4. Care options and patient choice
5. Doctor review and approval
6. Email delivery
7. Follow-up check with escalation

Vultr is the central backend: the VM runs the orchestration, the database, the
static frontend, and every model call goes through
`https://api.vultrinference.com/v1`.

## Safety design

- **No diagnosis, no prescribing by AI.** The agent only gathers information and
  drafts a summary. Prescription text is entered by the doctor.
- **Human approval is a hard gate.** `/approve` is the only path that sends
  email; the agent cannot call it.
- **Emergency screening is deterministic.** A regex red-flag list runs before the
  model. A model flag can also stop the flow, but the rule gate can never be
  overridden. Negated phrases ("no chest pain") are ignored.
- **Honest labels.** Every reply records its engine (`vultr / <model>` or
  `rules (...)`). A fallback is never presented as a model answer.
- **Synthetic data only.** The prototype is not a medical device and must not be
  used with real patient records.

## Run locally

```bash
cd consult-homeopathic
python3 -m venv .venv && . .venv/bin/activate
pip install -r requirements.txt -r requirements-dev.txt
cp .env.example .env      # fill ONE provider below
python3 app.py            # http://127.0.0.1:8000
```

### Pick any provider — no model is fixed

Fill whichever key and model you have. The app uses the first provider with a
key, or the one named in `INFERENCE_PROVIDER`. Model ids are never hard-coded.

| Provider | Key env | Model env | Base URL default |
|---|---|---|---|
| Vultr (submitted demo) | `VULTR_API_KEY` | `VULTR_MODEL` | `api.vultrinference.com/v1` |
| OpenAI / ChatGPT | `OPENAI_API_KEY` | `OPENAI_MODEL` | `api.openai.com/v1` |
| Anthropic / Claude | `ANTHROPIC_API_KEY` | `ANTHROPIC_MODEL` | `api.anthropic.com/v1` |
| Google / Gemini | `GEMINI_API_KEY` or `GOOGLE_API_KEY` | `GEMINI_MODEL` | `generativelanguage.googleapis.com/v1beta` |
| Any OpenAI-compatible | `INFERENCE_API_KEY` | `INFERENCE_MODEL` | set `INFERENCE_BASE_URL` |

`INFERENCE_MODEL` also works as a shared fallback for any provider. Aliases
(`chatgpt`, `claude`, `google`, `custom`) are accepted in `INFERENCE_PROVIDER`.
`/healthz` shows the active provider, the model, and the configured slots.

Without a key the app still runs and says so: the intake falls back to the
deterministic rule engine, and `/healthz` reports `llm_key: false`.

Run the tests (no network, no key):

```bash
CONSULT_FAKE_LLM=1 python3 -m pytest tests/ -q
```

## API

| Method | Path | Purpose |
|---|---|---|
| GET | `/healthz` | storage, model, key, mode |
| GET | `/` | patient intake |
| GET | `/doctor` | doctor dashboard |
| POST | `/api/intake/start` | open a case |
| POST | `/api/intake/{id}/message` | one patient turn (safety gate + LLM) |
| POST | `/api/cases/{id}/choose` | choose a care option |
| GET | `/api/doctor/cases?status=` | review queue |
| POST | `/api/cases/{id}/approve` | doctor decision + email |
| POST | `/api/cases/{id}/follow-up` | patient check-in, escalates on red flags |
| GET | `/api/mailbox` | sent-plan outbox |
| GET | `/api/cases/{id}` | full case, audit trail, allergy warnings |

## The case record

One JSON document is shared by both flows. Key fields: `case_id`, `patient`
(age, allergies, medications, history, email), `chief_complaint`, `symptoms`,
`duration_days`, `severity`, `red_flags`, `urgency`, `care_options`,
`selected_option`, `summary`, `doctor`, `email`, `transcript`, `status`
(`intake` → `pending_review` → `delivered`, or `emergency`).

## Deploy on Vultr

The app runs directly on an Ubuntu 24.04 VM (not in a container) so it can own
SQLite and send mail.

**One-command update from the developer machine** (needs SSH access + rsync):

```bash
./deploy/deploy.sh                    # uses the `vultr` SSH alias
CONSULT_HOST=root@1.2.3.4 ./deploy/deploy.sh
```

`vultr` is a normal `~/.ssh/config` Host entry (HostName, User, IdentityFile).
It rsyncs the tree to `/opt/consult`, installs requirements, restarts
`consult`, and prints `/healthz`. `.env` stays on the server and is never
copied; `.venv`, `out`, and caches are excluded.

First-time setup on a fresh VM:

```bash
sudo adduser --system --group --home /opt/consult consult
sudo mkdir -p /opt/consult /etc/consult /var/lib/consult
# copy the repo to /opt/consult, then:
sudo -u consult python3 -m venv /opt/consult/.venv
sudo -u consult /opt/consult/.venv/bin/pip install -r /opt/consult/requirements.txt
sudo install -m 600 /dev/null /etc/consult/consult.env   # add the same vars as .env
sudo install -m 644 deploy/consult.service /etc/systemd/system/consult.service
sudo systemctl daemon-reload && sudo systemctl enable --now consult
```

Caddy provides HTTPS (`deploy/Caddyfile`). The public URL is the Vultr VM host,
for example `https://consult.<vm-ip>.sslip.io/`.

## Demo script (about two minutes)

1. Patient: "cough and fever for five days, allergic to penicillin", choose
   **Online doctor review**.
2. Second patient reports chest pain; the agent stops and shows emergency
   guidance. This is the safety moment.
3. Doctor dashboard: open the pending case, see the structured summary and the
   allergy warning, edit the advice, approve.
4. Open the outbox and show the exact email the patient received.
5. Close on value: a case prepared in minutes instead of a full appointment slot.

## Submission assets

- `docs/SUBMISSION.md` — title, short/long description, tags, honest limitations
- `docs/VIDEO_SCRIPT.md` — two-minute shot list with narration
- `docs/ui.png`, `docs/doctor.png` — current screenshots

## What is deliberately out of scope

Real patient data, real payments, video calls, doctor identity verification, and
automated diagnosis or prescribing.

## Team

- Canh Pham — backend, Vultr inference, workflow, deployment
- Team roles to be confirmed in the hackathon chat

This is a hackathon prototype. It is not a medical device and does not provide
medical advice.
