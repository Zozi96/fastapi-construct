import inspect
from collections.abc import Callable
from typing import Any, TypeVar, Unpack

from fastapi import APIRouter, Depends, Response
from starlette.responses import Response as StarletteResponse

from .container import register_dependency
from .enums import ServiceLifetime
from .reflection import autowire_callable
from .types import APIRouterArgs


T = TypeVar("T")


def injectable(
    interface: type[Any] | ServiceLifetime | None = None,
    lifetime: ServiceLifetime = ServiceLifetime.SCOPED,
):
    """
    Decorator to register a class as an injectable dependency.

    This decorator registers the decorated class as an implementation of the specified
    interface within the dependency injection container. It also automatically inspects
    the class's `__init__` method to autowire its own dependencies.

    Args:
        interface (Type[T] | ServiceLifetime | None): The interface or base class that the
            decorated class implements. If None, the class itself is used as the interface.
            If a ServiceLifetime is passed, it is treated as the lifetime argument, and
            the class itself is used as the interface.
        lifetime (ServiceLifetime, optional): The lifetime of the service (e.g., SINGLETON,
            SCOPED, TRANSIENT). Defaults to ServiceLifetime.SCOPED.

    Returns:
        Callable[[Type[T]], Type[T]]: A decorator function that returns the original class
        after registering it.
    """
    # Handle case where decorator is called with just lifetime as first arg
    # e.g. @injectable(ServiceLifetime.SINGLETON)
    if isinstance(interface, ServiceLifetime):
        lifetime = interface
        interface = None

    def decorator(cls: type[T]) -> type[T]:
        """
        Registers a class as a dependency for the specified interface and autowires its constructor.

        This decorator performs two main actions:
        1. Registers the decorated class in the dependency injection container, binding it to the provided `interface` with the specified `lifetime`.
        2. Inspects the class's `__init__` method and sets up autowiring for its parameters.

        Args:
            cls (Type[T]): The class to be decorated and registered.

        Returns:
            Type[T]: The original class, unmodified but registered and configured for autowiring.
        """
        register_interface = interface if interface is not None else cls
        register_dependency(register_interface, cls, lifetime)

        # Only autowire if __init__ is defined in the class (not inherited from object)
        if "__init__" in cls.__dict__:
            autowire_callable(cls.__init__)

        return cls

    return decorator


def controller(router: APIRouter | None = None, **kwargs: Unpack[APIRouterArgs]) -> Callable[[type[T]], type[T]]:
    """
    Decorator factory that converts a class into a FastAPI-style controller.

    This decorator either creates a new APIRouter (using provided kwargs) or
    attaches and augments an existing APIRouter and then registers class methods
    marked with routing metadata as FastAPI endpoints. The decorated class will
    gain a `router` attribute referencing the APIRouter used.

    Parameters
    - router (APIRouter | None): Optional router to attach to the class. If None,
        a new APIRouter is created with the provided kwargs.
    - **kwargs: Keyword arguments forwarded to APIRouter when creating a new router.
        When an existing router is supplied, the decorator will merge certain keys:
        - "prefix" (if present) will be appended to the router.prefix string.
        - "tags" (if present and non-empty) will be extended into router.tags.

    Behavior
    - Assigns or creates an APIRouter and stores it on the class as `cls.router`.
    - Calls autowire_callable(cls.__init__) to prepare the constructor for dependency
        injection/autowiring.
    - Builds a dependency factory get_instance whose signature mirrors the class
        __init__ so FastAPI can inject constructor parameters.
    - Iterates over all public functions of the class (skips names starting with "_").
    - For each method that has a `_route_metadata` attribute (a mapping expected to
        contain at least the keys "path" and "method"), registers an endpoint:
        - Wraps the method in an endpoint function that depends on get_instance
            (so every request gets a controller instance injected).
        - Preserves the original method's docstring and name on the wrapper.
        - Replaces the wrapper's signature so FastAPI can extract request parameters
            from the original method (skipping `self`) and includes the controller
            dependency as a keyword-only parameter.
        - Supports both coroutine and regular methods (awaits coroutines).
        - Calls router.add_api_route(path, endpoint_wrapper, methods=[method_verb], **metadata)
            to register the route.

    Return
    - A class decorator that returns the augmented class (with `router` attribute).
        The decorator has side effects (router creation/augmentation and route registration).

    Expectations / Requirements
    - Methods intended to be exposed must have a `_route_metadata` attribute that
        provides at least "path" and "method" (HTTP verb).
    - Private methods (names starting with "_") are ignored.
    - When a shared router instance is passed to multiple decorated classes,
        "prefix" and "tags" kwargs (when provided) will mutate the existing router
        (prefix is appended; tags are extended). Be cautious about mutation/ordering.

    Example
    - Typical usage:
            @controller(prefix="/items", tags=["items"])
            class ItemController:
                    def __init__(self, service: ItemService): ...
                    def list(self): ...
                    # methods must be annotated with `_route_metadata` elsewhere
    """

    def decorator(cls: type[T]) -> type[T]:
        nonlocal router
        if router is None:
            router = APIRouter(**kwargs)
        else:
            if "prefix" in kwargs:
                router.prefix += kwargs["prefix"]  # type: ignore
            if kwargs.get("tags"):
                router.tags.extend(kwargs["tags"])  # type: ignore

        cls.router = router  # type: ignore

        # Only autowire if __init__ is defined in the class (not inherited from object)
        if "__init__" in cls.__dict__:
            autowire_callable(cls.__init__)

        get_instance = _create_get_instance(cls)

        members = inspect.getmembers(cls, predicate=inspect.isfunction)
        # Sort by definition order (line number) to ensure routes are registered in the correct order
        members.sort(key=lambda x: x[1].__code__.co_firstlineno)

        for name, method in members:
            if name.startswith("_"):
                continue

            if hasattr(method, "_route_metadata"):
                _register_route(router, name, method, get_instance)

        return cls

    return decorator


