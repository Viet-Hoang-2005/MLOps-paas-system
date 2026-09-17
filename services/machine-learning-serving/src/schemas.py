"""HTTP schemas for the machine-learning serving worker."""

from typing import Any

from pydantic import BaseModel


class InferenceRequest(BaseModel):
    features: dict[str, Any]
    model_version_id: str | None = None
