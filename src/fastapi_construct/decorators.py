import inspect
import re
import warnings
from collections.abc import Callable
from typing import Any, TypeVar, Unpack, get_args, get_origin

from fastapi import APIRouter, Depends, Response
from fastapi.responses import (
    FileResponse,
    HTMLResponse,
    JSONResponse,
    PlainTextResponse,
    RedirectResponse,
    StreamingResponse,
)
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
                _register_route(router, name, method, get_instance, controller_class=cls)

        return cls

    return decorator


def _create_get_instance[T](cls: type[T]) -> Callable[..., T]:
    """Helper to create the get_instance dependency factory."""
    if "__init__" in cls.__dict__:

        def get_instance(**kwargs) -> T: # type: ignore
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


def _register_route(router: APIRouter, name: str, method: Callable[..., Any], get_instance: Callable[..., Any], controller_class: type | None = None):
    """Helper to register a single route with automatic inference of metadata."""
    metadata = method._route_metadata.copy()  # type: ignore
    sig = inspect.signature(method)
    return_annotation = sig.return_annotation

    # 1. Validate response_model consistency if explicitly set
    _validate_response_model_consistency(method, metadata)

    # 2. Infer response_model from return annotation if not explicitly set
    if "response_model" not in metadata and return_annotation is not inspect.Signature.empty:
        if _contains_response(return_annotation):
            # If return type contains Response, disable response_model
            metadata["response_model"] = None
        else:
            # Otherwise, use the return annotation as response_model
            metadata["response_model"] = return_annotation

    # 3. Infer response_class from return type if not explicitly set
    # Only infer if response_model is not disabled (i.e., not None)
    if (
        "response_class" not in metadata
        and return_annotation is not inspect.Signature.empty
        and metadata.get("response_model") is not None
    ):
        response_class = _get_response_class_from_type(return_annotation)
        if response_class:
            metadata["response_class"] = response_class

    # 4. Infer summary and description from docstring if not explicitly set
    if "summary" not in metadata or "description" not in metadata:
        summary, description = _parse_docstring(method)
        if "summary" not in metadata and summary:
            metadata["summary"] = summary
        if "description" not in metadata and description:
            metadata["description"] = description

    # 5. Infer status_code based on HTTP method and return type if not explicitly set
    method_verb = metadata.get("method", "GET")
    if "status_code" not in metadata:
        inferred_status = _infer_status_code(method_verb, return_annotation)
        if inferred_status:
            metadata["status_code"] = inferred_status

    # 6. Generate operation_id if not explicitly set
    if "operation_id" not in metadata and controller_class:
        metadata["operation_id"] = _generate_operation_id(controller_class.__name__, name)

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
    """Helper to check if a type is or contains any Response class."""
    # Check if it's any Response class
    try:
        if isinstance(type_hint, type) and issubclass(
            type_hint,
            (
                Response,
                StarletteResponse,
                HTMLResponse,
                JSONResponse,
                PlainTextResponse,
                RedirectResponse,
                FileResponse,
                StreamingResponse,
            ),
        ):
            return True
    except TypeError:
        # Handle cases where issubclass can't be used
        pass

    # Handle Union, Optional, etc.
    origin = getattr(type_hint, "__origin__", None)
    if origin:
        args = getattr(type_hint, "__args__", ())
        return any(_contains_response(arg) for arg in args)
    return False


def _get_response_class_from_type(type_hint: Any) -> type[Response] | None:
    """
    Extract response class from type annotation if it's a Response subclass.

    Note: This function is currently not used because Response classes
    should have response_model=None, which is handled by _contains_response().
    Keeping for potential future use.
    """
    # Check if it's a direct Response subclass
    if isinstance(type_hint, type) and issubclass(
        type_hint, (Response, StarletteResponse, HTMLResponse, JSONResponse, PlainTextResponse, RedirectResponse, FileResponse, StreamingResponse)
    ):
        return type_hint

    # Handle Union types - check if all non-None types are the same Response class
    origin = get_origin(type_hint)
    if origin is not None:
        args = get_args(type_hint)
        response_classes = [
            arg for arg in args
            if isinstance(arg, type) and issubclass(
                arg, (Response, StarletteResponse, HTMLResponse, JSONResponse, PlainTextResponse, RedirectResponse, FileResponse, StreamingResponse)
            )
        ]
        if len(response_classes) == 1:
            return response_classes[0]

    return None


def _parse_docstring(func: Callable) -> tuple[str | None, str | None]:
    """
    Parse a function's docstring to extract summary and description.

    Returns:
        tuple: (summary, description) where summary is the first line and description is the rest
    """
    if not func.__doc__:
        return None, None

    lines = func.__doc__.strip().split("\n")
    if not lines:
        return None, None

    # First non-empty line is the summary
    summary = lines[0].strip()

    # Rest is the description (skip empty lines at the beginning)
    description_lines = []
    for line in lines[1:]:
        stripped = line.strip()
        if stripped or description_lines:  # Start collecting after first non-empty line
            description_lines.append(stripped)

    description = "\n".join(description_lines).strip() if description_lines else None

    return summary or None, description or None


def _infer_status_code(method_verb: str, return_annotation: Any) -> int | None:
    """
    Infer the appropriate status code based on HTTP method and return type.

    Returns None if no inference can be made (use FastAPI default).
    """
    # For POST, infer 201 if it returns something
    if method_verb == "POST" and return_annotation is not inspect.Signature.empty and return_annotation is not None:
        return 201

    # For DELETE, infer 204 if it returns None or has no return annotation
    if method_verb == "DELETE":
        if return_annotation is None or return_annotation is type(None):
            return 204
        # Check for Optional[None] or None in Union
        origin = get_origin(return_annotation)
        if origin is not None:
            args = get_args(return_annotation)
            # If all args are None, it's effectively None
            if all(arg is type(None) for arg in args):
                return 204

    return None


def _validate_response_model_consistency(method: Callable, metadata: dict) -> None:
    """
    Validate that explicit response_model is consistent with return type annotation.

    Emits a warning if there's an inconsistency.
    """
    if "response_model" not in metadata:
        return

    explicit_model = metadata["response_model"]
    return_annotation = inspect.signature(method).return_annotation

    # Skip validation if no return annotation or if response_model is None
    if return_annotation is inspect.Signature.empty or explicit_model is None:
        return

    # Skip if return annotation contains Response (handled separately)
    if _contains_response(return_annotation):
        return

    # Check for inconsistency
    if explicit_model != return_annotation:
        warnings.warn(
            f"Inconsistent response_model in {method.__name__}: "
            f"explicit response_model={explicit_model.__name__ if hasattr(explicit_model, '__name__') else explicit_model} "
            f"but return annotation is {return_annotation.__name__ if hasattr(return_annotation, '__name__') else return_annotation}. "
            f"The explicit response_model will be used.",
            UserWarning,
            stacklevel=4,
        )


def _generate_operation_id(controller_name: str, method_name: str) -> str:
    """
    Generate a unique operation ID from controller and method names.

    Example: UserController.get_user -> "user_get_user"
    """
    # Remove "Controller" suffix if present
    clean_controller = controller_name.replace("Controller", "")

    # Convert CamelCase to snake_case
    clean_controller = re.sub(r"(?<!^)(?=[A-Z])", "_", clean_controller).lower()

    return f"{clean_controller}_{method_name}"


inject = autowire_callable
