"""Shared Docker container ownership, creation, and removal primitives."""

import docker.errors


def verify_container(
    container,
    expected_labels,
    recorded_id,
    *,
    error_cls,
    ownership_msg,
    identity_msg,
):
    container.reload()
    labels = container.attrs.get("Config", {}).get("Labels") or {}
    has_mlops_labels = any(key.startswith("mlops_") for key in labels)
    if has_mlops_labels and any(labels.get(key) != value for key, value in expected_labels.items()):
        raise error_cls(ownership_msg)
    if recorded_id and recorded_id != container.id:
        raise error_cls(identity_msg)
    return container


def get_owned_container(
    client,
    container_name,
    expected_labels,
    recorded_id,
    *,
    error_cls,
    ownership_msg,
    identity_msg,
):
    container = client.containers.get(container_name)
    return verify_container(
        container,
        expected_labels,
        recorded_id,
        error_cls=error_cls,
        ownership_msg=ownership_msg,
        identity_msg=identity_msg,
    )


def create_or_attach_container(
    docker_client,
    container_name,
    expected_labels,
    recorded_id,
    *,
    error_cls,
    ownership_msg,
    identity_msg,
    missing_msg,
    **run_kwargs,
):
    client = docker_client.client
    try:
        container = get_owned_container(
            client,
            container_name,
            expected_labels,
            recorded_id,
            error_cls=error_cls,
            ownership_msg=ownership_msg,
            identity_msg=identity_msg,
        )
    except docker.errors.NotFound:
        if recorded_id:
            raise error_cls(missing_msg) from None
        merged_labels = {**run_kwargs.get("labels", {}), **expected_labels}
        run_kwargs["labels"] = merged_labels
        try:
            container = docker_client.run(**run_kwargs)
        except docker.errors.APIError as exc:
            if exc.status_code != 409:
                raise
            container = get_owned_container(
                client,
                container_name,
                expected_labels,
                recorded_id,
                error_cls=error_cls,
                ownership_msg=ownership_msg,
                identity_msg=identity_msg,
            )
    if container.attrs.get("State", {}).get("Status") == "created":
        container.start()
    return container


def remove_owned_container(get_container_fn, *, stop_timeout=None):
    try:
        container = get_container_fn()
    except docker.errors.NotFound:
        return
    if stop_timeout is not None:
        try:
            container.stop(timeout=stop_timeout)
        except docker.errors.NotFound:
            return
        except Exception:
            pass
    try:
        container.remove(force=True)
    except docker.errors.NotFound:
        pass
