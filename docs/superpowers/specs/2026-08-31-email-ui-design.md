# Cold Email Applier — Web UI Design

Date: 2026-08-31

## Problem

The pipeline works but is entirely CLI-driven. Three things are painful:

1. **Templates are code.** Tuning the system prompt, bio, subject line, or the
   three follow-up bodies means editing Python constants in `domains/*.py`, then
   running `--dry-run` against the real CSV to see what comes out. There is no
   way to iterate on a prompt against a single sample founder, and no history —
   a prompt that worked better an hour ago is gone.
2. **No per-email review.** `--dry-run` prints every generated email to the
   console; the only options are send all or send none. There is no way to fix
   one bad draft and keep the rest.
3. **State is opaque.** 2170 contacts in a CSV and a flat `sent_log.json`. Who
   is due for follow-up #2 is not answerable without reading JSON by hand, and a
   wrong predicted email cannot be corrected without editing the CSV.

## Goals

A local, single-user web dashboard that covers the whole loop: manage contacts,
finalise templates with live preview, review and edit every generated draft,
send with live progress, and see who is due for a follow-up.

**Non-goals.** Multi-user, auth, or hosting. Auto-sending on a schedule —
nothing goes out without an explicit human approve-then-send. Replacing the CLI.

## Key decisions

| Decision | Choice | Why |
|---|---|---|
| Data store | SQLite (`output/app.db`) | Drafts, approvals, per-send history, and template versions are relational and mutable; flat JSON gets race-y and slow at 2170 rows. |
| CLI | Kept, refactored onto the same DB | Scriptability retained. The extraction into shared services is what stops the CLI and UI from drifting into two implementations. |
| Stack | FastAPI + React/Vite/Tailwind | Owner is a MERN dev and will extend the frontend. Costs a `npm run build` step; in return the queue and per-draft editing stay comfortable to work on. |
| Follow-ups | Surfaced, never automatic | A background sender means a bad template silently blasts everyone. A "due" list with a button has the same value and none of that risk. |
| `domains/*.py` | Demoted to seed data | Templates become editable rows. The Python modules remain the first-run source and the record of the original content. |

## Architecture

```
app/                      # new — FastAPI backend
  main.py                 # app factory, CORS for dev, serves frontend/dist in prod
  db.py                   # schema, connection, migrations
  seed.py                 # first-run import (idempotent)
  api/
    contacts.py  templates.py  drafts.py  runs.py  followups.py  stats.py
  services/
    personalize.py        # OpenAI draft generation   (from send_emails.py)
    mailer.py             # SMTP connect + send       (from send_emails.py)
    queue.py              # eligibility, dedupe-by-company, follow-up windows
    runner.py             # background run executor + progress events
frontend/                 # new — Vite + React + Tailwind
send_emails.py            # kept; refactored to call app/services/* against the DB
domains/*.py              # kept; demoted to seed data for the templates table
```

### Service extraction

These move out of `send_emails.py` into `app/services/` unchanged in behaviour:

- `personalize_email` → `services/personalize.py`
- `send_email`, `connect_smtp` → `services/mailer.py`
- `dedupe_by_company`, `followup_eligible`, `FOLLOWUP_MIN_DAYS` → `services/queue.py`

`send_emails.py` keeps every current flag and its console output. Its
`load_sent_log`/`save_sent_log` are replaced by reads and writes against the
`sends` table. `--csv PATH` becomes "import this CSV, then run".

## Data model

`output/app.db`, gitignored.

### contacts
`id`, `company_name`, `batch`, `company_website`, `founder_name`,
`founder_title`, `founder_linkedin`, `founder_twitter`, `predicted_email`,
`email_pattern`, `yc_url`, `company_description`, `domain` (default `job`),
`status` (`active` | `skipped`), `created_at`.

`UNIQUE(predicted_email)`. Import upserts on that key, so re-importing the CSV
or scraping an overlapping batch never duplicates a row. Indexes on `batch`,
`company_name`, `status`.

### templates
`domain`, `key`, `content`, `updated_at`. Primary key `(domain, key)`.

