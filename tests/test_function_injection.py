import inspect
from abc import ABC, abstractmethod

from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient

from fastapi_construct import ServiceLifetime, inject, injectable


# Define interfaces and services
class IService(ABC):
    @abstractmethod
    def get_value(self) -> str: ...


@injectable(IService, lifetime=ServiceLifetime.SCOPED)
class Service(IService):
    def get_value(self) -> str:
        return "injected"


# Define a function to test injection
@inject
def function_with_injection(service: IService) -> str:
    return service.get_value()


# Define a function where injection is used as a dependency in a router
@inject
def dependency_function(service: IService):
    return service


def test_function_injection_direct_call():
    # This might not work directly without a FastAPI context if it relies on Depends
    # But let's see how Depends behaves. Depends is a Pydantic thing, usually resolved by FastAPI.
    # Calling it directly returns the function itself, but the signature is modified.
    # We can inspect the signature to see if Depends is there.

    sig = inspect.signature(function_with_injection)
    param = sig.parameters["service"]
    # Check that the default is a Depends instance by checking its type name
    assert type(param.default).__name__ == "Depends"


def test_function_injection_in_fastapi():
    app = FastAPI()

    # Register the service manually if needed, or rely on auto-discovery if we had a scanner.
    # Here we rely on the fact that @injectable registers it in the global registry.
    # But we need to make sure the app knows how to resolve it?
    # fastapi-construct works by registering dependencies in the container,
    # and then `autowire_callable` (which is `@inject`) replaces the default value with `Depends(provider)`.
    # So FastAPI should be able to resolve it.

    @app.get("/test")
    def endpoint(value: str = Depends(function_with_injection)):
        return {"value": value}

    client = TestClient(app)
    response = client.get("/test")
    assert response.status_code == 200
    assert response.json() == {"value": "injected"}


def test_function_injection_as_endpoint():
    """
    Test that @inject works when used with helper functions
    that are then used as dependencies in endpoints.
    """
    app = FastAPI()

    # Use the injected function as a dependency
    @app.get("/endpoint")
    def endpoint(service: IService = Depends(dependency_function)):  # noqa: B008
        return {"value": service.get_value()}

    client = TestClient(app)
    response = client.get("/endpoint")
    assert response.status_code == 200
    assert response.json() == {"value": "injected"}
