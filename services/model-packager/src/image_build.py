"""Docker build-context generation and image publication."""

import re

# Packages the serving image pins itself; a model's requirements must not replace them.
PROTECTED_PACKAGES = frozenset({"fastapi", "uvicorn", "starlette", "pydantic", "pydantic-core", "bentoml", "httpx"})
_REQUIREMENT_NAME = re.compile(r"[A-Za-z0-9](?:[A-Za-z0-9._-]*[A-Za-z0-9])?")


def _logical_lines(requirements_text):
    """Requirement lines with backslash continuations joined, as pip reads them."""
    lines, pending = [], ""
    for raw in requirements_text.splitlines():
        line = raw.rstrip()
        if line.endswith(chr(92)):
            pending += line[:-1] + " "
            continue
        lines.append(pending + line)
        pending = ""
    if pending:
        lines.append(pending)
    return lines


def requirement_name(line):
    """The normalized package name a requirement line installs; None if it has no name."""
    match = _REQUIREMENT_NAME.match(line.strip())
    return re.sub(r"[-_.]+", "-", match.group(0)).lower() if match else None


def filter_protected_requirements(requirements_text):
    kept, dropped = [], []
    for line in _logical_lines(requirements_text or ""):
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        name = requirement_name(stripped)
        if name is None:
            raise ValueError(f"Unrecognised requirement line: {stripped[:80]!r}")
        (dropped if name in PROTECTED_PACKAGES else kept).append(stripped)
    return "\n".join(kept), dropped


def render_dockerfile(base_image, *, has_requirements):
    """The serving-image Dockerfile. A failed ``pip install`` fails the build."""
    lines = [f"FROM {base_image}", "USER root"]
    if has_requirements:
        pinned = "|".join(sorted(name.replace("-", "[-_]") for name in PROTECTED_PACKAGES))
        lines += [
            "COPY requirements.txt /tmp/requirements.txt",
            f"RUN pip freeze | grep -i -E '^({pinned})==' > /tmp/constraints.txt || true",
            "RUN pip install --no-cache-dir -c /tmp/constraints.txt -r /tmp/requirements.txt",
        ]
    lines.append("COPY model /app/model_artifact")
    return "\n".join(lines) + "\n"


def serving_base_image(serving_image, harbor_url=""):
    harbor_url = (harbor_url or "").strip().rstrip("/")
    return f"{harbor_url}/mlops-paas/{serving_image}:latest" if harbor_url else f"mlops-paas-{serving_image}:latest"


def write_build_context(workspace, base_image, requirements_text, detail):
    """Write the Dockerfile and requirements.txt; return the requirements actually used."""
    kept, dropped = filter_protected_requirements(requirements_text)
    for line in dropped:
        detail(f"Ignoring requirement that would replace the serving stack: {line}")
    (workspace / "Dockerfile").write_text(render_dockerfile(base_image, has_requirements=bool(kept)), encoding="utf-8")
    (workspace / "requirements.txt").write_text((kept + "\n") if kept else "\n", encoding="utf-8")
    return kept


def build_image(
    *,
    workspace,
    build_id,
    requirements_text,
    serving_image,
    image_label,
    docker_module,
    environment,
    image_reference,
    detail,
):
    docker_client = docker_module.from_env()
    harbor_url = environment.get("HARBOR_REGISTRY_URL", "").strip().rstrip("/")
    harbor_user = environment.get("HARBOR_USERNAME", "").strip()
    harbor_pass = environment.get("HARBOR_PASSWORD", "").strip()
    if harbor_url and harbor_user and harbor_pass:
        detail(f"Logging into Harbor registry at {harbor_url}...")
        docker_client.login(username=harbor_user, password=harbor_pass, registry=harbor_url)

    write_build_context(workspace, serving_base_image(serving_image, harbor_url), requirements_text, detail)
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
