"""Configuration for local hosting of the Facebook twin."""

import os

DB_PATH = os.environ.get("TWIN_DB_PATH", "data/facebook.db")
HOST = os.environ.get("TWIN_HOST", "0.0.0.0")
PORT = int(os.environ.get("TWIN_PORT", "8081"))
BASE_URL = os.environ.get("TWIN_BASE_URL", f"http://localhost:{PORT}")
ADMIN_TOKEN = os.environ.get("TWIN_ADMIN_TOKEN", "")
INTERACTIVE_DIALOG = os.environ.get("TWIN_INTERACTIVE_DIALOG", "").lower() in ("1", "true", "yes")
