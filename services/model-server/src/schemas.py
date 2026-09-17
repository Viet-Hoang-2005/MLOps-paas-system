"""HTTP schemas for the inference gateway."""

from typing import Any

from pydantic import BaseModel


class InferenceRequest(BaseModel):
    features: dict[str, Any]
