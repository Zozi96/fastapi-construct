import inspect
from collections.abc import Callable
from functools import lru_cache
from typing import Any, TypeVar

from .enums import ServiceLifetime
from .exceptions import CircularDependencyError, DependencyNotFoundError, DependencyRegistrationError


T = TypeVar("T")


class DependencyConfig:
    def __init__(self, provider: Callable, lifetime: ServiceLifetime) -> None:
        self.provider = provider
        self.lifetime = lifetime


def _create_singleton_wrapper(cls: type[Any]) -> Callable:
    @lru_cache(maxsize=1)
    def singleton_factory(*args, **kwargs):
        return cls(*args, **kwargs)

    old_sig = inspect.signature(cls.__init__)
    new_params = [p for name, p in old_sig.parameters.items() if name != "self"]
    singleton_factory.__signature__ = old_sig.replace(parameters=new_params)  # type: ignore

    return singleton_factory


class Container:
    """
    Dependency Injection Container.

    Manages the registration and resolution of dependencies.
    """

    def __init__(self):
        self._registry: dict[type[Any], DependencyConfig] = {}
        self._resolving: set[type[Any]] = set()

    def register(
        self,
        interface: type[Any],
        provider: Callable,
        lifetime: ServiceLifetime = ServiceLifetime.SCOPED,
    ) -> None:
        """
        Registers a dependency provider for a specific interface.

        Args:
            interface: The type or interface to register.
            provider: The callable responsible for creating the dependency instance.
            lifetime: The scope of the dependency instance.

        Raises:
            DependencyRegistrationError: If the provider is invalid.
        """
        if not callable(provider):
            raise DependencyRegistrationError(f"Provider for {interface} must be callable.")

        final_provider = provider

        if lifetime == ServiceLifetime.SINGLETON and inspect.isclass(provider):
            final_provider = _create_singleton_wrapper(provider)

        self._registry[interface] = DependencyConfig(final_provider, lifetime)

    def get_config(self, interface: type[Any]) -> DependencyConfig | None:
        """
        Retrieves the dependency configuration for a given interface.

        Args:
            interface: The interface or type to retrieve.

        Returns:
            The configuration if found, None otherwise.
        """
        return self._registry.get(interface)

    def resolve(self, interface: type[T]) -> T:
        """
        Resolves a dependency recursively.

        Args:
            interface: The interface or type to resolve.

        Returns:
            The resolved instance.

        Raises:
            DependencyNotFoundError: If the dependency is not registered.
            CircularDependencyError: If a circular dependency is detected.
        """
        if interface in self._resolving:
            raise CircularDependencyError(f"Circular dependency detected for {interface}")

        config = self.get_config(interface)
        if not config:
            raise DependencyNotFoundError(f"No provider registered for {interface}")

        self._resolving.add(interface)
        try:
            provider = config.provider

            # Determine signature to inspect
            if inspect.isclass(provider):
                sig = inspect.signature(provider.__init__)
                # Remove self parameter for class __init__
                params = [p for name, p in sig.parameters.items() if name != "self"]
                sig = sig.replace(parameters=params)
            else:
                sig = inspect.signature(provider)

            # Resolve arguments
            kwargs = {}
            for name, param in sig.parameters.items():
                if param.annotation != inspect.Parameter.empty and self.get_config(param.annotation):
                    # Check if annotation is a registered dependency
                    kwargs[name] = self.resolve(param.annotation)
                    continue

                # If not a dependency, check for default value
                if param.default != inspect.Parameter.empty:
                    # If default is a Depends object (from autowiring), we might want to resolve it?
                    # But for manual resolution, we usually rely on type hints.
                    # If we can't resolve it and there is a default, use the default.
                    kwargs[name] = param.default
                    continue

                # If we can't resolve and no default, we can't proceed (unless we want to pass None?)
                # For now, let it fail at call time or raise here.
                # Let's try to resolve it anyway if it's a class, maybe it's a concrete class not registered?
                # But we only resolve registered dependencies.

            return provider(**kwargs)
        finally:
            self._resolving.remove(interface)


# Global default container
default_container = Container()


def register_dependency(
    interface: type[Any], provider: Callable, lifetime: ServiceLifetime = ServiceLifetime.SCOPED
) -> None:
    """
    Registers a dependency provider in the default container.
    """
    default_container.register(interface, provider, lifetime)


def get_dependency_config(interface: type[Any]) -> DependencyConfig | None:
    """
    Retrieves dependency configuration from the default container.
    """
    return default_container.get_config(interface)


def add_transient(interface: type[Any], provider: Callable) -> None:
    """
    Registers a transient dependency in the default container.
    """
    default_container.register(interface, provider, ServiceLifetime.TRANSIENT)


def add_scoped(interface: type[Any], provider: Callable) -> None:
    """
    Registers a scoped dependency in the default container.
    """
    default_container.register(interface, provider, ServiceLifetime.SCOPED)


def add_singleton(interface: type[Any], provider: Callable) -> None:
    """
    Registers a singleton dependency in the default container.
    """
    default_container.register(interface, provider, ServiceLifetime.SINGLETON)
