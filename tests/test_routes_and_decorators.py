"""Tests for route decorators, controllers, and injectable services."""

from collections.abc import Generator
from typing import Any

import pytest
from fastapi import APIRouter

from fastapi_construct import container
from fastapi_construct.decorators import controller, injectable
from fastapi_construct.enums import ServiceLifetime
from fastapi_construct.routes import delete, get, patch, post, put


@pytest.fixture(autouse=True)
def clear_registry() -> Generator[None, Any, None]:
    """Clear the dependency registry before and after each test."""
    container._dependency_registry.clear()
    yield
    container._dependency_registry.clear()


class TestRouteDecorators:
    """Tests for HTTP method route decorators."""

    def test_get_decorator_attaches_metadata(self) -> None:
        """Test that @get decorator attaches correct metadata."""

        @get("/hello", tags=["t"])
        def handler() -> str:
            return "ok"

        assert hasattr(handler, "_route_metadata")
        assert handler._route_metadata["path"] == "/hello"
        assert handler._route_metadata["method"] == "GET"
        assert handler._route_metadata["tags"] == ["t"]

    def test_post_decorator_attaches_metadata(self) -> None:
        """Test that @post decorator attaches correct metadata."""

        @post("/create", status_code=201)
        def handler() -> dict:
            return {"created": True}

        assert hasattr(handler, "_route_metadata")
        assert handler._route_metadata["path"] == "/create"
        assert handler._route_metadata["method"] == "POST"
        assert handler._route_metadata["status_code"] == 201

    def test_put_decorator_attaches_metadata(self) -> None:
        """Test that @put decorator attaches correct metadata."""

        @put("/update/{item_id}")
        def handler(item_id: int) -> dict:
            return {"updated": item_id}

        assert hasattr(handler, "_route_metadata")
        assert handler._route_metadata["path"] == "/update/{item_id}"
        assert handler._route_metadata["method"] == "PUT"

    def test_delete_decorator_attaches_metadata(self) -> None:
        """Test that @delete decorator attaches correct metadata."""

        @delete("/remove/{item_id}")
        def handler(item_id: int) -> dict:
            return {"deleted": item_id}

        assert hasattr(handler, "_route_metadata")
        assert handler._route_metadata["path"] == "/remove/{item_id}"
        assert handler._route_metadata["method"] == "DELETE"

    def test_patch_decorator_attaches_metadata(self) -> None:
        """Test that @patch decorator attaches correct metadata."""

        @patch("/partial/{item_id}")
        def handler(item_id: int) -> dict:
            return {"patched": item_id}

        assert hasattr(handler, "_route_metadata")
        assert handler._route_metadata["path"] == "/partial/{item_id}"
        assert handler._route_metadata["method"] == "PATCH"

    def test_route_decorator_with_multiple_kwargs(self) -> None:
        """Test route decorator with multiple FastAPI kwargs."""

        @get(
            "/complex",
            tags=["api"],
            summary="Complex endpoint",
            description="A complex endpoint with metadata",
            response_description="Successful response",
        )
        def handler() -> dict:
            return {"status": "ok"}

        metadata = handler._route_metadata
        assert metadata["path"] == "/complex"
        assert metadata["method"] == "GET"
        assert metadata["tags"] == ["api"]
        assert metadata["summary"] == "Complex endpoint"
        assert metadata["description"] == "A complex endpoint with metadata"


