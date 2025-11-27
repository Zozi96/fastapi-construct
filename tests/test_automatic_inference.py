"""Tests for automatic inference of metadata (status_code, summary, description, operation_id, response_class)."""

import warnings

from fastapi import FastAPI
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.testclient import TestClient
from pydantic import BaseModel

from fastapi_construct import controller, delete, get, post, put


class UserResponse(BaseModel):
    id: int
    name: str


class ItemResponse(BaseModel):
    id: int
    title: str
    price: float


def test_status_code_inference_for_post():
    """Test that POST methods automatically infer 201 status code."""

    @controller(prefix="/items")
    class ItemController:
        @post("/")
        def create_item(self) -> ItemResponse:
            return ItemResponse(id=1, title="Item", price=10.0)

    app = FastAPI()
    app.include_router(ItemController.router)
    client = TestClient(app)

    response = client.post("/items/")
    assert response.status_code == 201
    assert response.json() == {"id": 1, "title": "Item", "price": 10.0}


def test_status_code_inference_for_delete():
    """Test that DELETE methods with no return value automatically infer 204 status code."""

    @controller(prefix="/items")
    class ItemController:
        @delete("/{item_id}")
        def delete_item(self, item_id: int) -> None:
            pass

    app = FastAPI()
    app.include_router(ItemController.router)
    client = TestClient(app)

    response = client.delete("/items/1")
    assert response.status_code == 204


def test_status_code_explicit_takes_precedence():
    """Test that explicit status_code takes precedence over inferred."""

    @controller(prefix="/items")
    class ItemController:
        @post("/", status_code=200)
        def create_item(self) -> ItemResponse:
            return ItemResponse(id=1, title="Item", price=10.0)

    app = FastAPI()
    app.include_router(ItemController.router)
    client = TestClient(app)

    response = client.post("/items/")
    assert response.status_code == 200  # Explicit 200, not inferred 201


def test_summary_and_description_from_docstring():
    """Test that summary and description are inferred from docstring."""

    @controller(prefix="/users")
    class UserController:
        @get("/{user_id}")
        def get_user(self, user_id: int) -> UserResponse:
            """Get a user by ID.

            Retrieve detailed information about a specific user
            from the database using their unique identifier.
            """
            return UserResponse(id=user_id, name="John Doe")

    app = FastAPI()
    app.include_router(UserController.router)

    # Check OpenAPI schema
    openapi = app.openapi()
    endpoint = openapi["paths"]["/users/{user_id}"]["get"]
    assert endpoint["summary"] == "Get a user by ID."
    assert "Retrieve detailed information" in endpoint["description"]


def test_summary_explicit_takes_precedence():
    """Test that explicit summary/description takes precedence over docstring."""

    @controller(prefix="/users")
    class UserController:
        @get("/{user_id}", summary="Custom Summary", description="Custom Description")
        def get_user(self, user_id: int) -> UserResponse:
            """This docstring should be ignored.

            This description should also be ignored.
            """
            return UserResponse(id=user_id, name="John Doe")

    app = FastAPI()
    app.include_router(UserController.router)

    # Check OpenAPI schema
    openapi = app.openapi()
    endpoint = openapi["paths"]["/users/{user_id}"]["get"]
    assert endpoint["summary"] == "Custom Summary"
    assert endpoint["description"] == "Custom Description"


def test_operation_id_generation():
    """Test that operation_id is automatically generated from controller and method names."""

    @controller(prefix="/users")
    class UserController:
        @get("/{user_id}")
        def get_user_by_id(self, user_id: int) -> UserResponse:
            return UserResponse(id=user_id, name="John Doe")

        @post("/")
        def create_new_user(self) -> UserResponse:
            return UserResponse(id=1, name="Jane Doe")

    app = FastAPI()
    app.include_router(UserController.router)

    # Check OpenAPI schema
    openapi = app.openapi()
    assert "user_get_user_by_id" in openapi["paths"]["/users/{user_id}"]["get"]["operationId"]
    assert "user_create_new_user" in openapi["paths"]["/users/"]["post"]["operationId"]


def test_operation_id_camelcase_conversion():
    """Test that CamelCase controller names are converted to snake_case in operation_id."""

    @controller(prefix="/items")
    class ItemManagementController:
        @get("/{item_id}")
        def get_item(self, item_id: int) -> ItemResponse:
            return ItemResponse(id=item_id, title="Item", price=10.0)

    app = FastAPI()
    app.include_router(ItemManagementController.router)

    # Check OpenAPI schema
    openapi = app.openapi()
    operation_id = openapi["paths"]["/items/{item_id}"]["get"]["operationId"]
    assert operation_id == "item_management_get_item"


