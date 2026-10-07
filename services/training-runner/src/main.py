"""Training-runner process entrypoint."""

import sys

def main() -> None:
    if "--worker" in sys.argv:
        from src import application

        application.main()
    else:
        from src.supervisor import run

        sys.exit(run())


if __name__ == "__main__":
    try:
        main()
    except Exception:
        # The application already emitted a sanitized terminal error.
        sys.exit(1)
