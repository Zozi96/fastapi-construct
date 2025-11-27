"""Tests to ensure backward compatibility with existing code patterns."""

from typing import Any

from fastapi import FastAPI, Response
from fastapi.testclient import TestClient
from pydantic import BaseModel

from fastapi_construct import controller, delete, get, post, put


class User(BaseModel):
    id: int
    name: str


class Item(BaseModel):
    id: int
    title: str


# Test 1: Explicit response_model should still work exactly as before
def test_explicit_response_model_unchanged():
    """Existing code with explicit response_model should work identically."""

    @controller(prefix="/users")
    class UserController:
        @get("/{user_id}", response_model=User)
        def get_user(self, user_id: int):
            # No return type annotation
            return User(id=user_id, name="John")

        @post("/", response_model=User, status_code=201)
        def create_user(self, name: str):
            # No return type annotation
            return User(id=1, name=name)

    app = FastAPI()
    app.include_router(UserController.router)
    client = TestClient(app)

    response = client.get("/users/1")
    assert response.status_code == 200
    assert response.json() == {"id": 1, "name": "John"}

    response = client.post("/users/", params={"name": "Jane"})
    assert response.status_code == 201
    assert response.json() == {"id": 1, "name": "Jane"}


# Test 2: Methods without type annotations should still work
def test_no_type_annotations_still_works():
    """Code without type annotations should continue working."""

    @controller(prefix="/items")
    class ItemController:
        @get("/{item_id}")
        def get_item(self, item_id: int):  # No return type
            return {"id": item_id, "title": "Item"}

        @post("/")
        def create_item(self, title: str):  # No return type
            return {"id": 1, "title": title}

    app = FastAPI()
    app.include_router(ItemController.router)
    client = TestClient(app)

    response = client.get("/items/1")
    assert response.status_code == 200

    response = client.post("/items/", params={"title": "New Item"})
    assert response.status_code == 200  # Should be 200, not 201 (no type annotation)


# Test 3: Explicit status_code should take precedence
def test_explicit_status_code_precedence():
    """Explicit status codes should override inference."""

    @controller(prefix="/items")
    class ItemController:
        @post("/", status_code=200)
        def create_item(self) -> Item:
            # Even though POST with return value, explicit 200 wins
            return Item(id=1, title="Item")

        @delete("/{item_id}", status_code=200)
        def delete_item(self, item_id: int) -> None:
            # Even though DELETE with no return, explicit 200 wins
            pass

    app = FastAPI()
    app.include_router(ItemController.router)
    client = TestClient(app)

    response = client.post("/items/")
    assert response.status_code == 200  # Not 201

    response = client.delete("/items/1")
    assert response.status_code == 200  # Not 204


# Test 4: Response types should still work as before
def test_response_types_unchanged():
    """Returning Response objects should work exactly as before."""

    @controller(prefix="/raw")
    class RawController:
        @get("/text")
        def get_text(self):
            # No type annotation, returns Response
            return Response(content="text", media_type="text/plain")

        @get("/json")
        def get_json(self):
            # No type annotation, returns dict
            return {"key": "value"}

    app = FastAPI()
    app.include_router(RawController.router)
    client = TestClient(app)

    response = client.get("/raw/text")
    assert response.status_code == 200
    assert response.text == "text"

    response = client.get("/raw/json")
    assert response.status_code == 200
    assert response.json() == {"key": "value"}


# Test 5: Mixed explicit and inferred should work together
def test_mixed_explicit_and_inferred():
    """Mix of old (explicit) and new (inferred) styles should coexist."""

    @controller(prefix="/mixed")
    class MixedController:
        # Old style: explicit everything
        @get("/old", response_model=User, status_code=200)
        def old_style(self):
            return User(id=1, name="Old")

        # New style: infer everything
        @get("/new")
        def new_style(self) -> User:
            """Get user."""
            return User(id=2, name="New")

        # Mixed: some explicit, some inferred
        @post("/mixed", status_code=200)
        def mixed_style(self) -> User:
            """Create user."""
            return User(id=3, name="Mixed")

    app = FastAPI()
    app.include_router(MixedController.router)
    client = TestClient(app)

    # All should work
    assert client.get("/mixed/old").status_code == 200
    assert client.get("/mixed/new").status_code == 200
    assert client.post("/mixed/mixed").status_code == 200


# Test 6: Empty/missing docstrings shouldn't break
def test_missing_docstrings_no_issue():
    """Methods without docstrings should still work fine."""

    @controller(prefix="/nodoc")
    class NoDocController:
        @get("/{id}")
        def get_item(self, id: int) -> Item:
            return Item(id=id, title="Item")

        @post("/")
        def create_item(self, title: str) -> Item:
            return Item(id=1, title=title)

    app = FastAPI()
    app.include_router(NoDocController.router)
    client = TestClient(app)

    response = client.get("/nodoc/1")
    assert response.status_code == 200
    assert response.json() == {"id": 1, "title": "Item"}


