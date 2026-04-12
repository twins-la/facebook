"""Explainer page and agent instructions for the Facebook twin.

Serves:
  GET /                         — HTML explainer page for humans and agents
  GET /_twin/agent-instructions — Plain text agent instructions
"""

from flask import Blueprint, Response

explainer_bp = Blueprint("explainer", __name__)

AGENT_INSTRUCTIONS = """\
# Facebook Login Twin — facebook.twins.la

A high-fidelity digital twin of Facebook Login: OAuth 2.0 authorization,
token exchange, Graph /me user profile, and /debug_token inspection.
Code written against this twin works against real Facebook with only
hostname changes on the dialog and Graph URLs.

Supported Graph API versions: v19.0, v21.0 (served concurrently under
the same host).

## Authentication

OAuth endpoints (no auth, driven by app_id + app_secret in the flow):
  /dialog/oauth, /v*/oauth/access_token, /v*/me, /v*/debug_token

Twin Plane tenant ops — HTTP Basic Auth
  Username: app_id
  Password: app_secret
  (POST /_twin/tokens for direct token minting; GET /_twin/logs scoped
  to your app.)

Twin Plane admin ops — Bearer token
  Header: X-Twin-Admin-Token: <token>   (or Authorization: Bearer <token>)
  Service-wide operations (create/delete apps, create/update/delete
  users, read any logs, update twin settings) require the admin token
  set by the deployment owner.

Apps are admin-provisioned only — there is no self-bootstrap endpoint.
Ask the operator to create an app for you and share the app_id and
app_secret back.

## Key Endpoints

Twin Plane (no auth):
  GET  /_twin/health             — status check
  GET  /_twin/scenarios          — supported scenarios + API versions
  GET  /_twin/settings           — twin settings (interactive_dialog)
  GET  /_twin/references         — authoritative sources used to build this twin

Twin Plane (Basic Auth with app_id:app_secret):
  POST /_twin/tokens             — mint a user access token for one of
                                   your app's users (body: {"fb_id", "scopes"})
  GET  /_twin/logs               — your app's operation logs

Twin Plane (Admin Bearer):
  POST   /_twin/apps                               — create an app
  GET    /_twin/apps                               — list apps
  DELETE /_twin/apps/<app_id>                      — delete an app (cascades)
  POST   /_twin/users                              — create a test user (body: {"app_id", "fb_id", "name", "email", "granted_scopes"})
  GET    /_twin/users[?app_id=<id>]                — list users, optionally scoped
  PATCH  /_twin/apps/<app_id>/users/<fb_id>        — update user
  DELETE /_twin/apps/<app_id>/users/<fb_id>        — delete user
  PUT    /_twin/settings                           — update twin settings
  GET    /_twin/logs                               — all operation logs

OAuth & Graph API (for end users of your app):
  GET /dialog/oauth                  — authorization dialog (code + implicit)
  GET /v19.0/dialog/oauth            — versioned dialog (same semantics)
  GET /v21.0/dialog/oauth            — versioned dialog (same semantics)
  GET /v{19,21}/oauth/access_token   — exchange code for token
                                       (also grant_type=client_credentials
                                       for an app access token)
  GET /v{19,21}/me                   — fetch the authenticated user's profile
                                       (fields query param: id,name,email)
  GET /v{19,21}/debug_token          — inspect an input_token

## Quick Start (OAuth code flow)

1. Operator creates a test app and test user for you via Twin Plane:

     curl -X POST https://facebook.twins.la/_twin/apps \\
       -H "X-Twin-Admin-Token: $ADMIN_TOKEN" \\
       -H "Content-Type: application/json" \\
       -d '{"name": "My App", "redirect_uris": ["https://my-app.test/cb"]}'

     curl -X POST https://facebook.twins.la/_twin/users \\
       -H "X-Twin-Admin-Token: $ADMIN_TOKEN" \\
       -H "Content-Type: application/json" \\
       -d '{"app_id": "<app_id>", "name": "Alice", "email": "alice@test",
            "granted_scopes": ["email", "public_profile"]}'

2. Walk the dialog (this is what a browser would do):

     curl -I "https://facebook.twins.la/v19.0/dialog/oauth?\\
       client_id=<app_id>&redirect_uri=https://my-app.test/cb&\\
       response_type=code&state=xyz&scope=email,public_profile"
     # 302 Location: https://my-app.test/cb?code=<code>&state=xyz

3. Exchange the code for an access token:

     curl "https://facebook.twins.la/v19.0/oauth/access_token?\\
       client_id=<app_id>&client_secret=<app_secret>&\\
       redirect_uri=https://my-app.test/cb&code=<code>"
     # {"access_token":"EAA...","token_type":"bearer","expires_in":...}

4. Fetch the user's identity:

     curl "https://facebook.twins.la/v19.0/me?fields=id,name,email" \\
       -H "Authorization: Bearer <access_token>"
     # {"id":"...","name":"Alice","email":"alice@test"}

5. Verify app attribution (detect token substitution):

     curl "https://facebook.twins.la/v19.0/debug_token?\\
       input_token=<access_token>&access_token=<app_id>|<app_secret>"
     # {"data": {"app_id":"<app_id>","user_id":"...","is_valid":true,...}}

## Local Usage

pip install twins-facebook-local
python -c "
from twins_facebook_local.storage_sqlite import SQLiteFacebookStorage
from twins_facebook.app import create_app
storage = SQLiteFacebookStorage('facebook.db')
app = create_app(storage=storage, config={'admin_token': 'dev'})
app.run(port=8081)
"

Then use http://localhost:8081 instead of https://facebook.twins.la.

## Fidelity Notes

- Access tokens are opaque twin values — do NOT hard-code real Facebook
  token shapes or length expectations. The EAA prefix is a visual
  courtesy, not a fidelity contract.
- Error envelope matches Facebook: {"error": {"message","type","code",
  "fbtrace_id"}}. Well-known codes: 100 (parameter), 101 (app
  credentials), 190 (access token), 191 (redirect_uri), 803 (unknown
  path), 2500 (unknown API version).
- /dialog/oauth is served at the same host as /v*/... — real Facebook
  splits them across www.facebook.com and graph.facebook.com; twins.la
  collapses both to one host. Configure dialog URL and Graph URL
  independently in your client if the SDK expects different hostnames.
- Users are per-app on this twin — the same fb_id under different
  apps are different users. Tenants cannot cross-access each other's
  users.

## Reference

Detailed docs: https://github.com/twins-la/facebook
Project overview: https://twins.la
All twins: https://github.com/twins-la/twins-la
"""