def test_operation_id_explicit_takes_precedence():
    """Test that explicit operation_id takes precedence."""

    @controller(prefix="/users")
    class UserController:
        @get("/{user_id}", operation_id="custom_operation_id")
        def get_user(self, user_id: int) -> UserResponse:
            return UserResponse(id=user_id, name="John Doe")

    app = FastAPI()
    app.include_router(UserController.router)

    # Check OpenAPI schema
    openapi = app.openapi()
    assert openapi["paths"]["/users/{user_id}"]["get"]["operationId"] == "custom_operation_id"


def test_response_subclass_disables_response_model():
    """Test that Response subclasses automatically disable response_model."""

    @controller(prefix="/pages")
    class PageController:
        @get("/home")
        def get_home(self) -> HTMLResponse:
            return HTMLResponse("<h1>Home</h1>")

        @get("/data")
        def get_data(self) -> JSONResponse:
            return JSONResponse({"key": "value"})

    app = FastAPI()
    app.include_router(PageController.router)
    client = TestClient(app)

    # Test HTMLResponse
    response = client.get("/pages/home")
    assert response.status_code == 200
    assert response.headers["content-type"] == "text/html; charset=utf-8"
    assert response.text == "<h1>Home</h1>"

    # Test JSONResponse
    response = client.get("/pages/data")
    assert response.status_code == 200
    assert response.json() == {"key": "value"}


def test_response_model_inconsistency_warning():
    """Test that inconsistent response_model and return type emit a warning."""

    with warnings.catch_warnings(record=True) as w:
        warnings.simplefilter("always")

        @controller(prefix="/users")
        class UserController:
            @get("/{user_id}", response_model=ItemResponse)
            def get_user(self, user_id: int) -> UserResponse:  # Inconsistent!
                return UserResponse(id=user_id, name="John Doe")

        # Check that a warning was raised
        assert len(w) == 1
        assert issubclass(w[0].category, UserWarning)
        assert "Inconsistent response_model" in str(w[0].message)


def test_all_inferences_together():
    """Test that all automatic inferences work together."""

    @controller(prefix="/items")
    class ItemController:
        @post("/")
        def create_item(self, title: str, price: float) -> ItemResponse:
            """Create a new item.

            Add a new item to the inventory with the specified
            title and price.
            """
            return ItemResponse(id=1, title=title, price=price)

        @delete("/{item_id}")
        def delete_item(self, item_id: int) -> None:
            """Delete an item.

            Remove an item from the inventory.
            """
            pass

    app = FastAPI()
    app.include_router(ItemController.router)
    client = TestClient(app)

    # Test POST with all inferences
    response = client.post("/items/", params={"title": "Widget", "price": 19.99})
    assert response.status_code == 201  # Inferred
    assert response.json() == {"id": 1, "title": "Widget", "price": 19.99}

    # Test DELETE with all inferences
    response = client.delete("/items/1")
    assert response.status_code == 204  # Inferred

    # Check OpenAPI schema
    openapi = app.openapi()

    # POST endpoint
    post_endpoint = openapi["paths"]["/items/"]["post"]
    assert post_endpoint["summary"] == "Create a new item."
    assert "Add a new item to the inventory" in post_endpoint["description"]
    assert post_endpoint["operationId"] == "item_create_item"

    # DELETE endpoint
    delete_endpoint = openapi["paths"]["/items/{item_id}"]["delete"]
    assert delete_endpoint["summary"] == "Delete an item."
    assert "Remove an item from the inventory" in delete_endpoint["description"]
    assert delete_endpoint["operationId"] == "item_delete_item"


def test_no_docstring_doesnt_break():
    """Test that methods without docstrings don't break."""

    @controller(prefix="/items")
    class ItemController:
        @get("/{item_id}")
        def get_item(self, item_id: int) -> ItemResponse:
            return ItemResponse(id=item_id, title="Item", price=10.0)

    app = FastAPI()
    app.include_router(ItemController.router)
    client = TestClient(app)

    # Should not raise any errors
    response = client.get("/items/1")
    assert response.status_code == 200
    assert response.json() == {"id": 1, "title": "Item", "price": 10.0}

    # FastAPI generates summary from method name if no docstring
    openapi = app.openapi()
    endpoint = openapi["paths"]["/items/{item_id}"]["get"]
    # Should have auto-generated summary from method name
    assert "summary" in endpoint
