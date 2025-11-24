import inspect
from functools import lru_cache
from typing import Any, Callable, Dict, Type, Optional

from .enums import ServiceLifetime


class DependencyConfig:
    def __init__(self, provider: Callable, lifetime: ServiceLifetime) -> None:
        self.provider = provider
        self.lifetime = lifetime


_dependency_registry: Dict[Type[Any], DependencyConfig] = {}


def _create_singleton_wrapper(cls: Type[Any]) -> Callable:
    @lru_cache(maxsize=1)
    def singleton_factory(*args, **kwargs):
        return cls(*args, **kwargs)

    old_sig = inspect.signature(cls.__init__)
    new_params = [p for name, p in old_sig.parameters.items() if name != "self"]
    singleton_factory.__signature__ = old_sig.replace(parameters=new_params)  # type: ignore

    return singleton_factory


def register_dependency(
    interface: Type[Any], provider: Callable, lifetime: ServiceLifetime = ServiceLifetime.SCOPED
) -> None:
    """
    Registers a dependency provider for a specific interface with a defined lifetime.

    This function maps an interface (usually an abstract base class or a type) to a
    concrete provider (a class or a factory function). It handles the logic for
    different service lifetimes, specifically wrapping class-based providers in a
    singleton wrapper if the lifetime is set to SINGLETON.

    Args:
        interface (Type[Any]): The type or interface to register. This is the key used
            for dependency injection resolution.
        provider (Callable): The callable responsible for creating the dependency instance.
            This can be a class or a factory function.
        lifetime (ServiceLifetime, optional): The scope of the dependency instance.
            Defaults to ServiceLifetime.SCOPED.

    Returns:
        None
    """
    final_provider = provider

    if lifetime == ServiceLifetime.SINGLETON and inspect.isclass(provider):
        final_provider = _create_singleton_wrapper(provider)

    _dependency_registry[interface] = DependencyConfig(final_provider, lifetime)


def get_dependency_config(interface: Type[Any]) -> Optional[DependencyConfig]:
    """
    Retrieves the dependency configuration for a given interface.

    Args:
        interface (Type[Any]): The interface or type for which to retrieve the configuration.

    Returns:
        Optional[DependencyConfig]: The configuration associated with the interface if found,
        otherwise None.
    """
    return _dependency_registry.get(interface)


def add_transient(interface: Type[Any], provider: Callable) -> None:
    """
    Registers a transient dependency.

    Transient services are created each time they are requested. This method
    registers a provider callable against an interface type with the
    TRANSIENT lifetime scope.

    Args:
        interface (Type[Any]): The abstract base class or type definition
            that identifies the dependency.
        provider (Callable): The factory function or class constructor
            responsible for creating the instance of the dependency.
    """
    register_dependency(interface, provider, ServiceLifetime.TRANSIENT)


def add_scoped(interface: Type[Any], provider: Callable) -> None:
    """
    Registers a dependency with a scoped lifetime.

    Scoped dependencies are created once per request (or scope).

    Args:
        interface (Type[Any]): The interface or type to register.
        provider (Callable): The callable (function or class) that provides the implementation.
    """
    register_dependency(interface, provider, ServiceLifetime.SCOPED)


def add_singleton(interface: Type[Any], provider: Callable) -> None:
    """
    Registers a singleton dependency.

    A singleton dependency is created once and shared across the entire application lifetime.
    Subsequent requests for this interface will receive the same instance.

    Args:
        interface (Type[Any]): The type or interface to register.
        provider (Callable): The callable (function or class) that provides the instance.
    """
    register_dependency(interface, provider, ServiceLifetime.SINGLETON)
