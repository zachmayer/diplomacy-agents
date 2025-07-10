"""
Project-wide logging bootstrap helper.

Call ``setup_logging()`` once near application start to configure the root
logger with a consistent formatting style.  Subsequent modules can safely
call it again – it will be a no-op if the root logger is already configured.
"""

from __future__ import annotations

import logging

__all__ = ["setup_logging"]


def setup_logging(level: str = "INFO", json: bool = False) -> None:  # noqa: D401
    """
    Configure root logger if no handler exists.

    Parameters
    ----------
    level
        Root log level (e.g. "INFO", "DEBUG").
    json
        Emit logs as single-line JSON objects when *True* (useful for parsing).

    """
    if logging.getLogger().handlers:
        # Logging already configured – skip.
        return

    fmt = (
        '{"ts":"%(asctime)s","lvl":"%(levelname)s","name":"%(name)s","msg":"%(message)s"}'
        if json
        else "%(asctime)s %(levelname)s %(name)s: %(message)s"
    )
    logging.basicConfig(format=fmt, level=getattr(logging, level.upper(), logging.INFO))