class TestInjectableDecorator:
    """Tests for @injectable decorator."""

    def test_injectable_registers_and_autowires(self) -> None:
        """Test that @injectable registers service and autowires constructor."""

        class IDep:
            pass

        @injectable(IDep, lifetime=ServiceLifetime.SINGLETON)  # type: ignore
        class Impl:
            def __init__(self, x: int = 1) -> None:
                self.x = x

        cfg = container.get_dependency_config(IDep)
        assert cfg is not None
        assert cfg.lifetime == ServiceLifetime.SINGLETON
        assert callable(cfg.provider)

    def test_injectable_with_dependencies(self) -> None:
        """Test @injectable with constructor dependencies."""

        class IServiceA:
            pass

        class IServiceB:
            pass

        @injectable(IServiceA)  # type: ignore
        class ServiceA:
            def __init__(self) -> None:
                self.name = "ServiceA"

        @injectable(IServiceB)  # type: ignore
        class ServiceB:
            def __init__(self, service_a: IServiceA) -> None:
                self.service_a = service_a

        cfg_a = container.get_dependency_config(IServiceA)
        cfg_b = container.get_dependency_config(IServiceB)

        assert cfg_a is not None
        assert cfg_b is not None
        assert cfg_a.lifetime == ServiceLifetime.SCOPED  # Default
        assert cfg_b.lifetime == ServiceLifetime.SCOPED

    def test_injectable_different_lifetimes(self) -> None:
        """Test @injectable with different lifetimes."""

        class ITransient:
            pass

        class IScoped:
            pass

        class ISingleton:
            pass

        @injectable(ITransient, lifetime=ServiceLifetime.TRANSIENT)  # type: ignore
        class TransientService:
            def __init__(self) -> None:
                pass

        @injectable(IScoped, lifetime=ServiceLifetime.SCOPED)  # type: ignore
        class ScopedService:
            def __init__(self) -> None:
                pass

        @injectable(ISingleton, lifetime=ServiceLifetime.SINGLETON)  # type: ignore
        class SingletonService:
            def __init__(self) -> None:
                pass

        transient_cfg = container.get_dependency_config(ITransient)
        scoped_cfg = container.get_dependency_config(IScoped)
        singleton_cfg = container.get_dependency_config(ISingleton)

        assert transient_cfg is not None
        assert transient_cfg.lifetime == ServiceLifetime.TRANSIENT
        assert scoped_cfg is not None
        assert scoped_cfg.lifetime == ServiceLifetime.SCOPED
        assert singleton_cfg is not None
        assert singleton_cfg.lifetime == ServiceLifetime.SINGLETON


