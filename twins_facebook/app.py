"""Flask application factory for the Facebook twin.

The host calls create_app() with a storage backend and configuration,
and receives a configured Flask application to serve.
"""

import logging

from flask import Flask, g, jsonify

from .errors import unknown_path
from .explainer import explainer_bp
from .routes.debug_token import debug_token_bp
from .routes.graph_me import graph_me_bp
from .routes.oauth_dialog import oauth_dialog_bp
from .routes.oauth_token import oauth_token_bp
from .storage import FacebookTwinStorage
from .twin_plane.routes import twin_plane_bp

logger = logging.getLogger(__name__)


def create_app(
    storage: FacebookTwinStorage,
    tenants=None,
    config: dict | None = None,
) -> Flask:
    """Create and configure the Facebook twin Flask application.

    Args:
        storage: A FacebookTwinStorage implementation provided by the host.
        tenants: A TenantStore implementation. Required for Twin Plane tenant
            auth; tests may omit it for exercises that only hit unauth paths.
        config: Configuration dict. Supported keys:
            - base_url (str): Public base URL of the twin.
            - admin_token (str): Admin bearer token for Twin Plane admin ops.
              Empty string means "accept any bearer" (local dev convenience).
            - interactive_dialog (bool): If True, /dialog/oauth renders a
              consent HTML page; default False (auto-approve).
            - is_cloud (bool): Enables the cloud guard that rejects
              tenant_id="default".

    Returns:
        Configured Flask application.
    """
    config = config or {}
    base_url = config.get("base_url", "http://localhost:8081")
    admin_token = config.get("admin_token", "")
    interactive_dialog = bool(config.get("interactive_dialog", False))
    is_cloud = bool(config.get("is_cloud", False))

    app = Flask(__name__)
    app.config["TWIN_STORAGE"] = storage
    app.config["TWIN_TENANTS"] = tenants
    app.config["TWIN_BASE_URL"] = base_url
    app.config["TWIN_ADMIN_TOKEN"] = admin_token
    app.config["TWIN_IS_CLOUD"] = is_cloud
    app.config["TWIN_SETTINGS"] = {"interactive_dialog": interactive_dialog}

    @app.before_request
    def _inject():
        g.storage = app.config["TWIN_STORAGE"]
        g.tenants = app.config["TWIN_TENANTS"]
        g.base_url = app.config["TWIN_BASE_URL"]
        g.admin_token = app.config["TWIN_ADMIN_TOKEN"]
        g.is_cloud = app.config["TWIN_IS_CLOUD"]
        g.settings = app.config["TWIN_SETTINGS"]

    app.register_blueprint(oauth_dialog_bp)
    app.register_blueprint(oauth_token_bp)
    app.register_blueprint(graph_me_bp)
    app.register_blueprint(debug_token_bp)
    app.register_blueprint(twin_plane_bp)
    app.register_blueprint(explainer_bp)

    @app.errorhandler(404)
    def _not_found(_e):
        # Graph-shape JSON for /v* paths; plain 404 for everything else.
        path = _request_path_safe()
        if path.startswith("/v"):
            return unknown_path(path)
        body = jsonify({"error": "Not found", "path": path})
        body.status_code = 404
        return body

    logger.info("Facebook twin created — base_url=%s", base_url)
    return app


def _request_path_safe() -> str:
    from flask import request
    try:
        return request.path
    except Exception:  # pragma: no cover — only during error-handler edge cases
        return "/"
