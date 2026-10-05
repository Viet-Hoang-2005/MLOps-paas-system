import docker


class DockerClient:
    def __init__(self, client=None, timeout=60):
        self.client = client or docker.from_env(timeout=timeout)

    def run(self, **kwargs):
        kwargs.setdefault("detach", True)
        kwargs.setdefault("remove", False)
        return self.client.containers.run(**kwargs)

    def remove_if_successful(self, container):
        container.reload()
        if container.attrs.get("State", {}).get("ExitCode") == 0:
            container.remove()