# Test 7: Dict return types should still work
def test_dict_return_types():
    """Returning plain dicts should continue to work."""

    @controller(prefix="/dicts")
    class DictController:
        @get("/plain")
        def get_plain(self) -> dict:
            return {"key": "value"}

        @get("/any")
        def get_any(self) -> Any:
            return {"another": "dict"}

        @get("/dict-str-any")
        def get_dict_str_any(self) -> dict[str, Any]:
            return {"typed": "dict"}

    app = FastAPI()
    app.include_router(DictController.router)
    client = TestClient(app)

    response = client.get("/dicts/plain")
    assert response.status_code == 200
    assert response.json() == {"key": "value"}

    response = client.get("/dicts/any")
    assert response.status_code == 200

    response = client.get("/dicts/dict-str-any")
    assert response.status_code == 200


# Test 8: Explicit response_model=None should still work
def test_explicit_response_model_none():
    """Explicitly setting response_model=None should still work."""

    @controller(prefix="/none")
    class NoneController:
        @get("/test", response_model=None)
        def get_test(self) -> dict:
            return {"data": "value"}

    app = FastAPI()
    app.include_router(NoneController.router)
    client = TestClient(app)

    response = client.get("/none/test")
    assert response.status_code == 200
    assert response.json() == {"data": "value"}


# Test 9: List return types
def test_list_return_types():
    """List[Model] return types should work for inference."""

    @controller(prefix="/lists")
    class ListController:
        @get("/users")
        def get_users(self) -> list[User]:
            return [User(id=1, name="Alice"), User(id=2, name="Bob")]

        @get("/users-explicit", response_model=list[User])
        def get_users_explicit(self):
            return [User(id=3, name="Charlie"), User(id=4, name="Diana")]

    app = FastAPI()
    app.include_router(ListController.router)
    client = TestClient(app)

    # Inferred
    response = client.get("/lists/users")
    assert response.status_code == 200
    assert len(response.json()) == 2

    # Explicit
    response = client.get("/lists/users-explicit")
    assert response.status_code == 200
    assert len(response.json()) == 2


# Test 10: Optional return types
def test_optional_return_types():
    """Optional[Model] return types should work."""

    @controller(prefix="/optional")
    class OptionalController:
        @get("/{id}")
        def get_user(self, id: int) -> User | None:
            if id == 1:
                return User(id=1, name="Found")
            return None

    app = FastAPI()
    app.include_router(OptionalController.router)
    client = TestClient(app)

    response = client.get("/optional/1")
    assert response.status_code == 200
    assert response.json() == {"id": 1, "name": "Found"}

    response = client.get("/optional/2")
    assert response.status_code == 200
    assert response.json() is None


# Test 11: Controllers with no __init__
def test_controllers_without_init():
    """Controllers without __init__ should still work."""

    @controller(prefix="/simple")
    class SimpleController:
        @get("/test")
        def get_test(self) -> Item:
            return Item(id=1, title="Simple")

    app = FastAPI()
    app.include_router(SimpleController.router)
    client = TestClient(app)

    response = client.get("/simple/test")
    assert response.status_code == 200
    assert response.json() == {"id": 1, "title": "Simple"}


# Test 12: Empty return type (-> None) for non-DELETE methods
def test_none_return_for_put_patch():
    """PUT/PATCH with None return shouldn't get 204."""

    @controller(prefix="/updates")
    class UpdateController:
        @put("/{id}")
        def update_item(self, id: int) -> None:
            # PUT with None should stay 200, not 204
            pass

        @post("/process")
        def process(self) -> None:
            # POST with None should stay 200, not 204 (POST needs return value for 201)
            pass

    app = FastAPI()
    app.include_router(UpdateController.router)
    client = TestClient(app)

    response = client.put("/updates/1")
    assert response.status_code == 200  # Not 204

    response = client.post("/updates/process")
    assert response.status_code == 200  # Not 201 (no return value)


# Test 13: Existing OpenAPI customizations should be preserved
def test_openapi_customizations_preserved():
    """Custom OpenAPI parameters should be preserved."""

    @controller(prefix="/custom")
    class CustomController:
        @get(
            "/test",
            summary="Custom Summary",
            description="Custom Description",
            operation_id="custom_operation",
            deprecated=True,
            tags=["custom-tag"],
        )
        def get_test(self) -> Item:
            """This docstring should be ignored."""
            return Item(id=1, title="Custom")

    app = FastAPI()
    app.include_router(CustomController.router)

    openapi = app.openapi()
    endpoint = openapi["paths"]["/custom/test"]["get"]

    # All explicit values should be preserved
    assert endpoint["summary"] == "Custom Summary"
    assert endpoint["description"] == "Custom Description"
    assert endpoint["operationId"] == "custom_operation"
    assert endpoint["deprecated"] is True
    assert "custom-tag" in endpoint["tags"]
