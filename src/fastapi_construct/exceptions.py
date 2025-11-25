class FastAPIConstructError(Exception):
    """Base exception for fastapi-construct errors."""


class DependencyError(FastAPIConstructError):
    """Base exception for dependency injection errors."""


class DependencyNotFoundError(DependencyError):
    """Raised when a requested dependency is not found in the container."""


class DependencyRegistrationError(DependencyError):
    """Raised when there is an error registering a dependency."""


class CircularDependencyError(DependencyError):
    """Raised when a circular dependency is detected."""
