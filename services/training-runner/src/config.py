"""Environment access for a training job."""


def require_env(environment, name: str) -> str:
    value = environment.get(name, "").strip()
    if not value:
        raise RuntimeError(f"Missing required environment variable: {name}")
    return value