Keys: `bio`, `system_prompt`, `user_prompt`, `subject`, `followup_subject`,
`followup_1`, `followup_2`, `followup_3`.

`system_prompt` is stored already-formatted with the bio inlined at seed time,
matching what `SYSTEM_PROMPT_TEMPLATE.format(bio=CANDIDATE_BIO)` produces
today. `bio` is stored separately as an editable field; saving `bio` does not
retroactively rewrite `system_prompt` — the two are independent rows, and the
UI says so on the Templates screen. (Rationale: silently regenerating a prompt
the user has hand-tuned is worse than making them paste.)

The sales domain's per-ICP variants are stored as separate domains, `sales` and
`sales_professionals`, rather than as a nested ICP dimension — the ICP already
swaps the entire prompt set, so a flat domain key is sufficient.

### template_versions
`id`, `domain`, `key`, `content`, `created_at`. On every save the **previous**
content is snapshotted here before the new content is written. The Templates
screen offers a version list and a restore action.

### drafts
`id`, `contact_id`, `domain`, `round` (0 = initial, 1-3 = follow-up), `subject`,
`body`, `status` (`pending` | `approved` | `rejected` | `sent` | `failed`),
`generated_at`, `edited_at`, `error`.

`UNIQUE(contact_id, round)` among non-rejected drafts — regenerating replaces
the existing draft rather than accumulating.

