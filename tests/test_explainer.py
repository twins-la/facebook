"""Landing page + agent-instructions route tests."""


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
