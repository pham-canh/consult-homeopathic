# Two-minute demo video — shot list and narration

Record 1920×1080. One browser window, two tabs: patient app and doctor
dashboard. Use the synthetic cases already in the database or create fresh ones.

## 0:00–0:18 — Problem over the landing page

**On screen:** https://consult.139.180.147.61.sslip.io/ and the five-step card.

**Narration:** "A routine appointment takes hours out of a patient's day, and a
doctor spends the first minutes collecting the same basic history. Consult
Homeopathic Physicians automates the information work and keeps the medical
judgment with the doctor."

## 0:18–0:55 — Patient intake

**On screen:** click "Try: cough + fever for 5 days". The agent replies and asks
one or two follow-ups. Show the care options appearing.

**Narration:** "The patient describes a cough and fever for five days and a
penicillin allergy. The agent extracts the structured case, flags the allergy,
and offers three care paths. The patient chooses an online doctor review."

**Action:** click "Online doctor review". Show the status change to
`pending doctor`.

## 0:55–1:15 — Safety moment

**On screen:** start a second case with "Try: chest pain (safety demo)".

**Narration:** "This is the important part. A second patient reports chest pain
and breathlessness. The deterministic safety gate runs before the model, stops
the automated flow, and tells the patient to seek emergency care immediately.
No options are offered."

**Action:** let the red emergency banner sit on screen for two seconds.

## 1:15–1:45 — Doctor dashboard

**On screen:** open `/doctor`, click the pending case.

**Narration:** "The doctor sees the AI-prepared summary, the full conversation,
the allergy warning, and the audit trail. The AI has not diagnosed or prescribed.
The doctor writes the advice and approves the plan."

**Action:** type a short advice line, click "Approve & email plan". Show the
status become `delivered`.

## 1:45–2:00 — Delivery and close

**On screen:** scroll to the outbox and open the email preview.

**Narration:** "Only after approval is the plan emailed to the patient, with a
follow-up check that escalates on a red flag. One case prepared in minutes
instead of a full appointment slot. Built on a Vultr VM and Vultr Serverless
Inference."

**On screen:** end card with repo URL, live URL, and "prototype, not medical
care".

## Recording checklist

- [ ] Browser zoom 100%, no personal tabs visible.
- [ ] Synthetic data only; no real names or records.
- [ ] Show the engine badge `vultr / deepseek-v4.1-flash-1017` at least once.
- [ ] Keep the emergency banner readable for at least two seconds.
- [ ] End card includes the public repo and the live URL.
- [ ] Under two minutes, captions on, audio normalised.
