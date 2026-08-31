import pytest

from app.seed import domain_template_content, seed_templates

KEYS = {
    "bio", "system_prompt", "user_prompt", "subject",
    "followup_subject", "followup_1", "followup_2", "followup_3",
}


@pytest.mark.parametrize("domain", ["job", "sales", "sales_professionals"])
def test_every_domain_supplies_every_key(domain):
    content = domain_template_content(domain)
    assert set(content) == KEYS
    for key, value in content.items():
        assert isinstance(value, str) and value.strip(), f"{domain}.{key} is empty"


def test_job_system_prompt_has_bio_inlined():
    content = domain_template_content("job")
    assert "SatsEarn.app" in content["system_prompt"]
    assert "Saksham" in content["system_prompt"]


def test_sales_domains_differ():
    a = domain_template_content("sales")
    b = domain_template_content("sales_professionals")
    assert a["system_prompt"] != b["system_prompt"]
    assert a["subject"] != b["subject"]


def test_unknown_domain_raises():
    with pytest.raises(ValueError):
        domain_template_content("nope")


def test_seed_templates_inserts_all(conn):
    inserted = seed_templates(conn)
    assert inserted == 24  # 3 domains x 8 keys
    rows = conn.execute("SELECT domain, key FROM templates").fetchall()
    assert len(rows) == 24


def test_seed_templates_does_not_overwrite_edits(conn):
    seed_templates(conn)
    conn.execute(
        "UPDATE templates SET content='EDITED' WHERE domain='job' AND key='subject'"
    )
    conn.commit()
    assert seed_templates(conn) == 0
    row = conn.execute(
        "SELECT content FROM templates WHERE domain='job' AND key='subject'"
    ).fetchone()
    assert row["content"] == "EDITED"
