from datetime import datetime, timedelta

import pytest

from app.db import now_iso
from app.services.queue import (
    contacted_companies, contacted_emails, dedupe_by_company,
    eligible_followup, eligible_initial, followup_due_counts,
    followup_eligible, resolve_batch, send_history,
)


def add_contact(conn, email, company, title="Founder", name="Ada L",
                batch="Winter 2026", domain="job", status="active"):
    conn.execute(
        """INSERT INTO contacts (company_name, batch, founder_name, founder_title,
                                 predicted_email, domain, status, created_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
        (company, batch, name, title, email, domain, status, now_iso()),
    )
    conn.commit()
    return conn.execute(
        "SELECT id FROM contacts WHERE predicted_email = ?", (email,)
    ).fetchone()["id"]


def add_send(conn, email, round_num=0, days_ago=0, test_mode=0, error=None):
    stamp = (datetime.now() - timedelta(days=days_ago)).isoformat(timespec="seconds")
    contact = conn.execute(
        "SELECT id FROM contacts WHERE predicted_email = ?", (email,)
    ).fetchone()
    conn.execute(
        """INSERT INTO sends (contact_id, draft_id, round, to_addr, real_addr,
                              sent_at, test_mode, error)
           VALUES (?, NULL, ?, ?, ?, ?, ?, ?)""",
        (contact["id"] if contact else None, round_num, email, email,
         stamp, test_mode, error),
    )
    conn.commit()


def test_dedupe_prefers_ceo():
    rows = [
        {"company_name": "Acme", "founder_title": "Founder", "predicted_email": "a@x"},
        {"company_name": "Acme", "founder_title": "Co-founder & CEO", "predicted_email": "b@x"},
    ]
    assert [r["predicted_email"] for r in dedupe_by_company(rows)] == ["b@x"]


def test_dedupe_keeps_first_when_no_ceo():
    rows = [
        {"company_name": "Acme", "founder_title": "CTO", "predicted_email": "a@x"},
        {"company_name": "Acme", "founder_title": "Founder", "predicted_email": "b@x"},
    ]
    assert [r["predicted_email"] for r in dedupe_by_company(rows)] == ["a@x"]


def test_resolve_batch():
    assert resolve_batch("W26") == "Winter 2026"
    assert resolve_batch("Winter 2026") == "Winter 2026"
    assert resolve_batch("") == ""


def test_eligible_initial_excludes_contacted_address(conn):
    add_contact(conn, "a@acme.com", "Acme")
    add_contact(conn, "b@bolt.com", "Bolt")
    add_send(conn, "a@acme.com")
    emails = [r["predicted_email"] for r in eligible_initial(conn)]
    assert emails == ["b@bolt.com"]


def test_eligible_initial_excludes_whole_company(conn):
    add_contact(conn, "a@acme.com", "Acme")
    add_contact(conn, "c@acme.com", "Acme")
    add_send(conn, "a@acme.com")
    assert eligible_initial(conn) == []


def test_test_mode_send_does_not_count_as_contact(conn):
    add_contact(conn, "a@acme.com", "Acme")
    add_send(conn, "a@acme.com", test_mode=1)
    assert [r["predicted_email"] for r in eligible_initial(conn)] == ["a@acme.com"]
    assert contacted_emails(conn) == set()
    assert contacted_companies(conn) == set()


def test_failed_send_does_not_count_as_contact(conn):
    add_contact(conn, "a@acme.com", "Acme")
    add_send(conn, "a@acme.com", error="smtp exploded")
    assert [r["predicted_email"] for r in eligible_initial(conn)] == ["a@acme.com"]


def test_eligible_initial_skips_unknown_and_skipped(conn):
    add_contact(conn, "a@acme.com", "Acme", name="Unknown")
    add_contact(conn, "b@bolt.com", "Bolt", status="skipped")
    add_contact(conn, "c@cog.com", "Cog")
    assert [r["predicted_email"] for r in eligible_initial(conn)] == ["c@cog.com"]


def test_eligible_initial_filters_batch_and_limit(conn):
    add_contact(conn, "a@acme.com", "Acme", batch="Winter 2026")
    add_contact(conn, "b@bolt.com", "Bolt", batch="Spring 2026")
    assert [r["predicted_email"] for r in eligible_initial(conn, batch="W26")] == ["a@acme.com"]
    assert len(eligible_initial(conn, limit=1)) == 1


def test_eligible_initial_filters_domain(conn):
    add_contact(conn, "a@acme.com", "Acme", domain="job")
    add_contact(conn, "t@trade.local", "Trade", domain="sales")
    assert [r["predicted_email"] for r in eligible_initial(conn, domain="sales")] == ["t@trade.local"]


def test_send_history(conn):
    add_contact(conn, "a@acme.com", "Acme")
    add_send(conn, "a@acme.com", round_num=0, days_ago=10)
    add_send(conn, "a@acme.com", round_num=1, days_ago=6)
    history = send_history(conn, "a@acme.com")
    assert history["sent_at"] is not None
    assert len(history["followups"]) == 1


@pytest.mark.parametrize("days_ago,round_num,expected", [
    (2, 1, False), (3, 1, True), (4, 1, True),
])
def test_followup_eligible_round_one_window(days_ago, round_num, expected):
    stamp = (datetime.now() - timedelta(days=days_ago)).isoformat(timespec="seconds")
    entry = {"sent_at": stamp, "followups": []}
    assert followup_eligible(entry, round_num) is expected


def test_followup_eligible_round_two_uses_last_followup():
    old = (datetime.now() - timedelta(days=30)).isoformat(timespec="seconds")
    recent = (datetime.now() - timedelta(days=1)).isoformat(timespec="seconds")
    entry = {"sent_at": old, "followups": [recent]}
    assert followup_eligible(entry, 2) is False
    entry = {"sent_at": old, "followups": [old]}
    assert followup_eligible(entry, 2) is True


def test_followup_eligible_requires_prior_round():
    old = (datetime.now() - timedelta(days=30)).isoformat(timespec="seconds")
    assert followup_eligible({"sent_at": old, "followups": []}, 2) is False


def test_eligible_followup(conn):
    add_contact(conn, "a@acme.com", "Acme")
    add_contact(conn, "b@bolt.com", "Bolt")
    add_send(conn, "a@acme.com", days_ago=10)
    add_send(conn, "b@bolt.com", days_ago=1)
    assert [r["predicted_email"] for r in eligible_followup(conn, round_num=1)] == ["a@acme.com"]


def test_eligible_followup_skips_already_sent_round(conn):
    add_contact(conn, "a@acme.com", "Acme")
    add_send(conn, "a@acme.com", round_num=0, days_ago=20)
    add_send(conn, "a@acme.com", round_num=1, days_ago=10)
    assert eligible_followup(conn, round_num=1) == []
    assert [r["predicted_email"] for r in eligible_followup(conn, round_num=2)] == ["a@acme.com"]


def test_followup_due_counts(conn):
    add_contact(conn, "a@acme.com", "Acme")
    add_send(conn, "a@acme.com", days_ago=10)
    assert followup_due_counts(conn) == {1: 1, 2: 0, 3: 0}