def _create_get_instance[T](cls: type[T]) -> Callable[..., T]:
    """Helper to create the get_instance dependency factory."""
    if "__init__" in cls.__dict__:

        def get_instance(**kwargs):
            return cls(**kwargs)

        # Set signature for get_instance, excluding 'self' parameter and variadic args
        init_sig = inspect.signature(cls.__init__)
        init_params = [
            p
            for n, p in init_sig.parameters.items()
            if n != "self" and p.kind not in {inspect.Parameter.VAR_POSITIONAL, inspect.Parameter.VAR_KEYWORD}
        ]
        get_instance.__signature__ = init_sig.replace(parameters=init_params)  # type: ignore
        return get_instance

    def get_instance():
        return cls()

    return get_instance


def _register_route(router: APIRouter, name: str, method: Callable[..., Any], get_instance: Callable[..., Any]):
    """Helper to register a single route."""
    metadata = method._route_metadata.copy()  # type: ignore

    # Check if return annotation contains Response and response_model is not set
    if "response_model" not in metadata:
        return_annotation = inspect.signature(method).return_annotation
        if return_annotation is not inspect.Signature.empty and _contains_response(return_annotation):
            metadata["response_model"] = None

    # Create a factory function to capture the current method name in the closure
    def make_endpoint(method_name: str):
        async def endpoint_wrapper(
            **endpoint_kwargs,
        ):
            # Get controller instance from Depends
            _controller_instance = endpoint_kwargs.pop("_controller_instance")
            method_to_call = getattr(_controller_instance, method_name)
            if inspect.iscoroutinefunction(method_to_call):
                return await method_to_call(**endpoint_kwargs)
            return method_to_call(**endpoint_kwargs)

        return endpoint_wrapper

    endpoint_wrapper = make_endpoint(name)
    endpoint_wrapper.__name__ = name
    endpoint_wrapper.__doc__ = method.__doc__

    sig = inspect.signature(method)
    # Skip 'self' parameter
    params_list = list(sig.parameters.items())
    params = [p for n, p in params_list if n != "self"]

    # Add controller instance parameter with include_in_schema=False
    controller_param = inspect.Parameter(
        "_controller_instance",
        inspect.Parameter.KEYWORD_ONLY,
        default=Depends(get_instance),
    )

    # Set signature with method params + hidden controller instance
    endpoint_wrapper.__signature__ = sig.replace(parameters=[*params, controller_param])

    path = metadata.pop("path")
    method_verb = metadata.pop("method")

    router.add_api_route(path, endpoint_wrapper, methods=[method_verb], **metadata)


def _contains_response(type_hint: Any) -> bool:
    """Helper to check if a type is or contains Response."""
    if type_hint is Response or type_hint is StarletteResponse:
        return True
    # Handle Union, Optional, etc.
    origin = getattr(type_hint, "__origin__", None)
    if origin:
        args = getattr(type_hint, "__args__", ())
        return any(_contains_response(arg) for arg in args)
    return False


inject = autowire_callable
