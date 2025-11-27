import inspect
from collections.abc import Callable
from functools import lru_cache
from typing import Any

from .enums import ServiceLifetime
from .exceptions import CircularDependencyError, DependencyNotFoundError, DependencyRegistrationError


class DependencyConfig[T]:
    def __init__(self, provider: Callable[..., T], lifetime: ServiceLifetime) -> None:
        self.provider = provider
        self.lifetime = lifetime


def _create_singleton_wrapper[T](cls: type[T]) -> Callable[..., T]:
    @lru_cache(maxsize=1)
    def singleton_factory(*args, **kwargs) -> T:
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
        self._registry: dict[type, DependencyConfig] = {}
        self._resolving: set[type] = set()
        self._singletons: dict[type, Any] = {}

    def register[T](
        self,
        interface: type[T],
        provider: Callable[..., T],
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

        self._registry[interface] = DependencyConfig(provider, lifetime)

    def get_config[T](self, interface: type[T]) -> DependencyConfig[T] | None:
        """
        Retrieves the dependency configuration for a given interface.

        Args:
            interface: The interface or type to retrieve.

        Returns:
            The configuration if found, None otherwise.
        """
        return self._registry.get(interface)  # type: ignore

    def resolve[T](self, interface: type[T]) -> T:
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

        # If it's a singleton and we already have an instance, return it
        if config.lifetime == ServiceLifetime.SINGLETON and interface in self._singletons:
            return self._singletons[interface]  # type: ignore

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
                    kwargs[name] = param.default
                    continue

            instance = provider(**kwargs)

            if config.lifetime == ServiceLifetime.SINGLETON:
                self._singletons[interface] = instance

            return instance
        finally:
            self._resolving.remove(interface)

    def reset(self) -> None:
        """
        Reset the container state, clearing all singletons and registry.
        Useful for testing.
        """
        self._registry.clear()
        self._resolving.clear()
        self._singletons.clear()

    def get_singleton[T](self, interface: type[T]) -> T | None:
        """
        Retrieve a singleton instance if it exists.
        """
        return self._singletons.get(interface)

    def set_singleton[T](self, interface: type[T], instance: T) -> None:
        """
        Register a singleton instance.
        """
        self._singletons[interface] = instance


# Global default container
default_container = Container()


def register_dependency[T](
    interface: type[T], provider: Callable[..., T], lifetime: ServiceLifetime = ServiceLifetime.SCOPED
) -> None:
    """
    Register a dependency in the default container.
    """
    default_container.register(interface, provider, lifetime)


def get_dependency_config[T](interface: type[T]) -> DependencyConfig[T] | None:
    """
    Get the configuration for a dependency from the default container.
    """
    return default_container.get_config(interface)


def add_transient[T](interface: type[T], provider: Callable[..., T]) -> None:
    """
    Register a transient dependency.
    """
    register_dependency(interface, provider, ServiceLifetime.TRANSIENT)


def add_scoped[T](interface: type[T], provider: Callable[..., T]) -> None:
    """
    Register a scoped dependency.
    """
    register_dependency(interface, provider, ServiceLifetime.SCOPED)


def add_singleton[T](interface: type[T], provider: Callable[..., T]) -> None:
    """
    Register a singleton dependency.
    """
    register_dependency(interface, provider, ServiceLifetime.SINGLETON)
