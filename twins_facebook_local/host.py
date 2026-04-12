"""Local host entry point for the Facebook twin.

Wires SQLite storage, creates the Facebook twin Flask app, and serves
it. Can be run directly or via gunicorn.
"""

import logging
import os

from twins_facebook.app import create_app

from .config import ADMIN_TOKEN, BASE_URL, DB_PATH, INTERACTIVE_DIALOG
from .storage_sqlite import SQLiteFacebookStorage

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s — %(message)s",
)
logger = logging.getLogger(__name__)


def create_local_app():
    """WSGI entry point for gunicorn:

        gunicorn 'twins_facebook_local.host:create_local_app()'
    """
    db_dir = os.path.dirname(DB_PATH)
    if db_dir:
        os.makedirs(db_dir, exist_ok=True)

    storage = SQLiteFacebookStorage(db_path=DB_PATH)
    app = create_app(storage=storage, config={
        "base_url": BASE_URL,
        "admin_token": ADMIN_TOKEN,
        "interactive_dialog": INTERACTIVE_DIALOG,
    })
    logger.info("Local Facebook twin ready — db=%s base_url=%s", DB_PATH, BASE_URL)
    return app


def main():
    from .config import HOST, PORT
    app = create_local_app()
    logger.info("Starting local Facebook twin on %s:%d", HOST, PORT)
    app.run(host=HOST, port=PORT, debug=False)


if __name__ == "__main__":
    main()
