from fastapi import FastAPI, Response
from fastapi.testclient import TestClient
from pydantic import BaseModel

from fastapi_construct import controller, get, post


def test_response_model_inference_disabled_for_response_return_type():
    @controller(prefix="/test")
    class TestController:
        @get("/response")
        def return_response(self) -> Response:
            return Response(content="ok")

        @get("/union_response")
        def return_union_response(self) -> Response | dict:
            return {"message": "ok"}

        @get("/optional_response")
        def return_optional_response(self) -> Response | None:
            return None

    app = FastAPI()
    app.include_router(TestController.router)
    client = TestClient(app)

    response = client.get("/test/response")
    assert response.status_code == 200
    assert response.text == "ok"

    response = client.get("/test/union_response")
    assert response.status_code == 200
    assert response.json() == {"message": "ok"}

    response = client.get("/test/optional_response")
    assert response.status_code == 200
    assert response.json() is None


def test_response_model_inference_from_type_annotation():
    """Test that response_model is inferred from return type annotation when not explicitly set."""

    class UserResponse(BaseModel):
        id: int
        name: str

    class TokenResponse(BaseModel):
        access_token: str
        token_type: str = "bearer"

    @controller(prefix="/api")
    class TestController:
        @get("/user")
        def get_user(self) -> UserResponse:
            """Should infer response_model=UserResponse from return annotation."""
            return UserResponse(id=1, name="John Doe")

        @post("/login")
        async def login(self) -> TokenResponse:
            """Should infer response_model=TokenResponse from return annotation."""
            return TokenResponse(access_token="token123")

        @get("/user-explicit", response_model=UserResponse)
        def get_user_explicit(self) -> UserResponse:
            """Explicit response_model should take precedence."""
            return UserResponse(id=2, name="Jane Doe")

    app = FastAPI()
    app.include_router(TestController.router)
    client = TestClient(app)

    # Test inferred response_model for sync endpoint
    response = client.get("/api/user")
    assert response.status_code == 200
    assert response.json() == {"id": 1, "name": "John Doe"}

    # Test inferred response_model for async endpoint
    # Also tests automatic status_code=201 inference for POST
    response = client.post("/api/login")
    assert response.status_code == 201
    assert response.json() == {"access_token": "token123", "token_type": "bearer"}

    # Test explicit response_model still works
    response = client.get("/api/user-explicit")
    assert response.status_code == 200
    assert response.json() == {"id": 2, "name": "Jane Doe"}

    # Verify OpenAPI schema includes the response models
    openapi_schema = app.openapi()
    assert "UserResponse" in openapi_schema["components"]["schemas"]
    assert "TokenResponse" in openapi_schema["components"]["schemas"]
