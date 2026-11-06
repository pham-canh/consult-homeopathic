# Architecture and safety boundaries

## Runtime

```
Patient browser ─┐
                 ├─ FastAPI (single Vultr VM) ── inference provider
Doctor browser  ─┤        │
Follow-up link  ─┘        ├─ SQLite: cases, audit, emails, follow-up queue
                          ├─ local disk: uploaded reports
                          └─ SMTP or labelled .eml outbox
```

One process serves the API and static frontend. SQLite is enough for a single-VM
prototype and keeps the deployment auditable. The follow-up scheduler is a
daemon thread in the same process; it claims rows in SQLite before sending so a
duplicate check-in cannot be sent by two workers.

## Workflow

1. `start_case` creates the JSON record and greets the patient.
2. Each message first passes `safety.detect_red_flags`. A match stops the flow
   and returns emergency guidance. The model never sees a message before this
   gate.
3. If no rule matches, the model (or the rule engine without a key) extracts a
   structured case and returns care options.
4. `choose_option` closes intake and moves the case to `pending_review`.
5. `approve` requires `pending_review`, writes the doctor decision, schedules a
   follow-up, and only then sends email.
6. The follow-up agent sends the scheduled check-in. A public token link accepts
   one report; a red flag escalates to `emergency` and sets `needs_attention`.

## Trust boundaries

| Boundary | Rule |
|---|---|
| Model → medical decision | The model cannot set approval, prescription, or delivery |
| Model → red flags | A model flag can stop the flow; it cannot clear a rule flag |
| Patient → case state | The patient can choose an option, not approve or edit the plan |
| Doctor → delivery | Approval is the only write path to email, and it is single-use |
| Upload → summary | File type and size are checked; parsed values are labelled |
| Follow-up token | Opaque random token; one public check-in form per link |

## Data

- `cases`: full JSON document per case.
- `audit`: append-only action log (timestamp, actor, action, detail).
- `emails`: outbox index (subject, recipient, mode, path).
- `followups`: due time, token, sent marker.

Reports are stored under `CONSULT_DATA_DIR/reports/<case_id>/`; the API strips
the server path from responses.

## Failure behaviour

- No inference key: explicit `rules (...)` label, the flow still works.
- Inference error: fall back to the rule engine and record the reason.
- SMTP error during a check-in: the sent marker is cleared and the scheduler
  retries; the audit trail keeps the failure visible.
- Invalid state transition: HTTP 409 with a plain explanation.
- Storage failure: `/healthz` returns 503 instead of a false `ok`.
