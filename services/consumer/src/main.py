"""Thin process entrypoint for the consumer runtime."""


def run() -> None:
    """Import runtime dependencies only after logging has been configured."""
    from src.kafka_runtime import run as runtime_run

    runtime_run()


if __name__ == "__main__":
    run()
