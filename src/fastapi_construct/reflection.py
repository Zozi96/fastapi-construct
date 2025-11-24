import inspect
from collections.abc import Callable
from typing import Any

from fastapi import Depends

from .container import get_dependency_config
from .enums import ServiceLifetime


def autowire_callable(func: Callable) -> Callable:
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
                use_cache = config.lifetime != ServiceLifetime.TRANSIENT
                new_params.append(param.replace(default=Depends(config.provider, use_cache=use_cache)))
                continue

        new_params.append(param)

    func.__signature__ = sig.replace(parameters=new_params)  # type: ignore
    return func


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
