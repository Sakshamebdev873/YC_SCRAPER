import pytest

from app.seed import seed_templates
from app.services.templates import (
    DOMAIN_KEYS, TEMPLATE_KEYS, get_template, get_templates,
    list_versions, restore_version, save_template,
)


@pytest.fixture
def seeded(conn):
    seed_templates(conn)
    return conn


def test_get_templates_returns_every_key(seeded):
    templates = get_templates(seeded, "job")
    assert set(templates) == set(TEMPLATE_KEYS)


def test_get_templates_unknown_domain(seeded):
    with pytest.raises(ValueError):
        get_templates(seeded, "nope")


def test_save_updates_content(seeded):
    save_template(seeded, "job", "subject", "New subject for {company_name}")
    assert get_template(seeded, "job", "subject") == "New subject for {company_name}"


def test_save_snapshots_previous_content(seeded):
    original = get_template(seeded, "job", "subject")
    save_template(seeded, "job", "subject", "v2")
    versions = list_versions(seeded, "job", "subject")
    assert len(versions) == 1
    assert versions[0]["content"] == original


def test_versions_are_newest_first(seeded):
    save_template(seeded, "job", "subject", "v2")
    save_template(seeded, "job", "subject", "v3")
    versions = list_versions(seeded, "job", "subject")
    assert [v["content"] for v in versions][0] == "v2"
    assert len(versions) == 2


def test_restore_puts_old_content_back_and_snapshots_current(seeded):
    original = get_template(seeded, "job", "subject")
    save_template(seeded, "job", "subject", "v2")
    version_id = list_versions(seeded, "job", "subject")[0]["id"]
    result = restore_version(seeded, version_id)
    assert result == {"domain": "job", "key": "subject", "content": original}
    assert get_template(seeded, "job", "subject") == original
    assert "v2" in [v["content"] for v in list_versions(seeded, "job", "subject")]


def test_save_rejects_unknown_key(seeded):
    with pytest.raises(ValueError):
        save_template(seeded, "job", "nope", "x")


def test_restore_rejects_unknown_version(seeded):
    with pytest.raises(ValueError):
        restore_version(seeded, 9999)


def test_all_domains_seeded(seeded):
    for domain in DOMAIN_KEYS:
        assert set(get_templates(seeded, domain)) == set(TEMPLATE_KEYS)
