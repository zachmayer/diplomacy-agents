"""Pytest configuration."""

import logging


def pytest_configure() -> None:  # noqa: D103
    # Silence verbose INFO logs from httpx (and httpcore) during test runs
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)
