# Backend testing

Run checks from the target service so pytest finds the correct config, fixtures and imports. Match the environment in [CI](../../../../.github/workflows/ci.yml), including Python 3.12 and runtime/test requirements. See [TESTING.md](../../../../TESTING.md) for broader acceptance.

- Control Plane: `python -m pytest src/apps/<app>/tests`. For model/schema changes also run `python manage.py check --settings=config.settings.test` and `python manage.py makemigrations --check --dry-run --settings=config.settings.test`.
- Other services: `python -m pytest tests` or an affected test file. CI applies service-specific coverage gates.
- For Python code changes, run Ruff against the changed paths. Keep unit tests isolated from real brokers, S3, Docker and cluster credentials. Use the repository's integration settings when PostgreSQL behavior, real Docker, or external I/O is the subject of the test.
- For image dependencies, identify install inputs from the target Dockerfile. Resolve intersecting pins on the target Python/platform, build with that Dockerfile, run `python -m pip check` in the image, then run targeted tests or smoke the affected entry point. A host resolver check alone does not verify Linux wheels, native libraries or image startup.
