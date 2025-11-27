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


class AutowireError(DependencyError):
    """Base exception for errors during autowiring."""


class InterfaceMismatchError(AutowireError):
    """Raised when an implementation is injected instead of its registered interface."""


class CaptiveDependencyError(AutowireError):
    """Raised when a Scoped dependency is injected into a Singleton service."""
