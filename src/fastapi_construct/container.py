import inspect
import threading
from collections.abc import Callable, Generator
from contextlib import contextmanager
from contextvars import ContextVar
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
        # Use frozenset as default to avoid shared mutable state issues
        self._resolving_ctx: ContextVar[set[type]] = ContextVar("resolving", default=frozenset())
        self._singletons: dict[type, Any] = {}
        self._lock = threading.Lock()
        self._scope_ctx: ContextVar[dict[type, Any] | None] = ContextVar("scope_ctx", default=None)
        self._initialized_services: set[int] = set()  # Track initialized instances by id

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
        Resolves a dependency recursively (Synchronous).

        Args:
            interface: The interface or type to resolve.

        Returns:
            The resolved instance.

        Raises:
            DependencyNotFoundError: If the dependency is not registered.
            CircularDependencyError: If a circular dependency is detected.
        """
        return self._resolve_impl(interface)

    async def resolve_async[T](self, interface: type[T]) -> T:
        """
        Resolves a dependency recursively (Asynchronous).
        Waits for on_startup hooks if present.

        Args:
            interface: The interface or type to resolve.

        Returns:
            The resolved instance.
        """
        instance = self._resolve_impl(interface)
        await self._run_startup_hooks(instance)
        return instance

    def _resolve_impl[T](self, interface: type[T]) -> T:
        resolving = self._resolving_ctx.get()
        if interface in resolving:
            raise CircularDependencyError(f"Circular dependency detected for {interface}")

        config = self.get_config(interface)
        if not config:
            raise DependencyNotFoundError(f"No provider registered for {interface}")

        # Singleton Resolution (Thread-Safe)
        if config.lifetime == ServiceLifetime.SINGLETON:
            return self._resolve_singleton(config, interface)

        # Scoped Resolution
        if config.lifetime == ServiceLifetime.SCOPED:
            return self._resolve_scoped(config, interface)

        # Transient Resolution
        return self._create_instance(config, interface)

    def _resolve_singleton[T](self, config: DependencyConfig[T], interface: type[T]) -> T:
        # Double-checked locking optimization
        if interface in self._singletons:
            return self._singletons[interface]  # type: ignore

        with self._lock:
            if interface in self._singletons:
                return self._singletons[interface]  # type: ignore

            instance = self._create_instance(config, interface)
            self._singletons[interface] = instance
            return instance

    def _resolve_scoped[T](self, config: DependencyConfig[T], interface: type[T]) -> T:
        scope = self._scope_ctx.get()
        if scope is not None:
            if interface in scope:
                return scope[interface]

            instance = self._create_instance(config, interface)
            scope[interface] = instance
            return instance

        # If no manual scope, fall back to creating a new instance (Transient-like behavior outside scope)
        return self._create_instance(config, interface)

    def _create_instance[T](self, config: DependencyConfig[T], interface: type[T]) -> T:
        resolving = self._resolving_ctx.get()
        new_resolving = set(resolving)
        new_resolving.add(interface)
        token = self._resolving_ctx.set(new_resolving)

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

            return provider(**kwargs)
        finally:
            self._resolving_ctx.reset(token)

    async def _run_startup_hooks(self, instance: Any) -> None:
        """
        Runs the on_startup hook if present and not already run.
        """
        if instance is None:
            return

        instance_id = id(instance)
        if instance_id in self._initialized_services:
            return

        if hasattr(instance, "on_startup"):
            startup_method = instance.on_startup
            if callable(startup_method):
                if inspect.iscoroutinefunction(startup_method):
                    await startup_method()
                else:
                    startup_method()

        self._initialized_services.add(instance_id)

    @contextmanager
    def scope(self) -> Generator[None, None, None]:
        """
        Context manager to create a manual scope for resolving SCOPED dependencies.
        Useful for background tasks or scripts.
        """
        token = self._scope_ctx.set({})
        try:
            yield
        finally:
            self._scope_ctx.reset(token)

    def reset(self) -> None:
        """
        Reset the container state, clearing all singletons and registry.
        Useful for testing.
        """
        self._registry.clear()
        # self._resolving_ctx is context local, no need to reset
        self._singletons.clear()
        self._initialized_services.clear()

    def get_singleton[T](self, interface: type[T]) -> T | None:
        """
        Retrieve a singleton instance if it exists.
        """
        return self._singletons.get(interface)

    def set_singleton[T](self, interface: type[T], instance: T) -> None:
        """
        Register a singleton instance.
        """
        with self._lock:
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
