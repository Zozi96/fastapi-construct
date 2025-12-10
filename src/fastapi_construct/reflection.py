import inspect
from collections.abc import Callable
from contextlib import suppress
from typing import Any

from fastapi import Depends

from .container import default_container, get_dependency_config
from .enums import ServiceLifetime
from .exceptions import CaptiveDependencyError, InterfaceMismatchError


def autowire_callable[F: Callable[..., Any]](func: F, owner_lifetime: ServiceLifetime | None = None) -> F:
    """
    Inspects the signature of a callable and injects FastAPI dependencies based on type hints.

    This function iterates through the parameters of the given callable. If a parameter has a type annotation
    that corresponds to a registered dependency configuration (retrieved via `get_dependency_config`),
    it replaces the parameter's default value with a FastAPI `Depends` instance pointing to the configured provider.

    The `use_cache` argument for `Depends` is determined by the service lifetime:
    - `True` for Singleton or Scoped lifetimes.
    - `False` for Transient lifetimes.

    Args:
        func (Callable): The callable object (function or method) to inspect and modify.
        owner_lifetime (ServiceLifetime, optional): The lifetime of the service that owns this callable.
            Used to validate dependency injection rules (e.g., preventing Scoped in Singleton).

    Returns:
        Callable: The same callable object with its `__signature__` attribute modified to include
        FastAPI dependency injections.

    Raises:
        InterfaceMismatchError: If a parameter has a type annotation that cannot be resolved as a dependency,
                   with helpful suggestions on how to fix it.
        CaptiveDependencyError: If a Scoped dependency is injected into a Singleton service.
    """
    sig: inspect.Signature = inspect.signature(func)
    new_params = []
    unresolved_params = []

    for param in sig.parameters.values():
        if param.name == "self":
            new_params.append(param)
            continue

        if param.annotation != inspect.Parameter.empty and param.default == inspect.Parameter.empty:
            config = get_dependency_config(param.annotation)

            if config:
                # Validate Scoped in Singleton
                if owner_lifetime == ServiceLifetime.SINGLETON and config.lifetime == ServiceLifetime.SCOPED:
                    func_name = getattr(func, "__qualname__", getattr(func, "__name__", str(func)))
                    param_type_name = getattr(param.annotation, "__name__", str(param.annotation))
                    raise CaptiveDependencyError(
                        f"Cannot inject Scoped dependency '{param_type_name}' into Singleton service '{func_name}'.\n"
                        "This would cause the Scoped dependency to be held for the lifetime of the application (Captive Dependency).\n"
                        "Solutions:\n"
                        "1. Change the Singleton service to be Scoped.\n"
                        "2. Change the dependency to be Singleton (if stateless).\n"
                        "3. Inject a factory or provider instead of the direct dependency."
                    )

                if config.lifetime == ServiceLifetime.SINGLETON:
                    # For Singletons, we need a proxy that checks the container for an existing instance
                    # because FastAPI's use_cache=True is only request-scoped.
                    proxy = _create_singleton_proxy(config.provider, param.annotation)
                    new_params.append(param.replace(default=Depends(proxy, use_cache=False)))
                else:
                    use_cache = config.lifetime != ServiceLifetime.TRANSIENT
                    # Wrap provider to support async initialization (on_startup)
                    wrapper = _create_async_wrapper(config.provider)
                    new_params.append(param.replace(default=Depends(wrapper, use_cache=use_cache)))
                continue

            # Check if this type is registered under a different interface
            possible_interface = _find_registered_interface(param.annotation)
            if possible_interface:
                unresolved_params.append((param, possible_interface))

        new_params.append(param)

    # If there are unresolved parameters that have a registered interface, raise a helpful error
    if unresolved_params:
        func_name = getattr(func, "__qualname__", getattr(func, "__name__", str(func)))
        error_parts = [f"Cannot autowire dependencies for {func_name}. The following parameters cannot be resolved:\n"]

        for param, interface in unresolved_params:
            param_type_name = getattr(param.annotation, "__name__", str(param.annotation))
            interface_name = getattr(interface, "__name__", str(interface))
            error_parts.append(
                f"  • Parameter '{param.name}' with type '{param_type_name}'\n"
                f"    → This type is registered as '{interface_name}' in the container.\n"
                f"    → Change the type annotation from '{param_type_name}' to '{interface_name}'\n"
            )

        error_parts.append(
            "\nRemember: When using @injectable(InterfaceType, ...), you must inject the interface type, "
            "not the implementation type. This follows the Dependency Inversion Principle."
        )

        raise InterfaceMismatchError("".join(error_parts))

    func.__signature__ = sig.replace(parameters=new_params)  # type: ignore
    return func


