# Demo video script — Consult Homeopathic Physicians

Target: **4:30–4:45**, screen capture + voiceover (no slides-only cut).
Build: **v2.4.0** · live: https://consult-homeopathic.207.148.72.102.sslip.io/
Deck: `docs/pitch.pdf` · Submission copy: `docs/SUBMISSION.md`

Amna only has to press record. Everything else in this file is prep.

---

## 1. What Amna needs before recording

- The live URL above and the `/doctor` dashboard password (sent separately;
  never show it on screen).
- A browser window at 1920x1080 (or 16:9), 100% zoom, bookmarks bar hidden.
- Two tabs open: the patient app and `/doctor`, already signed in to the
  dashboard so the video does not spend time on login.
- `docs/sample-lab.txt` downloaded to the Desktop (ready to upload).
- Clipboard: the symptom sentence and a fresh synthetic email for this take.
- Do Not Disturb on. Close personal tabs, mail, Slack, and notifications.
- One rehearsal, timed. Keep a slot for one re-record.

Synthetic data for this take:

```
Name:  Maya Chen
Email: maya.demo1@example.com   (increment the number on each take)
Text:  I have had a cough and a fever for five days. I am allergic to penicillin.
       My email is maya.demo1@example.com.
File:  sample-lab.txt
```

Do **not** touch the one external pending case already in the live DB. In the
dashboard, search for `Maya` so the video never opens it.

Pre-roll live check:

```
https://consult-homeopathic.207.148.72.102.sslip.io/healthz
```

It must say `"version":"2.4.0"` and `"payments":{"demo":true, ...}`.

---

## 2. Shot list (what to click, in order)

| Time | Screen | Action |
|---|---|---|
| 0:00 | Homepage | No click. Slow scroll to "What happens to your case". |
| 0:12 | Homepage | Keep scrolling to the intake card. |
| 0:30 | Intake | Type name + email, paste symptom sentence, Send. |
| 0:45 | Intake | Answer follow-ups briefly (fever ~38.5 C, worse at night). |
| 1:05 | Intake | Click **Document**, upload `sample-lab.txt`. |
| 1:12 | Intake | Answer "Yes, this week's blood test." |
| 1:20 | Intake | Click **Online doctor review** when the options appear. |
| 1:25 | New tab | Homepage → chip **Try: chest pain (safety demo)**. |
| 1:45 | Dashboard | **Cases** → search `Maya` → open the newest case (top of the list). |
| 2:05 | Dashboard | Show summary, allergy warning, labs, conversation, audit. |
| 2:15 | Dashboard | Click **Approve and email plan**. |
| 2:25 | Dashboard | **Outbox** → open the plan email (show the demo-fee line) → **Open case**. |
| 2:35 | Payment | Case drawer → **Open demo payment page** → choose a method → **Pay $29.00 (demo)** → show receipt. |
| 2:50 | Dashboard | Case drawer: payment status + audit entry. |
| 2:55 | Dashboard | Optional: **Send check-in email now** → **Follow-ups** → **Copy link** → open → report chest pain. |
| 3:10 | Dashboard/static | Business case voiceover (no clicks needed). |
| 4:10 | Homepage or dashboard | Team + roadmap + thank you. |

If the follow-up beat (2:55) runs long, cut it and keep the rest. The payment
beat is required; the follow-up beat is a bonus.

---

## 3. Narration (read at a natural pace)

### 0:00–0:12 — Hook

> Clinics lose hours to intake paperwork, and patients wait. Consult
> Homeopathic Physicians turns a short conversation into a structured case -
> and a licensed doctor makes the final decision.

Action: homepage visible, slow scroll.

### 0:12–0:30 — Problem and who

> Meet Maya. She has had a cough and a fever for five days. Today she would
> call a clinic, wait on hold, repeat her history, and hope the note is
> complete. The buyer is a small clinic with one to fifteen clinicians - teams
> that need doctor oversight but cannot staff a full intake desk.

### 0:30–1:25 — Live intake (the core proof)

Action: type/paste the synthetic data, Send. Let the agent ask its questions.

> I'll start a real intake. Name, email, and the symptom in plain language.
> The agent asks short follow-ups - duration, severity, allergies - and builds
> a structured case as we talk. I'll attach a lab report. The parser reads the
> numeric values and flags anything outside the printed reference range. Now
> it proposes care paths with plain-language reasons. I'll choose online
> doctor review.

Notes:
- Answer follow-ups in one short sentence. Do not restart the intake mid-take.
- If the model asks something unexpected, answer briefly and keep moving.
- The lab file is synthetic and contains three abnormal values.

### 1:25–1:45 — Deterministic emergency gate

Action: new tab, homepage, click the chest-pain sample chip.

> Now the safety case. Chest pain and shortness of breath. The red-flag gate
> is a deterministic check that runs before the model - it stops the intake
> and tells the patient to seek emergency care. The model cannot override it.

### 1:45–2:25 — Doctor dashboard and approval

Action: dashboard → Cases → search `Maya` → open the newest case (top of
list) → show tabs.

> This is the clinic dashboard. The case is waiting for a doctor; nothing is
> auto-approved. Here is the structured summary, the penicillin allergy
> warning, the lab values from the document, the full conversation, and the
> audit trail. The doctor edits the plan and approves it. Nothing is emailed
> before this click, and the approval is single-use.