### sends
`id`, `contact_id`, `draft_id`, `round`, `to_addr` (where it actually went),
`real_addr` (the contact's true address), `sent_at`, `test_mode`, `error`.

Replaces `sent_log.json`. "Already contacted" means a `sends` row with
`test_mode = 0` and `error IS NULL` — test sends never mark someone as
contacted, preserving today's behaviour where `--test-email` skips log writes.

### runs
`id`, `kind` (`generate` | `send` | `scrape`), `domain`, `status`
(`running` | `done` | `stopped` | `error`), `total`, `completed`, `started_at`,
`finished_at`, `error`.

### settings
`key`, `value`. Holds send delay (default 30) and test-mode default (on).
Gmail and OpenAI credentials stay in `.env` and are never written to the DB or
returned by the API.

## Seeding and migration

`app/seed.py`, run on startup, idempotent — safe to run on every boot:

1. Create tables if absent.
2. If `templates` is empty for a domain, import that domain module's constants.
3. Upsert `output/yc_founders_emails.csv` into `contacts` on `predicted_email`.
4. For each key in `output/sent_log.json` with no existing `sends` row: insert
   one with `round = 0`, `sent_at` from the log, `test_mode = 0`, and a
   `contact_id` resolved by email (null if the contact is not in the CSV — the
   row still counts as "contacted" for dedupe by address). Each `followups`
   entry becomes a `sends` row with the matching round.
5. `sent_log.json` is read-only throughout and left on disk as a backup.

Running seed twice must not duplicate contacts or sends. This is tested.

## API

All routes under `/api`, server bound to `127.0.0.1`.

```
GET    /api/stats                       counts: contacts, contacted, pending drafts, due follow-ups
GET    /api/contacts                    ?search= &batch= &status= &page= &per_page=
PATCH  /api/contacts/{id}               fix predicted_email, toggle status
POST   /api/contacts/import             re-import a CSV path
POST   /api/runs/scrape                 {batch, max} → background run

GET    /api/templates/{domain}          all keys for a domain
PUT    /api/templates/{domain}/{key}    save (snapshots previous into template_versions)
GET    /api/templates/{domain}/{key}/versions
POST   /api/templates/{domain}/{key}/restore/{version_id}
POST   /api/templates/preview           {domain, key, content, contact_id} → generated email
                                        using UNSAVED content

GET    /api/queue                       ?domain= &batch= &round= &limit= → eligible contacts
POST   /api/runs/generate               {contact_ids, domain, round} → background run
GET    /api/drafts                      ?status= &round= &domain=
PATCH  /api/drafts/{id}                 edit subject/body, or set status approved/rejected
POST   /api/drafts/{id}/regenerate

POST   /api/runs/send                   {draft_ids, test_mode, delay} → background run
GET    /api/runs/{id}                   status snapshot
GET    /api/runs/{id}/events            SSE progress stream
POST   /api/runs/{id}/stop              cooperative stop

GET    /api/followups/due               grouped by round 1/2/3
```

`/api/templates/preview` is the core of the template-finalising loop: it renders
against unsaved editor content so the user sees the real output before
committing.

## Screens

1. **Dashboard** — contacts / contacted / pending drafts / due follow-ups, plus
   recent runs.
2. **Contacts** — searchable, filterable, paginated table over all 2170. Inline
   edit of `predicted_email`, skip toggle, and a *Scrape new batch* action.
3. **Templates** — domain + key rail, monospace editor, sample-founder picker,
   *Preview* (calls OpenAI with unsaved content), Save, version history with
   restore.
4. **Compose** — domain / batch / round / limit → eligible queue → *Generate
   drafts* → cards streaming in, each with editable subject and body and
   Approve / Reject / Regenerate. Bulk approve.
5. **Send** — approved drafts only. Test-mode toggle on by default, delay
   field, *Start send*, live SSE log, Stop.
6. **Follow-ups** — three tabs by round, each listing contacts past the 3 / 4 /
   5-day threshold, feeding into the same generate → approve → send path.

## Queue rules

Unchanged from `send_emails.py`, moved into `services/queue.py`:

- **Initial (round 0):** has a `predicted_email`; `founder_name` not `Unknown`
  or empty; `status = active`; no real send to that address; no real send to
  anyone at the same `company_name`; then dedupe to one contact per company,
  preferring a title containing "ceo".
- **Follow-up round N:** a real round-0 send exists; fewer than N follow-up
  sends recorded; at least `FOLLOWUP_MIN_DAYS[N]` days (3 / 4 / 5) since the
  previous contact.

## Safety

- Bound to `127.0.0.1`. No auth, because it is never reachable off-box.
- Nothing sends that is not an approved draft. There is no "send without
  review" path in the UI.
- Test mode defaults on. Live mode shows a red banner naming the real recipient
  count before the run starts.
- The inter-send delay is enforced server-side in the runner.
- Each send writes its `sends` row immediately, before the delay — a crash
  mid-run loses at most the in-flight email.
- Credentials are read from `.env` and never returned by any endpoint.

## Error handling

- **OpenAI failure during generate:** the draft is written with `status =
  failed` and the error text; the run continues. The card offers Regenerate.
- **SMTP send failure:** a `sends` row is written with the error, the draft goes
  to `failed`, the run continues to the next email.
- **SMTP connect failure:** the run ends immediately with `status = error` and
  the existing App Password guidance surfaced in the UI.
- **Stop:** cooperative — the runner checks a flag between emails, so an
  in-flight send always completes rather than being torn mid-SMTP.

## Testing

`pytest` against a temp SQLite, with OpenAI and SMTP faked — no test opens a
socket to Gmail or OpenAI.

- `services/queue.py`: initial eligibility, company-level exclusion,
  CEO-preferring dedupe, follow-up windows at the boundary days, test sends not
  counting as contact.
- `app/seed.py`: idempotency (twice → no duplicate contacts or sends),
  `sent_log.json` migration including follow-up rounds and unknown addresses.
- `services/runner.py`: a failing email does not abort the run; stop takes
  effect between emails; `sends` rows are written before the delay.
- API routes via FastAPI `TestClient`: template save snapshots a version,
  preview uses unsaved content, send rejects unapproved draft ids.
- `send_emails.py` parity: same queue against the same data as before the
  refactor.

The frontend stays thin — data fetching and forms — and gets no test framework.

## Build order

1. DB, schema, seed + migration, with tests. Nothing user-visible.
2. Extract services out of `send_emails.py`; repoint the CLI at the DB; parity
   tests green.
3. FastAPI app with the read endpoints (stats, contacts, templates, queue).
4. Frontend shell: routing, layout, Dashboard, Contacts.
5. Templates screen with live preview and version restore.
6. Generate + drafts: the runner, SSE, Compose screen.
7. Send screen and Follow-ups screen.
8. Prod serving: `npm run build`, FastAPI mounts `frontend/dist`, single-command
   launch; README updated.
