# src/mini_iac/state/models.py
from datetime import datetime
from pydantic import BaseModel


class ResourceRecord(BaseModel):
    id: str
    name: str
    resource_type: str
    spec_hash: str
    spec_dict: dict | None = None
    depends_on: list[str] = []
    docker_labels: dict[str, str] = {}
    created_at: datetime


class State(BaseModel):
    version: int = 0
    project: str = ""
    resources: dict[str, ResourceRecord] = {}
