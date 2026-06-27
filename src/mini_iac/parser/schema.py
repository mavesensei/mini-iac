from pydantic import BaseModel


class HealthCheckSpec(BaseModel):
    path: str
    port: int
    retries: int = 3
    interval_seconds: int = 2


class ContainerSpec(BaseModel):
    name: str
    image: str
    ports: list[str] = []
    env: dict[str, str] = {}
    depends_on: list[str] = []
    volumes: list[str] = []
    health_check: HealthCheckSpec | None = None


class NetworkSpec(BaseModel):
    name: str


class AppSpec(BaseModel):
    project: str = ""
    containers: list[ContainerSpec] = []
    network: NetworkSpec | None = None
    volumes: list[str] = []
