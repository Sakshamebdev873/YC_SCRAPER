from app.services.leads import generate_placeholder_leads


def test_generates_requested_count(conn):
    rows = generate_placeholder_leads(conn, "sales", 3)
    assert len(rows) == 3
    assert conn.execute(
        "SELECT COUNT(*) c FROM contacts WHERE domain='sales'"
    ).fetchone()["c"] == 3


def test_emails_are_unique_across_calls(conn):
    a = generate_placeholder_leads(conn, "sales", 2)
    b = generate_placeholder_leads(conn, "sales", 2)
    emails = {r["predicted_email"] for r in a + b}
    assert len(emails) == 4


def test_professionals_domain_gets_its_own_rows(conn):
    generate_placeholder_leads(conn, "sales_professionals", 2)
    rows = conn.execute(
        "SELECT * FROM contacts WHERE domain='sales_professionals'"
    ).fetchall()
    assert len(rows) == 2
    assert all("10+ employees" in r["company_description"] for r in rows)


def test_rows_are_queue_eligible(conn):
    from app.services.queue import eligible_initial
    generate_placeholder_leads(conn, "sales", 2)
    assert len(eligible_initial(conn, domain="sales")) == 2
