"""Explicit opt-in for disposable local PostgreSQL integration tests."""
import os
from urllib.parse import urlparse
import pytest


def pytest_addoption(parser):
    parser.addoption("--test-database-url", default=None, help="Disposable local PostgreSQL URL; database name must end with _test")


def pytest_configure(config):
    value = config.getoption("--test-database-url")
    if value:
        target = urlparse(value)
        if target.hostname not in {"localhost", "127.0.0.1"} or not target.path.endswith("_test"):
            raise pytest.UsageError("CLI test database must be local and have a name ending in _test")
        os.environ["TEST_DATABASE_URL"] = value
