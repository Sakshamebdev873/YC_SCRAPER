"""The concrete background workers: generate drafts, send them, scrape.

Each factory returns worker(state, conn) for runner.start_run. The
`client` / `connect` / `runner_cmd` parameters exist so tests can inject
fakes — nothing here ever reaches the network in a test.
"""

import subprocess
import sys
from pathlib import Path

from app.services.drafts import get_draft, update_draft, upsert_draft
from app.services.mailer import connect_smtp, gmail_credentials, send_email
from app.services.personalize import (
    generate_body, openai_client, render_followup_body, render_subject,
)
from app.services.runner import bump, sleep_interruptible
from app.services.templates import get_templates
from app.db import now_iso

DEFAULT_SEND_DELAY = 30


def _contact(conn, contact_id):
    row = conn.execute("SELECT * FROM contacts WHERE id = ?", (contact_id,)).fetchone()
    return dict(row) if row else None


def make_generate_worker(contact_ids, domain: str, round_num: int, client=None):
    def worker(state, conn):
        openai = client or (openai_client() if round_num == 0 else None)
        templates = get_templates(conn, domain)
        for index, contact_id in enumerate(contact_ids, 1):
            if state.stop_requested:
                break
            contact = _contact(conn, contact_id)
            if contact is None:
                state.emit({"type": "skipped", "contact_id": contact_id,
                            "reason": "contact not found"})
                continue
            subject = render_subject(templates, contact, round_num)
            try:
                if round_num == 0:
                    body = generate_body(openai, templates, contact)
                else:
                    body = render_followup_body(templates, contact, round_num)
                draft_id = upsert_draft(conn, contact_id, domain, round_num, subject, body)
                state.emit({"type": "item", "draft_id": draft_id,
                            "contact_id": contact_id, "status": "pending",
                            "company_name": contact["company_name"]})
            except Exception as exc:  # noqa: BLE001 — recorded on the draft, run continues
                draft_id = upsert_draft(conn, contact_id, domain, round_num, subject, "",
                                        status="failed", error=str(exc))
                state.emit({"type": "item", "draft_id": draft_id,
                            "contact_id": contact_id, "status": "failed",
                            "company_name": contact["company_name"],
                            "error": str(exc)})
            bump(conn, state.run_id, index)
            state.emit({"type": "progress", "completed": index,
                        "total": len(contact_ids)})

    return worker


def _default_connect():
    email, password = gmail_credentials()
    return email, connect_smtp(email, password)


def make_send_worker(draft_ids, test_mode: bool, delay: float, test_addr: str,
                     connect=None):
    def worker(state, conn):
        from_addr, smtp = (connect or _default_connect)()
        try:
            for index, draft_id in enumerate(draft_ids, 1):
                if state.stop_requested:
                    break
                draft = get_draft(conn, draft_id)
                if draft is None or draft["status"] != "approved":
                    state.emit({"type": "skipped", "draft_id": draft_id,
                                "reason": "not approved"})
                    continue

                real_addr = draft["predicted_email"]
                to_addr = test_addr if test_mode else real_addr
                error = None
                try:
                    send_email(smtp, from_addr, to_addr, draft["subject"], draft["body"])
                except Exception as exc:  # noqa: BLE001 — recorded, run continues
                    error = str(exc)

                conn.execute(
                    """INSERT INTO sends (contact_id, draft_id, round, to_addr,
                                          real_addr, sent_at, test_mode, error)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                    (draft["contact_id"], draft_id, draft["round"], to_addr,
                     real_addr, now_iso(), 1 if test_mode else 0, error),
                )
                conn.commit()
                update_draft(conn, draft_id,
                             status="failed" if error else "sent", error=error)

                bump(conn, state.run_id, index)
                state.emit({
                    "type": "item", "draft_id": draft_id, "to_addr": to_addr,
                    "company_name": draft["company_name"],
                    "status": "failed" if error else "sent", "error": error,
                })
                state.emit({"type": "progress", "completed": index,
                            "total": len(draft_ids)})

                if index < len(draft_ids) and delay > 0:
                    sleep_interruptible(state, delay)
        finally:
            try:
                smtp.quit()
            except Exception:  # noqa: BLE001 — nothing useful to do on a dead socket
                pass

    return worker


def make_scrape_worker(batch: str, max_companies: int, runner_cmd=None):
    def worker(state, conn):
        from app.seed import DEFAULT_CSV, import_contacts

        cmd = runner_cmd or [
            sys.executable, str(Path("run_scraper.py").resolve()),
            "--max", str(max_companies),
        ]
        if batch and not runner_cmd:
            cmd += ["--batch", batch]

        state.emit({"type": "progress", "message": "scraping..."})
        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode != 0:
            raise RuntimeError(result.stderr.strip()[-2000:] or "scraper failed")

        imported = import_contacts(conn, DEFAULT_CSV)
        state.emit({"type": "item", "imported": imported})

    return worker
