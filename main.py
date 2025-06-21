"""CLI entrypoint for diplomacy-agents."""

import logging

logging.basicConfig(
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    level=logging.INFO,
)

logger = logging.getLogger(__name__)


def main() -> None:  # noqa: D401
    """Run a greeting."""
    logger.info("Hello from diplomacy-agents!")


if __name__ == "__main__":
    main()
