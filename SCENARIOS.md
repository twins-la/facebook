# Facebook Twin — Supported Scenarios

## Facebook Login (Supported)

The Facebook Login scenario enables applications to authenticate users via Facebook's OAuth 2.0 flow and retrieve the user's basic profile from the Graph API. Code written against this twin for the Facebook Login scenario should work against real Facebook with only hostname changes.

### Scope

**In scope:**

- Authorization dialog — `GET /dialog/oauth` and `GET /v{19,21}/dialog/oauth`
  - `response_type=code` (authorization-code flow, for web apps)
  - `response_type=token` (implicit flow, for mobile/SPA clients) — returns token in URL fragment
  - Redirect-URI allowlisting against the registered app
  - `state` parameter round-trip (CSRF protection)
  - `scope` parameter parsing (comma- or space-separated)
  - User-denial simulation via `twin_simulate=denied` → `error=access_denied`
- Token exchange — `GET /v{19,21}/oauth/access_token`
  - Authorization code → short-lived user access token
  - One-shot code consumption (reuse is rejected)
  - Redirect-URI binding (code is only valid with the redirect_uri used to issue it)
  - App credentials validation (app_id + app_secret)
  - `grant_type=client_credentials` → app access token (`APP_ID|APP_SECRET` shape)
- Graph API user profile — `GET /v{19,21}/me` and `GET /v{19,21}/<fb_user_id>`
  - Access token via `Authorization: Bearer`, `?access_token=…`, or form body
  - `fields` parameter (whitelist: `id`, `name`, `email`)
  - `email` is omitted (not errored) when the user has not granted the `email` scope
- Token inspection — `GET /v{19,21}/debug_token`
  - Validates caller credentials (app access token or user access token)
  - Returns `app_id`, `user_id`, `type`, `is_valid`, `expires_at`, `scopes` for the inspected token
  - Detects token substitution: `app_id` in the response reflects the *issuing* app, not the caller's app
- Facebook-shape error envelope:
  `{"error": {"message", "type", "code", "fbtrace_id", "error_subcode"?}}`
  - Well-known codes used by the twin: `100` (parameter), `101` (app credentials), `190` (access token), `191` (redirect_uri), `803` (unknown path), `2500` (unknown API version)
- Configurable test behavior via Twin Plane (`/_twin/...`):
  - App CRUD (`app_id`, `app_secret`, registered `redirect_uris`)
  - Test-user CRUD (`fb_id`, `name`, `email`, `granted_scopes`, `simulate_invalid`, `simulate_expired`)
  - Direct token minting for fixture-style tests
  - Interactive dialog toggle (`PUT /_twin/settings {"interactive_dialog": true}`)
  - Scoped operation logs

**Out of scope (behavior may be fabricated):**

- Friends, social graph, followers, followees
- Photos, videos, media APIs
- Posting, commenting, reacting, sharing
- Pages, Groups, Business APIs, Marketing/Ads APIs
- Webhooks, Realtime Updates, Messenger platform
- Long-lived token exchange, token refresh, server-to-server code-flow extensions
- Facebook SDK client-side JS/iOS/Android behavior (the SDK is the caller's concern, not the twin's)
- Multi-factor auth, account recovery, account creation
- Geographic/device attribution fields on the user resource

### Graph API versions supported

Real Facebook serves multiple Graph API versions concurrently under different path prefixes. The twin preserves this: every Graph endpoint is mounted under every supported version path.

| Version | Status | First retrieved |
|---------|--------|-----------------|
| v19.0   | supported | 2026-04-12 |
| v21.0   | supported | 2026-04-12 |

Requests to an unsupported version path return a Facebook-format error (code 2500).

### Single-host serving

Real Facebook splits the dialog (`https://www.facebook.com`) from the Graph API (`https://graph.facebook.com`) across two hostnames. The twin serves both surfaces under one base URL. Consumers configure the dialog URL and Graph URL independently in their client; both can point at the same twin host.

### Authoritative References

- Facebook Login — Manually Build a Login Flow: https://developers.facebook.com/docs/facebook-login/guides/advanced/manual-flow (retrieved 2026-04-12)
- Graph API — Access Tokens: https://developers.facebook.com/docs/facebook-login/guides/access-tokens (retrieved 2026-04-12)
- Graph API — /me User endpoint: https://developers.facebook.com/docs/graph-api/reference/user/ (retrieved 2026-04-12)
- Graph API — /debug_token: https://developers.facebook.com/docs/graph-api/reference/v19.0/debug_token (retrieved 2026-04-12)
- Graph API — Error Handling: https://developers.facebook.com/docs/graph-api/guides/error-handling/ (retrieved 2026-04-12)
- Graph API — Changelog & supported versions: https://developers.facebook.com/docs/graph-api/changelog/ (retrieved 2026-04-12)

The running twin exposes the same reference list at `GET /_twin/references`.

### Version

0.1.0 — Initial Facebook Login scenario implementation, v19.0 and v21.0.