class TestControllerDecorator:
    """Tests for @controller decorator."""

    def test_controller_creates_router_and_registers_route(self) -> None:
        """Test that @controller creates router and registers routes."""

        @controller(prefix="/pfx", tags=["tag"])
        class TestController:
            def __init__(self) -> None:
                pass

            @get("/say")
            def say(self, who: str) -> str:
                return f"hi {who}"

        # Controller has router attribute
        assert hasattr(TestController, "router")
        routes_list = [r for r in TestController.router.routes if hasattr(r, "path")]
        assert any("/say" in getattr(r, "path", "") for r in routes_list)

    def test_controller_with_dependency_injection(self) -> None:
        """Test controller with dependency injection in constructor."""

        class IService:
            pass

        @injectable(IService)  # type: ignore
        class Service:
            def __init__(self) -> None:
                self.value = "test"

        @controller(prefix="/api")
        class TestController:
            def __init__(self, service: IService) -> None:
                self.service = service

            @get("/value")
            def get_value(self) -> str:
                return self.service.value # type: ignore

        assert hasattr(TestController, "router")

    def test_controller_multiple_routes(self) -> None:
        """Test controller with multiple HTTP methods."""

        @controller(prefix="/items")
        class ItemController:
            def __init__(self) -> None:
                self.items: dict[int, str] = {}

            @get("/{item_id}")
            def get_item(self, item_id: int) -> dict:
                return {"item_id": item_id}

            @post("/")
            def create_item(self, name: str) -> dict:
                return {"name": name, "created": True}

            @put("/{item_id}")
            def update_item(self, item_id: int, name: str) -> dict:
                return {"item_id": item_id, "name": name, "updated": True}

            @delete("/{item_id}")
            def delete_item(self, item_id: int) -> dict:
                return {"item_id": item_id, "deleted": True}

        routes = [r for r in ItemController.router.routes if hasattr(r, "path")]
        assert len(routes) >= 4

    def test_controller_with_existing_router(self) -> None:
        """Test controller with an existing APIRouter."""
        existing_router = APIRouter(prefix="/base", tags=["base"])

        @controller(router=existing_router, prefix="/extra", tags=["extra"])
        class TestController:
            def __init__(self) -> None:
                pass

            @get("/test")
            def test_route(self) -> str:
                return "ok"

        # Router should have combined prefix and tags
        assert TestController.router is existing_router
        assert "/extra" in existing_router.prefix
        assert "extra" in existing_router.tags

    def test_controller_async_methods(self) -> None:
        """Test controller with async methods."""

        @controller(prefix="/async")
        class AsyncController:
            def __init__(self) -> None:
                pass

            @get("/endpoint")
            async def async_endpoint(self) -> dict:
                return {"async": True}

        assert hasattr(AsyncController, "router")
        routes = [r for r in AsyncController.router.routes if hasattr(r, "path")]
        assert len(routes) >= 1

    def test_controller_ignores_private_methods(self) -> None:
        """Test that controller ignores methods starting with underscore."""

        @controller(prefix="/test")
        class TestController:
            def __init__(self) -> None:
                pass

            @get("/public")
            def public_method(self) -> str:
                return "public"

            def _private_helper(self) -> str:
                return "private"

        routes = [r for r in TestController.router.routes if hasattr(r, "path")]
        # Should only have the public method
        assert len(routes) == 1
        assert any("/public" in getattr(r, "path", "") for r in routes)

    def test_controller_with_path_parameters(self) -> None:
        """Test controller with path parameters."""

        @controller(prefix="/users")
        class UserController:
            def __init__(self) -> None:
                pass

            @get("/{user_id}/profile")
            def get_profile(self, user_id: int) -> dict:
                return {"user_id": user_id, "profile": "data"}

            @get("/{user_id}/posts/{post_id}")
            def get_post(self, user_id: int, post_id: int) -> dict:
                return {"user_id": user_id, "post_id": post_id}

        routes = [r for r in UserController.router.routes if hasattr(r, "path")]
        assert len(routes) >= 2


class TestIntegrationScenarios:
    """Integration tests combining multiple features."""

    def test_controller_with_service_dependency(self) -> None:
        """Test controller with injected service."""

        class IUserService:
            pass

        @injectable(IUserService)  # type: ignore
        class UserService:
            def __init__(self) -> None:
                self.users = {1: "Alice", 2: "Bob"}

            def get_user(self, user_id: int) -> str:
                return self.users.get(user_id, "Unknown")

        @controller(prefix="/api/users", tags=["users"])
        class UserController:
            def __init__(self, service: IUserService) -> None:
                self.service = service

            @get("/{user_id}")
            def get_user(self, user_id: int) -> dict:
                return {"user": self.service.get_user(user_id)} # type: ignore

        # Verify controller was created with router
        assert hasattr(UserController, "router")
        assert UserController.router.prefix == "/api/users"

    def test_nested_dependency_chain(self) -> None:
        """Test deeply nested dependency chain."""

        class IRepo:
            pass

        class IService:
            pass

        @injectable(IRepo)  # type: ignore
        class Repository:
            def __init__(self) -> None:
                self.data = "repo_data"

        @injectable(IService)  # type: ignore
        class Service:
            def __init__(self, repo: IRepo) -> None:
                self.repo = repo

        @controller(prefix="/api")
        class ApiController:
            def __init__(self, service: IService) -> None:
                self.service = service

            @get("/data")
            def get_data(self) -> dict:
                return {"data": self.service.repo.data} # type: ignore

        # Verify all dependencies are registered
        assert container.get_dependency_config(IRepo) is not None
        assert container.get_dependency_config(IService) is not None
        assert hasattr(ApiController, "router")
