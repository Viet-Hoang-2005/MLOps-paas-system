"""Environment-backed image naming for model packaging."""


def image_reference(environment, build_id: str = "") -> str:
    build_id = environment.get("BUILD_ID", "").strip().lower() or build_id.lower()
    project_id = environment.get("PROJECT_ID", "").strip().lower() or build_id
    repository = environment.get("IMAGE_REPOSITORY", "").strip().rstrip("/")
    tag = environment.get("IMAGE_TAG", "").strip() or f"build-{build_id}"
    if not repository:
        repository = f"image-{project_id}"
        harbor_url = environment.get("HARBOR_REGISTRY_URL", "").strip().rstrip("/")
        harbor_project = environment.get("HARBOR_USER_PROJECT", "user-images").strip().strip("/")
        if harbor_url:
            repository = f"{harbor_url}/{harbor_project}/{repository}"
    return f"{repository}:{tag}"
