import inspect
from typing import Any, TypeVar, Unpack

from fastapi import APIRouter, Depends

from .container import register_dependency
from .enums import ServiceLifetime
from .reflection import autowire_callable
from .types import APIRouterArgs


T = TypeVar("T")


def injectable[T](interface: type[T], lifetime: ServiceLifetime = ServiceLifetime.SCOPED):
    """
    Decorator to register a class as an injectable dependency.

    This decorator registers the decorated class as an implementation of the specified
    interface within the dependency injection container. It also automatically inspects
    the class's `__init__` method to autowire its own dependencies.

    Args:
        interface (Type[T]): The interface or base class that the decorated class implements.
            This is the type used when requesting the dependency.
        lifetime (ServiceLifetime, optional): The lifetime of the service (e.g., SINGLETON,
            SCOPED, TRANSIENT). Defaults to ServiceLifetime.SCOPED.

    Returns:
        Callable[[Type[T]], Type[T]]: A decorator function that returns the original class
        after registering it.
    """

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
        register_dependency(interface, cls, lifetime)
        autowire_callable(cls.__init__)
        return cls

    return decorator


def controller(router: APIRouter | None = None, **kwargs: Unpack[APIRouterArgs]) -> Any:
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

    def decorator(cls: type[Any]) -> type[Any]:
        nonlocal router
        if router is None:
            router = APIRouter(**kwargs)
        else:
            if "prefix" in kwargs:
                router.prefix += kwargs["prefix"]  # type: ignore
            if kwargs.get("tags"):
                router.tags.extend(kwargs["tags"])  # type: ignore

        cls.router = router  # type: ignore
        autowire_callable(cls.__init__)

        def get_instance(**kwargs):
            return cls(**kwargs)

        get_instance.__signature__ = inspect.signature(cls.__init__)  # type: ignore

        for name, method in inspect.getmembers(cls, predicate=inspect.isfunction):
            if name.startswith("_"):
                continue

            if hasattr(method, "_route_metadata"):
                metadata = method._route_metadata  # type: ignore

                async def endpoint_wrapper(
                    _controller_instance: cls = Depends(get_instance),  # type: ignore  # noqa: B008
                    **endpoint_kwargs,
                ):
                    method_to_call = getattr(_controller_instance, name)  # noqa: B023
                    if inspect.iscoroutinefunction(method_to_call):
                        return await method_to_call(**endpoint_kwargs)
                    return method_to_call(**endpoint_kwargs)

                endpoint_wrapper.__name__ = name
                endpoint_wrapper.__doc__ = method.__doc__

                sig = inspect.signature(method)
                params = list(sig.parameters.values())[1:]  # Skip self

                endpoint_wrapper.__signature__ = sig.replace(
                    parameters=[
                        *params,
                        inspect.Parameter(
                            "_controller_instance", inspect.Parameter.KEYWORD_ONLY, default=Depends(get_instance)
                        ),
                    ]
                )

                path = metadata.pop("path")
                method_verb = metadata.pop("method")

                router.add_api_route(path, endpoint_wrapper, methods=[method_verb], **metadata)

        return cls

    return decorator
