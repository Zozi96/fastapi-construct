import inspect
from collections.abc import Callable
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
                    new_params.append(param.replace(default=Depends(config.provider, use_cache=use_cache)))
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

    def proxy(**kwargs):
        instance = default_container.get_singleton(interface)
        if instance is not None:
            return instance

        instance = provider(**kwargs)
        default_container.set_singleton(interface, instance)
        return instance

    # Copy signature from provider
    if inspect.isclass(provider):
        init_sig = inspect.signature(provider.__init__)
        # Remove self
        params = [p for n, p in init_sig.parameters.items() if n != "self"]
        proxy.__signature__ = init_sig.replace(parameters=params)  # type: ignore
    else:
        proxy.__signature__ = inspect.signature(provider)  # type: ignore

    return proxy


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
        use_cache = config.lifetime != ServiceLifetime.TRANSIENT
        return Depends(config.provider, use_cache=use_cache)
    return annotation
