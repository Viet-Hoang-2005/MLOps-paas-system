"""Model-packager process entrypoint."""

import os

if __name__ == "__main__":
    if os.environ.get("TASK_TYPE") == "NOTIFY_BUILD":
        from src.notify import main
    else:
        from src.tasks import main

    main()