Action: click **Approve and email plan**.

### 2:25–2:55 — Plan email and demo payment

Action: Outbox → open the newest plan email → show the demo-fee line →
click **Open case** in the email header.

> The approved plan is in the outbox. The email includes a clearly labelled
> demo consultation-fee link. This is demo-only: no card details are
> collected, no payment provider is called, and no real charge is made.
> I'll open the payment page from the case and record the demo payment.

Action: case drawer → **Open demo payment page** → choose a method →
**Pay $29.00 (demo)** → receipt. Close the payment tab, reopen the case, and
show `Paid (demo)` plus the audit row.

### 2:55–3:10 — Follow-up escalation (optional, cut if long)

Action: case drawer → **Send check-in email now** → **Follow-ups** →
**Copy link** for Maya → open it in a new tab → report chest pain → **Send update**.

> One more loop: the follow-up check-in. I'll report a red flag. The case
> escalates automatically and the clinic sees the alert.

### 3:10–4:10 — Business case

> The buyer is an independent clinic or telehealth team with one to fifteen
> clinicians. The US has roughly 220,000 to 260,000 physician practices, and
> about 73 percent of physician offices have fewer than 50 employees. At $99
> per clinic per month, the US-only software ceiling is roughly 190 to 225
> million dollars of annual recurring revenue before expansion. The model is
> clinic SaaS at $99 to $299 per month, plus a usage tier for high-volume
> telehealth. AI is required because intake must understand free-form
> language, choose the next question, extract a structured history, and read
> an unstructured document. A fixed form cannot do that. The model drafts, the
> deterministic gate blocks emergencies, and the doctor decides. The result is
> less intake work, fewer missed red flags, and a complete audit trail.

### 4:10–4:40 — Team, roadmap, close

> Built by Canh Pham: backend, inference integration, workflow, and
> deployment. [If Amna is on the team, add her role here.] Next: per-user
> authentication, MFA and encryption for a real clinic pilot; live email and
> EHR integration; and broader clinical content and languages. The app, code,
> and deck are in the submission. Thank you.

---

## 4. Recording checklist

Before:
- [ ] `/healthz` shows `2.4.0`, `payments.demo = true`, `mode = live`.
- [ ] Dashboard session already signed in; password not visible on screen.
- [ ] Tabs: intake, dashboard, one blank tab for the emergency demo.
- [ ] `sample-lab.txt` on the Desktop; clipboard has the symptom sentence.
- [ ] 1080p capture, 16:9, 30 fps, system audio off, mic tested.
- [ ] Phone and notifications off; browser profile clean.
- [ ] One timed rehearsal with the same clicks.

During:
- [ ] Speak slower than feels natural; pause one second between sections.
- [ ] Keep the cursor still while talking; do not scroll ahead of the narration.
- [ ] If a step fails, stop, note the timestamp, and redo from that section.
- [ ] Never fake an output; if the live step fails, re-record it.

After:
- [ ] Trim dead air, keep it under 5:00, add captions.
- [ ] Export 1080p MP4; check audio levels on headphones.
- [ ] Upload to YouTube as **Unlisted** or **Public** (never Private), mark
      **Not for Kids**.
- [ ] Paste the link into `docs/SUBMISSION.md`, `README.md`, and the lablab
      submission form; test the link logged out.
- [ ] Keep the external pending case untouched in the live DB.

---

## 5. YouTube metadata

Title:

```
Consult Homeopathic Physicians — AI intake with a doctor in the loop (Vultr Agent Rush)
```

Description:

```
An AI intake agent collects symptoms by text, voice, or document, screens for
emergencies with a deterministic red-flag gate, and prepares a structured case.
A licensed doctor reviews, edits, and approves the plan on a dashboard; only
then is it emailed. The build includes prior-visit history, follow-up
escalation, an audit trail, and a demo-only consultation-fee receipt (no card
details, no provider call, no real charge).

Live demo: https://consult-homeopathic.207.148.72.102.sslip.io/
Doctor dashboard: https://consult-homeopathic.207.148.72.102.sslip.io/doctor
Challenge 2 — Powering the Future of Work, Vultr: Agent Rush Hackathon
Stack: Python, FastAPI, SQLite, Vultr Cloud Compute, Vultr Serverless
Inference, Gemini audio API.

Synthetic data only. This is a hackathon prototype, not a medical device.
```

Tags:

```
vultr, agent rush, lablab, ai healthcare, patient intake, human in the loop,
fastapi, gemini, voice ai, hackathon
```

Plain-text description for the submission form (if it does not accept
markdown): use the same paragraphs without the links block duplication.

---

## 6. Handoff message to Amna

```
Hi Amna - v2.4.0 is live and everything is ready for the video.

Live: https://consult-homeopathic.207.148.72.102.sslip.io/
Dashboard: https://consult-homeopathic.207.148.72.102.sslip.io/doctor
Script + shot list: docs/VIDEO_SCRIPT.md
Lab file: docs/sample-lab.txt (put it on the Desktop)

Use a fresh synthetic email (maya.demo1@example.com), sign in to the
dashboard before recording, and do not open or approve the one external
pending case - search for "Maya" instead. The payment step is demo-only:
no card details, no real charge.

After the take, upload to YouTube as Unlisted, mark Not for Kids, and send me
the link plus the timestamp of the payment step.
```
