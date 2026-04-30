"""Landing page + agent-instructions route tests."""

from twins_local.testing import assert_no_html_entity_in_css_content


def test_explainer_has_no_html_entities_inside_css_content(client):
    """Sweep-style class check (Job 022): catches the entity-in-CSS-content
    bug class that shipped in Job 020 / fixed in Job 021 for telegram. Now
    enforced sibling-wide via twins_local.testing.
    """
    assert_no_html_entity_in_css_content(client.get("/").get_data(as_text=True))


def test_root_returns_html(client):
    r = client.get("/")
    assert r.status_code == 200
    assert r.content_type.startswith("text/html")
    body = r.get_data(as_text=True)
    # Facebook identity
    assert "facebook.twins.la" in body
    assert "#1877F2" in body  # Facebook Blue accent
    assert '<span class="facebook">facebook</span>' in body
    # Scenario-accurate content
    assert "OAuth" in body
    assert "v19.0" in body and "v21.0" in body
    assert "debug_token" in body
    # Link to agent instructions
    assert "/_twin/agent-instructions" in body


def test_root_has_no_twilio_leftovers(client):
    """Copy-paste hygiene: nothing Twilio-specific should survive in the
    Facebook landing page."""
    body = client.get("/").get_data(as_text=True).lower()
    for forbidden in (
        "twilio",
        "sendgrid",
        "messages.json",
        "accountsid",
        "auth_token",
        "twilio-signature",
        "#e11d48",
    ):
        assert forbidden not in body, f"Found Twilio leftover '{forbidden}' in landing page"


def test_agent_instructions_returns_plain_text(client):
    r = client.get("/_twin/agent-instructions")
    assert r.status_code == 200
    assert r.content_type.startswith("text/plain")
    body = r.get_data(as_text=True)
    assert "facebook.twins.la" in body
    assert "OAuth" in body
    assert "v19.0" in body and "v21.0" in body
    # Tenant auth model
    assert "app_id" in body and "app_secret" in body
    # Admin auth header
    assert "X-Twin-Admin-Token" in body


def test_agent_instructions_no_twilio_leftovers(client):
    body = client.get("/_twin/agent-instructions").get_data(as_text=True).lower()
    for forbidden in ("twilio", "sendgrid", "messages.json", "accountsid"):
        assert forbidden not in body
