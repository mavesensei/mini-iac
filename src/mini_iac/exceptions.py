class MiniIacError(Exception):
    pass


class ConfigError(MiniIacError):
    pass


class StateError(MiniIacError):
    pass


class PlannerError(MiniIacError):
    pass


class DockerError(MiniIacError):
    pass


class DaemonNotReachable(DockerError):
    pass


class ImagePullError(DockerError):
    pass


class ContainerNotFoundError(DockerError):
    pass


class HealthCheckFailedError(DockerError):
    def __init__(self, message: str, last_error: Exception | None = None, attempts: int = 0):
        super().__init__(message)
        self.last_error = last_error
        self.attempts = attempts
