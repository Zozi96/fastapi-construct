"""Test the exact auth pattern that was failing."""
import warnings

from fastapi import FastAPI, status
from fastapi.testclient import TestClient
from pydantic import BaseModel

from fastapi_construct import controller, post


class LoginRequest(BaseModel):
    email: str
    password: str


class RegisterRequest(BaseModel):
    email: str
    password: str
    full_name: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


class UserResponse(BaseModel):
    id: int
    name: str
    email: str


def test_auth_controller_with_explicit_response_model():
    """Test the exact pattern from the user's auth controller."""

    @controller(prefix="", tags=["auth"])
    class AuthController:
        @post(
            "/register",
            status_code=status.HTTP_201_CREATED,
            response_model=UserResponse,
        )
        async def register(self, register_data: RegisterRequest) -> UserResponse:
            return UserResponse(id=1, name="Test User", email="test@example.com")

        @post("/login", response_model=TokenResponse)
        async def login(self, login_data: LoginRequest) -> TokenResponse:
            return TokenResponse(access_token="test_token_123")

    app = FastAPI()
    app.include_router(AuthController.router)
    client = TestClient(app)

    # Test register
    response = client.post(
        "/register",
        json={"email": "user@example.com", "password": "password123", "full_name": "John Doe"},
    )
    assert response.status_code == 201
    assert response.json() == {"id": 1, "name": "Test User", "email": "test@example.com"}

    # Test login
    response = client.post(
        "/login",
        json={"email": "user@example.com", "password": "password123"},
    )
    assert response.status_code == 201  # Should be 201 due to status_code inference for POST
    assert response.json() == {"access_token": "test_token_123", "token_type": "bearer"}


def test_auth_controller_without_explicit_response_model():
    """Test auth controller relying only on type inference."""

    @controller(prefix="/api", tags=["auth"])
    class AuthController:
        @post("/register")
        async def register(self, register_data: RegisterRequest) -> UserResponse:
            """Register a new user."""
            return UserResponse(id=1, name="Test User", email="test@example.com")

        @post("/login")
        async def login(self, login_data: LoginRequest) -> TokenResponse:
            """Login and get access token."""
            return TokenResponse(access_token="test_token_123")

    app = FastAPI()
    app.include_router(AuthController.router)
    client = TestClient(app)

    # Test register - should infer status_code=201 and response_model=UserResponse
    response = client.post(
        "/api/register",
        json={"email": "user@example.com", "password": "password123", "full_name": "John Doe"},
    )
    assert response.status_code == 201
    assert response.json() == {"id": 1, "name": "Test User", "email": "test@example.com"}

    # Test login - should infer status_code=201 and response_model=TokenResponse
    response = client.post(
        "/api/login",
        json={"email": "user@example.com", "password": "password123"},
    )
    assert response.status_code == 201
    assert response.json() == {"access_token": "test_token_123", "token_type": "bearer"}


def test_validation_warning_is_emitted():
    """Test that validation warning is emitted for inconsistent types."""

    with warnings.catch_warnings(record=True) as w:
        warnings.simplefilter("always")

        @controller(prefix="/test")
        class TestController:
            @post("/endpoint", response_model=TokenResponse)
            async def endpoint(self) -> UserResponse:  # Inconsistent!
                return UserResponse(id=1, name="Test", email="test@example.com")

        # Should have emitted a warning
        assert len(w) == 1
        assert "Inconsistent response_model" in str(w[0].message)
