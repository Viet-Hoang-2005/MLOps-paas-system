"""Training-runner process entrypoint."""

import sys

from src import application


def main() -> None:
    application.main()


if __name__ == "__main__":
    try:
        main()
    except Exception:
        # The application already emitted a sanitized terminal error.
        sys.exit(1)
