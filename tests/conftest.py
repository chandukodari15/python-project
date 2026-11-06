"""
Pytest configuration and test fixtures for WattWise.
Uses an isolated in-memory or temporary SQLite test database.
"""
import os
import sys
import tempfile
import pytest

# Ensure application package is discoverable
APP_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if APP_DIR not in sys.path:
    sys.path.insert(0, APP_DIR)

import db
from app import app as flask_app


@pytest.fixture(scope="session")
def app():
    flask_app.config.update({
        "TESTING": True,
        "DEBUG": False,
        "WTF_CSRF_ENABLED": False,
    })
    return flask_app


@pytest.fixture(scope="function")
def client(app, tmp_path):
    """
    Creates a fresh, isolated test database for every test function.
    """
    test_db_path = str(tmp_path / "test_isolated.db")
    
    # Override db module state to target this temporary test database
    db._active_engine = "sqlite"
    db.init_sqlite_tables(test_db_path)
    
    # Monkey-patch get_connection to return connection to this test db
    original_get_connection = db.get_connection
    db.get_connection = lambda: db.get_sqlite_connection(test_db_path)
    
    with app.test_client() as test_client:
        with app.app_context():
            yield test_client

    # Restore original connection
    db.get_connection = original_get_connection
