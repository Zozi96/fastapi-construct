from collections.abc import Callable
from typing import Unpack

from .types import APIMethodArgs


def route(path: str, method: str, **kwargs: Unpack[APIMethodArgs]) -> Callable:
    """
    Decorator to register a method as a FastAPI route within a controller.

    This decorator attaches route metadata to the function, which is later processed
    by the `Controller` to register the actual path operation with the FastAPI application.

    Args:
        path (str): The URL path for the route (e.g., "/items/{item_id}").
        method (str): The HTTP method for the route (e.g., "GET", "POST", "PUT").
        **kwargs (Unpack[APIMethodArgs]): Additional keyword arguments supported by
            FastAPI's path operation decorators (e.g., `response_model`, `status_code`,
            `tags`, `dependencies`, etc.).

    Returns:
        Callable: A decorator that modifies the target function by attaching a
        `_route_metadata` attribute containing the route configuration.
    """

    def decorator(func: Callable) -> Callable:
        func._route_metadata = {  # type: ignore
            "path": path,
            "method": method,
            **kwargs,
        }
        return func

    return decorator


def get(path: str, **kwargs: Unpack[APIMethodArgs]) -> Callable:
    """
    Register a GET route.

    Args:
        path (str): The URL path for the route.
        **kwargs (Unpack[APIMethodArgs]): Additional arguments passed to the underlying router
            (e.g., response_model, status_code, dependencies, etc.).

    Returns:
        Callable: A decorator that registers the decorated function as a GET route handler.
    """
    return route(path, "GET", **kwargs)


def post(path: str, **kwargs: Unpack[APIMethodArgs]) -> Callable:
    """
    Register a POST route.

    Args:
        path (str): The URL path for the route.
        **kwargs (Unpack[APIMethodArgs]): Additional arguments passed to the underlying router
            (e.g., response_model, status_code, dependencies, etc.).

    Returns:
        Callable: A decorator that registers the decorated function as a POST route handler.
    """
    return route(path, "POST", **kwargs)


def put(path: str, **kwargs: Unpack[APIMethodArgs]) -> Callable:
    """
    Register a PUT route.

    Args:
        path (str): The URL path for the route.
        **kwargs (Unpack[APIMethodArgs]): Additional arguments passed to the underlying router decorator
            (e.g., response_model, status_code, dependencies, etc.).

    Returns:
        Callable: A decorator that registers the decorated function as a PUT route handler.
    """
    return route(path, "PUT", **kwargs)


def delete(path: str, **kwargs: Unpack[APIMethodArgs]) -> Callable:
    """
    Register a DELETE route.

    Args:
        path (str): The URL path for the route.
        **kwargs (Unpack[APIMethodArgs]): Additional arguments passed to the underlying router
            (e.g., response_model, status_code, dependencies, etc.).

    Returns:
        Callable: A decorator that registers the decorated function as a DELETE route handler.
    """
    return route(path, "DELETE", **kwargs)


def patch(path: str, **kwargs: Unpack[APIMethodArgs]) -> Callable:
    """
    Register a route with the PATCH HTTP method.

    Args:
        path (str): The URL path for the route.
        **kwargs (Unpack[APIMethodArgs]): Additional arguments passed to the underlying router
            (e.g., response_model, status_code, dependencies, etc.).

    Returns:
        Callable: A decorator that registers the decorated function as a PATCH route handler.
    """
    return route(path, "PATCH", **kwargs)