def _find_registered_interface(implementation: type[Any]) -> type[Any] | None:
    """
    Check if the given implementation type is registered in the container under a different interface.

    Returns the interface type if found, None otherwise.
    """
    # Iterate through all registered dependencies to find if this implementation is registered
    for registered_type in default_container._registry:
        config = get_dependency_config(registered_type)
        if config and inspect.isclass(config.provider):
            # Check if the provider is the same as or a subclass of the implementation
            if config.provider == implementation or (
                inspect.isclass(implementation) and issubclass(implementation, config.provider)
            ):
                return registered_type
            # Also check if implementation is the provider itself
            if implementation == config.provider:
                return registered_type

    return None


def _create_singleton_proxy(provider: Callable[..., Any], interface: type[Any]) -> Callable[..., Any]:
    """
    Creates a proxy function for Singleton dependencies.

    This proxy checks the container for an existing instance before creating a new one.
    It mimics the signature of the provider so FastAPI can inject dependencies into it.
    """

    async def proxy(**kwargs):
        # Fast check without lock
        instance = default_container.get_singleton(interface)
        if instance is not None:
            return instance

        # Acquire lock and check again (Double-Checked Locking)
        # We access the lock directly from the container to ensure process-wide safety
        with default_container._lock:
            instance = default_container.get_singleton(interface)
            if instance is not None:
                return instance

            instance = provider(**kwargs)
            await default_container._run_startup_hooks(instance)
            default_container.set_singleton(interface, instance)
            return instance

    _copy_signature(provider, proxy)
    return proxy


def _create_async_wrapper(provider: Callable[..., Any]) -> Callable[..., Any]:
    """
    Creates a wrapper function to support async initialization (on_startup).
    Handles AsyncGenerators by yielding the value and ensuring cleanup.
    """
    if inspect.isasyncgenfunction(provider):

        async def wrapper(**kwargs):
            gen = provider(**kwargs)
            try:
                instance = await anext(gen)
                await default_container._run_startup_hooks(instance)
                yield instance
            finally:
                try:
                    await anext(gen)
                except StopAsyncIteration:
                    pass
                except Exception:
                    # If an error occurs during cleanup, we still want to ensure aclose is called
                    # but we also want to propagate the error if appropriate.
                    # FastAPI usually suppresses errors during cleanup or logs them?
                    # For now let's just re-raise.
                    raise
                finally:
                    await gen.aclose()

    else:

        async def wrapper(**kwargs):
            instance = provider(**kwargs)
            await default_container._run_startup_hooks(instance)
            return instance

    _copy_signature(provider, wrapper)
    return wrapper


def _copy_signature(source: Callable, target: Callable) -> None:
    """Helper to copy signature from source to target."""
    with suppress(AttributeError):
        target.__signature__ = inspect.signature(source)


def resolve_dependency_for_param(annotation: Any) -> Any:
    """
    Resolves the FastAPI dependency for a given type annotation based on registered configurations.

    This function checks if a dependency configuration exists for the provided annotation.
    If a configuration is found, it returns a FastAPI `Depends` object configured with the
    appropriate provider and cache setting (based on the service lifetime). If no configuration
    is found, the original annotation is returned as is.

    Args:
        annotation (Any): The type annotation to resolve a dependency for.

    Returns:
        Any: A FastAPI `Depends` object if a configuration exists, otherwise the original annotation.
    """
    config = get_dependency_config(annotation)
    if config:
        if config.lifetime == ServiceLifetime.SINGLETON:
            proxy = _create_singleton_proxy(config.provider, annotation)
            return Depends(proxy, use_cache=False)

        use_cache = config.lifetime != ServiceLifetime.TRANSIENT
        wrapper = _create_async_wrapper(config.provider)
        return Depends(wrapper, use_cache=use_cache)
    return annotation
