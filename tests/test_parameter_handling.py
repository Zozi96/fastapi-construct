from fastapi import FastAPI
from fastapi.testclient import TestClient

from fastapi_construct import controller, get, injectable


def test_controller_with_variadic_args():
    @controller(prefix="/variadic")
    class VariadicController:
        def __init__(self, *args, **kwargs):
            self.args = args
            self.kwargs = kwargs

        @get("/")
        def index(self):
            return {"args": len(self.args), "kwargs": len(self.kwargs)}

    app = FastAPI()
    app.include_router(VariadicController.router)
    client = TestClient(app)

    response = client.get("/variadic/")
    assert response.status_code == 200
    assert response.json() == {"args": 0, "kwargs": 0}


def test_controller_with_optional_args():
    @controller(prefix="/optional")
    class OptionalController:
        def __init__(self, a: int = 10, b: str = "default"):
            self.a = a
            self.b = b

        @get("/")
        def index(self):
            return {"a": self.a, "b": self.b}

    app = FastAPI()
    app.include_router(OptionalController.router)
    client = TestClient(app)

    # Should use defaults
    response = client.get("/optional/")
    assert response.status_code == 200
    assert response.json() == {"a": 10, "b": "default"}

    # FastAPI treats un-annotated (or simple annotated) init params as query params if not injected?
    # Actually, get_instance signature is used by FastAPI.
    # If get_instance(a: int = 10, b: str = "default"), FastAPI will treat them as query params.
    # Let's verify this behavior.
    response = client.get("/optional/?a=20&b=custom")
    assert response.status_code == 200
    assert response.json() == {"a": 20, "b": "custom"}


def test_controller_with_mixed_args():
    @injectable(int)
    class SomeDependency:
        def __init__(self):
            self.val = 999

    @controller(prefix="/mixed")
    class MixedController:
        def __init__(self, dep: int, extra: str = "extra"):
            self.dep = dep
            self.extra = extra

        @get("/")
        def index(self):
            return {"dep": self.dep.val, "extra": self.extra}

    app = FastAPI()
    app.include_router(MixedController.router)
    client = TestClient(app)

    response = client.get("/mixed/")
    assert response.status_code == 200
    assert response.json() == {"dep": 999, "extra": "extra"}

    response = client.get("/mixed/?extra=new")
    assert response.status_code == 200
    assert response.json() == {"dep": 999, "extra": "new"}


def test_empty_controller():
    @controller(prefix="/empty")
    class EmptyController:
        @get("/")
        def index(self):
            return {"ok": True}

    app = FastAPI()
    app.include_router(EmptyController.router)
    client = TestClient(app)

    response = client.get("/empty/")
    assert response.status_code == 200
    assert response.json() == {"ok": True}
