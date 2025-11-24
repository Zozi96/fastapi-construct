from enum import Enum


class ServiceLifetime(Enum):
    """Defines the lifecycle of a dependency."""

    TRANSIENT = "transient"
    SCOPED = "scoped"
    SINGLETON = "singleton"
