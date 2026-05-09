"""Sweep test: unknown ``/v<num>/<rest>`` paths return Graph-shaped JSON 404.

Closes twins-la/twins-la#2 (facebook half). The catch-all already lives
in `app.py:_not_found` (registered as `@app.errorhandler(404)` and routes
``/v*`` paths to `errors.unknown_path`); this sweep is the explicit
coverage.

Facebook's documented Graph error envelope is
``{error: {message, type, code, fbtrace_id}}``.
"""

import pytest


@pytest.mark.parametrize(
    "method,path",
    [
        ("GET", "v18.0/me/foo-no-such-edge"),
        ("POST", "v17.0/me/wrong-thing"),
        ("DELETE", "v18.0/some/very/deep/path"),
        ("GET", "v17.0/foo/bar/baz/quux"),
        ("POST", "v19.0/totally-unknown/edge/path"),
    ],
)
def test_unknown_graph_path_returns_json_404(client, method, path):
    full = f"/{path}"
    resp = client.open(
        full,
        method=method,
        json={"foo": "bar"} if method in ("POST", "PUT", "PATCH") else None,
    )
    assert resp.status_code == 404, f"{method} {full} got {resp.status_code}"
    assert resp.headers["Content-Type"].startswith("application/json"), (
        f"{method} {full} returned {resp.headers.get('Content-Type')!r} "
        f"body={resp.get_data(as_text=True)[:200]!r}"
    )
    body = resp.get_json()
    assert body is not None and "error" in body
    err = body["error"]
    # Graph error envelope.
    assert err["type"] == "GraphMethodException"
    assert err["code"] == 803
    assert "does not exist" in err["message"].lower()


def test_unknown_graph_path_no_html_leak(client):
    resp = client.get("/v18.0/literally-anything")
    body = resp.get_data(as_text=True)
    assert "<!doctype" not in body.lower()
