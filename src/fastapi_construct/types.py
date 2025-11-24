from typing import Any, TypedDict, Sequence, Callable
from enum import Enum
from fastapi import Response, params
from fastapi.routing import APIRoute
from starlette.types import ASGIApp, Lifespan
from starlette.routing import BaseRoute

type IncEx = set[int] | set[str] | dict[int, Any] | dict[str, Any] | None


class APIRouterArgs(TypedDict, total=False):
    """Arguments for APIRouter."""

    prefix: str
    tags: list[str | Enum] | None
    dependencies: Sequence[params.Depends] | None
    default_response_class: type[Response]
    responses: dict[int | str, dict[str, Any]] | None
    callbacks: list[BaseRoute] | None
    routes: list[BaseRoute] | None
    redirect_slashes: bool
    default: ASGIApp | None
    dependency_overrides_provider: Any | None
    route_class: type[APIRoute]
    on_startup: Sequence[Callable[[], Any]] | None
    on_shutdown: Sequence[Callable[[], Any]] | None
    lifespan: Lifespan[Any] | None
    deprecated: bool | None
    include_in_schema: bool
    generate_unique_id_function: Callable[[APIRoute], str]


class APIMethodArgs(TypedDict, total=False):
    """Arguments for API methods."""

    response_model: Any
    status_code: int | None
    tags: list[str | Enum] | None
    dependencies: Sequence[params.Depends] | None
    summary: str | None
    description: str | None
    response_description: str
    responses: dict[int | str, dict[str, Any]] | None
    deprecated: bool | None
    operation_id: str | None
    response_model_include: IncEx
    response_model_exclude: IncEx
    response_model_by_alias: bool
    response_model_exclude_unset: bool
    response_model_exclude_defaults: bool
    response_model_exclude_none: bool
    include_in_schema: bool
    response_class: type[Response]
    name: str | None
    callbacks: list[BaseRoute] | None
    openapi_extra: dict[str, Any] | None
    generate_unique_id_function: Callable[[APIRoute], str]
