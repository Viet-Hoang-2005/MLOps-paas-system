"""Process entrypoint for a single drift-analysis run."""

import sys

from src.application import main


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception:
        # The application already emitted a sanitized terminal error.
        sys.exit(1)