EXPLAINER_HTML = """\
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>facebook.twins.la — Facebook Login Twin</title>
    <link rel="icon" type="image/png" href="https://twins.la/twins.png">
    <style>
        @import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600&family=JetBrains+Mono:wght@400&display=swap');
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body {
            min-height: 100vh;
            background: #f8f8f8;
            font-family: 'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
            color: #374151;
            padding: 4rem 2rem;
            line-height: 1.7;
        }
        main { max-width: 700px; margin: 0 auto; }
        h1 {
            font-size: clamp(2rem, 5vw, 3rem);
            font-weight: 600;
            letter-spacing: -0.03em;
            color: #1a2e4a;
            margin-bottom: 0.5rem;
        }
        h1 .facebook { color: #1877F2; }
        .tagline {
            font-size: 1.1rem;
            color: #6b7280;
            margin-bottom: 2.5rem;
            font-weight: 300;
        }
        h2 {
            font-size: 1.25rem;
            font-weight: 600;
            color: #1a2e4a;
            margin: 2rem 0 0.75rem;
            letter-spacing: -0.01em;
        }
        p { margin-bottom: 1rem; color: #6b7280; }
        p strong { color: #1a2e4a; }
        a { color: #1877F2; text-decoration: none; }
        a:hover { color: #166FE5; text-decoration: underline; }
        ul { list-style: none; padding: 0; margin-bottom: 1rem; }
        ul li { padding: 0.3rem 0; color: #6b7280; }
        ul li::before { content: "\\2192  "; color: #1877F2; }
        code {
            font-family: 'JetBrains Mono', monospace;
            font-size: 0.85em;
            background: #f3f4f6;
            padding: 0.15em 0.4em;
            border-radius: 4px;
            color: #1a2e4a;
            border: 1px solid #e5e7eb;
        }
        .snippet-box {
            background: #ffffff;
            border: 1px solid #e5e7eb;
            border-radius: 10px;
            padding: 1.5rem;
            margin: 1rem 0;
            position: relative;
            box-shadow: 0 1px 3px rgba(0,0,0,0.04);
        }
        .snippet-box pre {
            font-family: 'JetBrains Mono', monospace;
            font-size: 0.8rem;
            color: #6b7280;
            white-space: pre-wrap;
            word-break: break-word;
            line-height: 1.5;
            max-height: 400px;
            overflow-y: auto;
        }
        .copy-btn {
            position: absolute;
            top: 0.75rem;
            right: 0.75rem;
            background: #f3f4f6;
            color: #6b7280;
            border: 1px solid #e5e7eb;
            padding: 0.3rem 0.7rem;
            border-radius: 6px;
            font-size: 0.75rem;
            cursor: pointer;
            font-family: 'Inter', sans-serif;
            transition: background 0.15s, color 0.15s;
        }
        .copy-btn:hover { background: #1877F2; color: #ffffff; }
        .links { margin-top: 2.5rem; padding-top: 1.5rem; border-top: 1px solid #e5e7eb; }
        .links a { margin-right: 1.5rem; font-size: 0.9rem; }
        footer { margin-top: 3rem; color: #6b7280; font-size: 0.8rem; }
        footer .dot { color: #1877F2; }
        .breadcrumb { margin-bottom: 0.5rem; font-size: 0.85rem; }
        .breadcrumb a { color: #0e7490; }
        .breadcrumb a:hover { color: #1a2e4a; }
    </style>
</head>
<body>
    <main>
        <p class="breadcrumb"><a href="https://twins.la">twins.la</a></p>
        <h1><span class="facebook">facebook</span>.twins.la</h1>
        <p class="tagline">A digital twin of Facebook Login &mdash; OAuth 2.0 and the Graph API slice for signing users in.</p>

        <h2>What is this?</h2>
        <p>
            This is a high-fidelity digital twin of Facebook's Login surface:
            the OAuth 2.0 authorization dialog, token exchange, the Graph API
            <code>/me</code> user-profile endpoint, and <code>/debug_token</code>
            for inspecting access tokens. Code you write against this twin
            works against real Facebook with only hostname changes on the
            dialog and Graph URLs. No Facebook App registration needed to
            develop.
        </p>

        <h2>Supported scenarios</h2>
        <ul>
            <li>OAuth 2.0 authorization &mdash; <code>response_type=code</code> (web) and <code>response_type=token</code> (implicit)</li>
            <li>Authorization code &rarr; access token exchange, with one-shot code consumption</li>
            <li>App access tokens via <code>grant_type=client_credentials</code></li>
            <li>Graph API <code>/me</code> with field selection (<code>id</code>, <code>name</code>, <code>email</code>)</li>
            <li><code>/debug_token</code> with app-attribution to detect token substitution</li>
            <li>Graph API versions <code>v19.0</code> and <code>v21.0</code> served concurrently</li>
            <li>Configurable test apps and users via the Twin Plane</li>
            <li>Failure simulation: invalid token, expired token, missing email grant, user denial</li>
        </ul>

        <h2>How to use it</h2>
        <p>
            <strong>Cloud:</strong> Point your app's Facebook SDK or HTTP
            client at <code>https://facebook.twins.la</code> for both the
            dialog URL (real: <code>www.facebook.com</code>) and the Graph
            URL (real: <code>graph.facebook.com</code>). Ask the operator to
            create a test app and user for you, then walk the OAuth code
            flow.
        </p>
        <p>
            <strong>Local:</strong> Install with <code>pip install
            twins-facebook-local</code> and run a local instance on
            any port. Same API, same behavior, your machine.
        </p>

        <h2>For agents</h2>
        <p>
            Copy this into your agent's system prompt, tool configuration,
            or <code>CLAUDE.md</code>. Also available as plain text at
            <a href="/_twin/agent-instructions"><code>/_twin/agent-instructions</code></a>.
        </p>
        <div class="snippet-box">
            <button class="copy-btn" onclick="navigator.clipboard.writeText(document.getElementById('agent-snippet').textContent).then(()=>{this.textContent='Copied!';setTimeout(()=>this.textContent='Copy',1500)})">Copy</button>
            <pre id="agent-snippet">""" + AGENT_INSTRUCTIONS.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;") + """</pre>
        </div>

        <div class="links">
            <a href="https://github.com/twins-la/facebook">GitHub</a>
            <a href="https://twins.la">twins.la</a>
            <a href="/_twin/health">Health</a>
            <a href="/_twin/scenarios">Scenarios</a>
            <a href="/_twin/references">References</a>
        </div>

        <footer>twins.la <span class="dot">&middot;</span> Where agents meet their environment.</footer>
    </main>
</body>
</html>
"""


@explainer_bp.route("/", methods=["GET"])
def explainer_page():
    """Serve the HTML explainer page."""
    return EXPLAINER_HTML


@explainer_bp.route("/_twin/agent-instructions", methods=["GET"])
def agent_instructions():
    """Serve agent instructions as plain text."""
    return Response(AGENT_INSTRUCTIONS, mimetype="text/plain")
