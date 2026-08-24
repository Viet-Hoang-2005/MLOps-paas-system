"""Canonical names and immutable references for tenant model images."""


def normalize_registry(registry):
    return str(registry or "").replace("https://", "").replace("http://", "").strip("/")


def local_image_repository(project_id):
    return f"image-{str(project_id).lower()}"


def image_repository(project_id, *, registry="", registry_project="user-images"):
    repository = local_image_repository(project_id)
    registry = normalize_registry(registry)
    if not registry:
        return repository
    return f"{registry}/{str(registry_project).strip('/')}/{repository}"


def build_image_tag(build_id):
    return f"build-{str(build_id).lower()}"


def version_image_tag(version_number):
    return f"v{version_number}"


def tagged_image_reference(repository, tag):
    return f"{str(repository).rstrip('/')}:{tag}"


def temporary_image_reference(project_id, build_id, *, registry="", registry_project="user-images"):
    return tagged_image_reference(
        image_repository(project_id, registry=registry, registry_project=registry_project),
        build_image_tag(build_id),
    )


def repository_from_reference(reference):
    reference = str(reference or "").strip()
    if "@" in reference:
        return reference.split("@", 1)[0]
    head, separator, tail = reference.rpartition("/")
    if ":" in tail:
        tail = tail.rsplit(":", 1)[0]
    return f"{head}{separator}{tail}" if separator else tail


def immutable_image_reference(build):
    """Pin production by OCI digest and local Docker by image ID."""

    if not build.image_digest:
        return build.image_uri
    if build.backend == "argo":
        return f"{repository_from_reference(build.image_uri)}@{build.image_digest}"
    return build.image_digest
