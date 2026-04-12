# Facebook Twin

A digital twin of Facebook Login (OAuth 2.0 + Graph API `/me` + `/debug_token`) for [twins.la](https://twins.la).

## What This Is

A Python package that emulates the slice of Facebook used to sign users in:

- OAuth 2.0 authorization dialog (code flow and implicit flow)
- Authorization code → access token exchange
- Graph API `/me` user-profile lookup with field selection
- Token inspection via `/debug_token`

Existing Facebook Login code can be pointed at this twin by changing only the hostname. No real Facebook app registration required; the twin lets you configure test apps and test users via its Twin Plane.

## Supported Scenarios

See [SCENARIOS.md](SCENARIOS.md) for the full scope and authoritative references.

- **Facebook Login** — OAuth authorization, token exchange, Graph `/me`, `/debug_token`, on Graph API versions **v19.0** and **v21.0**.

## Usage

This package is not run directly. It is loaded by a host:

- **Local**: run via Docker Compose from `/src/twins/local/`
- **Cloud**: available at `facebook.twins.la`

## Quick Start (local)

```bash
cd /src/twins/local
docker compose up facebook
```

The twin listens on `http://localhost:8081`. Then, using any HTTP client:

```python
import requests

TWIN = "http://localhost:8081"

# 1. Create an app and a test user via Twin Plane.
app = requests.post(f"{TWIN}/_twin/apps", json={
    "name": "My App",
    "redirect_uris": ["https://myapp.test/oauth/callback"],
}).json()

user = requests.post(f"{TWIN}/_twin/users", json={
    "name": "Alice Example",
    "email": "alice@example.com",
    "granted_scopes": ["email", "public_profile"],
}).json()

# 2. Walk the OAuth code flow — normally the user is redirected here by their browser.
r = requests.get(f"{TWIN}/v19.0/dialog/oauth", params={
    "client_id": app["app_id"],
    "redirect_uri": app["redirect_uris"][0],
    "response_type": "code",
    "state": "xyz",
}, allow_redirects=False)
code = requests.utils.urlparse(r.headers["Location"]).query
# parse `code` from the redirect

# 3. Exchange code for an access token.
token = requests.get(f"{TWIN}/v19.0/oauth/access_token", params={
    "client_id": app["app_id"],
    "client_secret": app["app_secret"],
    "redirect_uri": app["redirect_uris"][0],
    "code": <the code from step 2>,
}).json()["access_token"]

# 4. Fetch the user profile.
profile = requests.get(f"{TWIN}/v19.0/me", params={"fields": "id,name,email"},
                       headers={"Authorization": f"Bearer {token}"}).json()
# → {"id": "...", "name": "Alice Example", "email": "alice@example.com"}

# 5. Verify the token's app attribution.
app_token = f"{app['app_id']}|{app['app_secret']}"
debug = requests.get(f"{TWIN}/v19.0/debug_token", params={
    "input_token": token, "access_token": app_token,
}).json()
# → {"data": {"app_id": "...", "user_id": "...", "is_valid": true, ...}}
```

## Twin Plane

The Twin Plane is served at `/_twin/`. Unauthenticated endpoints:

- `GET /_twin/health`
- `GET /_twin/scenarios`
- `GET /_twin/references`
- `GET /_twin/settings`

Admin-scoped endpoints (require `X-Twin-Admin-Token` header, or `Authorization: Bearer <admin_token>`):

- `POST|GET|DELETE /_twin/apps[/<app_id>]`
- `POST|GET|PATCH|DELETE /_twin/users[/<fb_id>]`
- `PUT /_twin/settings` — toggle `interactive_dialog`

Tenant or admin (Basic Auth with `app_id:app_secret`, or admin token):

- `POST /_twin/tokens` — mint a user access token directly (for fixtures)
- `GET /_twin/logs` — operation logs; tenants see only their own app's logs

When no admin token is configured in the host, any bearer token is accepted (local-dev convenience). Production hosts should always set `TWIN_ADMIN_TOKEN`.

## Version

0.1.0
