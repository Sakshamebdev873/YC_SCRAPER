import pytest

from app.db import now_iso
from app.services.drafts import get_draft, list_drafts, update_draft, upsert_draft


@pytest.fixture
def contact_id(conn):
    conn.execute(
        """INSERT INTO contacts (company_name, batch, founder_name, predicted_email, created_at)
           VALUES ('Acme', 'Winter 2026', 'Ada L', 'ada@acme.com', ?)""",
        (now_iso(),),
    )
    conn.commit()
    return conn.execute("SELECT id FROM contacts").fetchone()["id"]


def test_upsert_creates_a_draft(conn, contact_id):
    draft_id = upsert_draft(conn, contact_id, "job", 0, "Subj", "Body")
    draft = get_draft(conn, draft_id)
    assert draft["subject"] == "Subj"
    assert draft["status"] == "pending"
    assert draft["company_name"] == "Acme"
    assert draft["predicted_email"] == "ada@acme.com"


def test_upsert_replaces_the_live_draft(conn, contact_id):
    upsert_draft(conn, contact_id, "job", 0, "Old", "Old body")
    upsert_draft(conn, contact_id, "job", 0, "New", "New body")
    drafts = list_drafts(conn)
    assert len(drafts) == 1
    assert drafts[0]["subject"] == "New"


def test_upsert_keeps_sent_drafts_as_history(conn, contact_id):
    first = upsert_draft(conn, contact_id, "job", 0, "Old", "Old body")
    update_draft(conn, first, status="sent")
    upsert_draft(conn, contact_id, "job", 0, "New", "New body")
    assert len(list_drafts(conn)) == 2
    assert len(list_drafts(conn, status="sent")) == 1


def test_rounds_are_independent(conn, contact_id):
    upsert_draft(conn, contact_id, "job", 0, "Initial", "b")
    upsert_draft(conn, contact_id, "job", 1, "Followup", "b")
    assert len(list_drafts(conn)) == 2
    assert len(list_drafts(conn, round_num=1)) == 1


def test_update_sets_edited_at_on_content_change(conn, contact_id):
    draft_id = upsert_draft(conn, contact_id, "job", 0, "Subj", "Body")
    assert get_draft(conn, draft_id)["edited_at"] is None
    update_draft(conn, draft_id, body="Edited body")
    draft = get_draft(conn, draft_id)
    assert draft["body"] == "Edited body"
    assert draft["edited_at"] is not None


def test_update_status_alone_does_not_set_edited_at(conn, contact_id):
    draft_id = upsert_draft(conn, contact_id, "job", 0, "Subj", "Body")
    update_draft(conn, draft_id, status="approved")
    draft = get_draft(conn, draft_id)
    assert draft["status"] == "approved"
    assert draft["edited_at"] is None


def test_update_rejects_bad_status(conn, contact_id):
    draft_id = upsert_draft(conn, contact_id, "job", 0, "S", "B")
    with pytest.raises(ValueError):
        update_draft(conn, draft_id, status="whatever")


def test_update_rejects_unknown_id(conn):
    with pytest.raises(ValueError):
        update_draft(conn, 999, status="approved")


def test_failed_draft_records_the_error(conn, contact_id):
    draft_id = upsert_draft(conn, contact_id, "job", 0, "S", "", status="failed",
                            error="rate limited")
    assert get_draft(conn, draft_id)["error"] == "rate limited"


def test_list_filters_by_domain(conn, contact_id):
    upsert_draft(conn, contact_id, "job", 0, "S", "B")
    assert len(list_drafts(conn, domain="job")) == 1
    assert len(list_drafts(conn, domain="sales")) == 0
