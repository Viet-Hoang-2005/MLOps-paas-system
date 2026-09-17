"""Docker build-context generation and image publication."""


def build_image(*, workspace, build_id, requirements_text, serving_image,
                image_label, docker_module, environment, image_reference, detail):
    docker_client = docker_module.from_env()
    harbor_url = environment.get("HARBOR_REGISTRY_URL", "").strip().rstrip("/")
    harbor_user = environment.get("HARBOR_USERNAME", "").strip()
    harbor_pass = environment.get("HARBOR_PASSWORD", "").strip()
    if harbor_url and harbor_user and harbor_pass:
        detail(f"Logging into Harbor registry at {harbor_url}...")
        docker_client.login(username=harbor_user, password=harbor_pass, registry=harbor_url)

    base_image = (f"{harbor_url}/mlops-paas/{serving_image}:latest" if harbor_url
                  else f"mlops-paas-{serving_image}:latest")
    dockerfile_content = f"""FROM {base_image}
USER root
COPY requirements.txt /tmp/custom_requirements.txt
RUN grep -i -v -E '^(fastapi|uvicorn|starlette|pydantic|bentoml|httpx)([[:space:]=<>~!]*)?$' /tmp/custom_requirements.txt > /tmp/safe_requirements.txt || touch /tmp/safe_requirements.txt
RUN pip install --no-cache-dir -r /tmp/safe_requirements.txt || echo 'Some requirements failed to install, continuing...'
COPY model /app/model_artifact
"""
    (workspace / "Dockerfile").write_text(dockerfile_content, encoding="utf-8")
    requirements = requirements_text.strip()
    (workspace / "requirements.txt").write_text(
        (requirements + "\n") if requirements else "\n", encoding="utf-8",
    )
    image_tag = image_reference(build_id)
    detail(f"Building {image_label}Docker image {image_tag} from workspace {workspace}...")
    for line in docker_client.api.build(path=str(workspace), tag=image_tag, rm=True, decode=True):
        if "stream" in line:
            detail(line["stream"].strip())
        elif "errorDetail" in line:
            raise RuntimeError(line["errorDetail"].get("message", "Unknown Docker build error"))
    detail(f"{image_label}Docker image {image_tag} built successfully!")
    if harbor_url and harbor_user and harbor_pass and image_tag.startswith(f"{harbor_url}/"):
        detail(f"Pushing {image_label}image {image_tag} to Harbor...")
        for line in docker_client.images.push(image_tag, stream=True, decode=True):
            if "status" in line:
                detail(line.get("status", ""))
            elif "errorDetail" in line:
                raise RuntimeError(line["errorDetail"].get("message", "Failed to push image to Harbor"))
        detail(f"{image_label}image successfully pushed to Harbor!")
