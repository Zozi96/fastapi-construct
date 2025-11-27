import inspect
from collections.abc import Callable
from typing import Any

from fastapi import Depends

from .container import default_container, get_dependency_config
from .enums import ServiceLifetime


def autowire_callable[F: Callable[..., Any]](func: F) -> F:
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

    Returns:
        Callable: The same callable object with its `__signature__` attribute modified to include
        FastAPI dependency injections.
    """
    sig: inspect.Signature = inspect.signature(func)
    new_params = []

    for param in sig.parameters.values():
        if param.name == "self":
            new_params.append(param)
            continue

        if param.annotation != inspect.Parameter.empty and param.default == inspect.Parameter.empty:
            config = get_dependency_config(param.annotation)

            if config:
                if config.lifetime == ServiceLifetime.SINGLETON:
                    # For Singletons, we need a proxy that checks the container for an existing instance
                    # because FastAPI's use_cache=True is only request-scoped.
                    proxy = _create_singleton_proxy(config.provider, param.annotation)
                    new_params.append(param.replace(default=Depends(proxy, use_cache=False)))
                else:
                    use_cache = config.lifetime != ServiceLifetime.TRANSIENT
                    new_params.append(param.replace(default=Depends(config.provider, use_cache=use_cache)))
                continue

        new_params.append(param)

    func.__signature__ = sig.replace(parameters=new_params)  # type: ignore
    return func


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
