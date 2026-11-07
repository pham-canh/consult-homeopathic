# Consult Homeopathic Physicians

**AI-assisted patient intake with a licensed doctor in the loop.**

[![tests](https://github.com/pham-canh/consult-homeopathic/actions/workflows/tests.yml/badge.svg)](https://github.com/pham-canh/consult-homeopathic/actions/workflows/tests.yml)

Event: [Vultr: Agent Rush Hackathon](https://lablab.ai/ai-hackathons/vultr-hackathon)
Live demo: https://consult-homeopathic.207.148.72.102.sslip.io/
Challenge: **2 — Powering the Future of Work**

> This is the complete, independently deployed submission build for Challenge 2.
> The public app, API, and doctor dashboard run on a dedicated Vultr VM.

The agent collects symptoms and history in a short conversation, screens for
emergency red flags, reads an uploaded lab report, proposes care options, and
prepares a structured case. A licensed doctor reviews that case on a dashboard,
edits the plan, and approves it. Only then is the plan emailed to the patient.
The agent never diagnoses and never prescribes.

This is a code-only submission; no demo video is included.

## What is in this build

| Area | Implemented |
|---|---|
| Conversational intake | Plain-language chat with follow-up questions and structured extraction |
| Emergency gate | Deterministic red-flag rules run before every model call; negation-aware; cannot be overridden |
| Lab report reader | `.txt`, `.md`, `.csv`, `.pdf` upload; deterministic value parsing plus an optional model summary; abnormal values flagged |
| Care options | Two or three care paths with plain-language reasons; the patient chooses one |
| Doctor dashboard | Review queue, full transcript, structured summary, allergy and interaction warnings, report findings, audit trail |
| Human approval | `/approve` is the only path that sends a plan; approval is single-use and blocked for emergency cases |
| Email delivery | Real SMTP when configured, otherwise a labelled `.eml` outbox |
| Follow-up agent | Check-in is scheduled after approval, emailed with a token link, and escalates automatically on a red flag |
| Safety checks | Allergy cross-reactivity and a short, visible drug-interaction list |
| Audit trail | Every patient, agent, safety, and doctor action is timestamped |
| Model providers | No model id bundled; Vultr, OpenAI, Anthropic, Gemini, and any OpenAI-compatible endpoint |
| Operations | Health check, SQLite persistence, Dockerfile, systemd unit, Caddy HTTPS, Vultr provisioning script |

Core and stretch features from the project overview are therefore present. The
only deliberately excluded items are real patient data, payments, video calls,
doctor identity verification, and automated diagnosis or prescribing.

## Screenshots

Patient intake with lab upload:

![Patient intake](docs/ui.png)

Doctor review dashboard with the structured case and audit trail:

![Doctor dashboard](docs/doctor.png)

## Architecture

```
Patient browser ─┐
                 ├─ FastAPI on a dedicated Vultr VM ── configured inference provider
Doctor browser  ─┤        │
Follow-up link  ─┘        ├── SQLite case store + audit trail + follow-up queue
                          ├── uploaded reports on local disk
                          └── email (SMTP or labelled .eml outbox)
```

One JSON case record is shared by both flows. Key fields: `case_id`, `patient`
(name, email, age, sex, allergies, medications, history),
`chief_complaint`, `symptoms`, `duration_days`, `severity`, `red_flags`,
`urgency`, `reports`, `care_options`, `selected_option`, `summary`, `doctor`,
`email`, `follow_up`, `transcript`, `needs_attention`, and `status`
(`intake` → `pending_review` → `delivered`, or `emergency`).

## Run locally

```bash
python3 -m venv .venv && . .venv/bin/activate
pip install -r requirements.txt -r requirements-dev.txt
cp .env.example .env
python3 scripts/configure_model.py   # choose a provider, model, and key
python3 app.py                       # http://127.0.0.1:8000
```

No model is hard-coded. The app uses the provider named in `INFERENCE_PROVIDER`,
or the first provider with a key:

| Provider | Key env | Model env | Base URL default |
|---|---|---|---|
| Vultr (submitted demo) | `VULTR_API_KEY` | `VULTR_MODEL` | `api.vultrinference.com/v1` |
| OpenAI / ChatGPT | `OPENAI_API_KEY` | `OPENAI_MODEL` | `api.openai.com/v1` |
| Anthropic / Claude | `ANTHROPIC_API_KEY` | `ANTHROPIC_MODEL` | `api.anthropic.com/v1` |
| Google / Gemini | `GEMINI_API_KEY` or `GOOGLE_API_KEY` | `GEMINI_MODEL` | `generativelanguage.googleapis.com/v1beta` |
| Any OpenAI-compatible | `INFERENCE_API_KEY` | `INFERENCE_MODEL` | set `INFERENCE_BASE_URL` |

### Switch provider or model

The team can change providers without touching code. The helper writes only the
gitignored, mode-600 `.env`; the key is read with a hidden prompt and never
printed:

```bash
python3 scripts/configure_model.py
python3 scripts/configure_model.py --provider claude --model claude-sonnet-4-5
python3 scripts/configure_model.py --provider openai-compatible \
  --model my-model --base-url http://localhost:11434/v1
python3 scripts/configure_model.py --provider gemini --model gemini-2.5-flash --test
```

Restart the app after saving, then check `/healthz` for the active provider and
model. The same settings can be edited directly in `.env`; supported aliases
include `chatgpt`, `claude`, `google`, `openrouter`, and `ollama`.

On the running VM, use the wrapper. It runs the same hidden-input helper against
`/opt/consult-homeopathic/.env`, restarts the service, and prints `/healthz`:

```bash
./deploy/configure_model.sh
```

The systemd unit loads that optional file after the server env file, so the new
provider takes effect on restart. Changing the local `.env` later does not alter
the VM env; use the wrapper or edit `/etc/consult-homeopathic/consult.env` and
restart.

Without a key the app still runs and says so: intake falls back to the
deterministic rule engine, and `/healthz` reports `llm_key: false`.

Run the tests (no network, no key, 70 tests):

```bash
CONSULT_FAKE_LLM=1 CONSULT_DISABLE_SCHEDULER=1 python3 -m pytest tests/ -q
```

## API

| Method | Path | Purpose |
|---|---|---|
| GET | `/healthz` | storage, model, key, scheduler |
| GET | `/` | patient intake |
| GET | `/doctor` | doctor dashboard |
| GET | `/follow-up/{token}` | public check-in page |
| POST | `/api/intake/start` | open a case (name, email) |
| POST | `/api/intake/{id}/message` | one patient turn (safety gate + model) |
| POST | `/api/intake/{id}/report` | upload a lab report |
| POST | `/api/cases/{id}/choose` | choose a care option |
| GET | `/api/doctor/cases?status=` | review queue |
| POST | `/api/cases/{id}/approve` | doctor decision, email plan, schedule follow-up |
| POST | `/api/cases/{id}/follow-up` | log a follow-up report |
| POST | `/api/cases/{id}/follow-up/send` | send the scheduled check-in now |
| GET/POST | `/api/follow-up/{token}` | read/submit the public check-in |
| GET | `/api/mailbox` | sent-plan and check-in outbox |
| GET | `/api/emails/{id}` | open one outbox email by id |
| GET | `/api/cases/{id}` | full case, reports, audit trail, warnings |

Invalid state transitions return `409`; invalid uploads return `400`; unknown
cases and tokens return `404`.

## Safety design

- **No diagnosis, no prescribing by AI.** The agent gathers information and
  drafts a summary. Prescription text is entered by the doctor.
- **Human approval is a hard gate.** `/approve` is the only path that sends a
  plan, requires `pending_review`, and cannot run twice. Emergency cases cannot
  be approved.
- **Emergency screening is deterministic.** A regex red-flag list runs before the
  model. A model flag can also stop the flow, but the rule gate can never be
  overridden. Negated phrases ("no chest pain") are ignored unless a contrast
  reintroduces a symptom ("no fever but chest pain").
- **Follow-up escalation is deterministic.** A red flag in a check-in moves the
  case to `emergency`, marks `needs_attention`, and alerts the clinic if
  `CONSULT_DOCTOR_EMAIL` is set.
- **Honest labels.** Every reply records its engine (`vultr / <model>` or
  `rules (...)`). A fallback is never presented as a model answer.
- **Synthetic data only.** The prototype is not a medical device and must not be
  used with real patient records.

## Deploy on a dedicated Vultr VM

This build is meant to own a VM so it never shares a database or service with
another project. The provisioning script creates a new Ubuntu 24.04 instance,
a firewall group, and an SSH key entry through the Vultr API.

```bash
# Put a Vultr API key with instance/firewall permissions in ~/.vultr_api_key
chmod 600 ~/.vultr_api_key

./deploy/provision_and_deploy.sh
```

Defaults: region `sgp`, plan `vc2-1c-2gb`, label `consult-homeopathic`. Override
with `VULTR_REGION`, `VULTR_PLAN`, or `VULTR_LABEL`. The script:

1. creates a firewall group (22, 80, 443) and the instance;
2. waits for the public IP;
3. rsyncs the tree to `/opt/consult-homeopathic`;
4. writes `/etc/consult-homeopathic/consult.env` from the local `.env` plus the
   server public URL (never committed);
5. creates the venv, installs requirements, installs the systemd unit;
6. configures Caddy HTTPS on `consult-homeopathic.<ip>.sslip.io`;
7. prints `/healthz`.

Later updates:

```bash
CONSULT_HOST=root@<ip> ./deploy/deploy.sh
./deploy/configure_model.sh           # change provider/key/model on the VM
```

Server layout: code `/opt/consult-homeopathic`, data
`/var/lib/consult-homeopathic`, env `/etc/consult-homeopathic/consult.env`, unit
`consult-homeopathic.service`.

### Docker alternative

```bash
cp .env.example .env   # fill a provider
docker compose up -d --build
```

The image runs as a non-root user and stores SQLite, reports, and emails in the
`/data` volume.

## Demo flow (about two minutes)

1. Patient: "cough and fever for five days, allergic to penicillin", attach a
   small lab report, choose **Online doctor review**.
2. Second patient reports chest pain; the agent stops and shows emergency
   guidance.
3. Doctor dashboard: open the pending case, see the structured summary, lab
   values, and allergy warning, edit the advice, approve.
4. Open the outbox and show the exact plan email; the follow-up link is in it.
5. Send the check-in now and open the public link; submit "chest pain" to show
   the automatic escalation and the `needs_attention` banner.

To make step 5 instant in a demo, set `FOLLOWUP_DAYS=0`.

## Submission assets

- `docs/SUBMISSION.md` — title, descriptions, tags, limitations
- `docs/ARCHITECTURE.md` — flow and threat boundaries
- `docs/ui.png`, `docs/doctor.png` — intake and dashboard screenshots
- This is a code-only submission; no video is included.

## What is deliberately out of scope

Real patient data, real payments, video calls, doctor identity verification, and
automated diagnosis or prescribing. The doctor dashboard is open for judges in
this demo; production needs authentication, consent, encryption at rest, and
health-data compliance.

## Team

- Canh Pham — backend, inference integration, workflow, deployment

This is a hackathon prototype. It is not a medical device and does not provide
medical advice.
