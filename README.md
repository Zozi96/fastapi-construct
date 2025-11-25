# FastAPI Construct

[![Tests](https://github.com/Zozi96/fastapi-construct/actions/workflows/test.yml/badge.svg)](https://github.com/Zozi96/fastapi-construct/actions/workflows/test.yml)
[![PyPI version](https://badge.fury.io/py/fastapi-construct.svg)](https://pypi.org/project/fastapi-construct/)
[![Python Version](https://img.shields.io/pypi/pyversions/fastapi-construct)](https://pypi.org/project/fastapi-construct/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Downloads](https://img.shields.io/pypi/dm/fastapi-construct)](https://pypi.org/project/fastapi-construct/)
[![Code style: ruff](https://img.shields.io/badge/code%20style-ruff-000000.svg)](https://github.com/astral-sh/ruff)

> A lightweight dependency injection library for FastAPI with NestJS/ASP.NET Core style architecture

FastAPI Construct brings the elegant patterns of NestJS and ASP.NET Core to FastAPI, enabling clean, testable, and maintainable code through:

- **Class-based controllers** with clean route grouping
- **Constructor dependency injection** using Python type hints (no `Depends()` boilerplate)
- **Function injection** with `@inject` decorator for regular functions and endpoints
- **Service lifecycles** (Scoped, Transient, Singleton) for fine-grained control
- **Auto-wiring** of dependencies by type

## Table of Contents

- [Why FastAPI Construct?](#why-fastapi-construct)
- [Installation](#installation)
- [Quick Start](#quick-start)
- [Features](#features)
  - [Dependency Injection](#dependency-injection)
  - [Function Injection](#function-injection)
  - [Service Lifecycles](#service-lifecycles)
  - [Class-based Controllers](#class-based-controllers)
  - [HTTP Method Decorators](#http-method-decorators)
- [Advanced Usage](#advanced-usage)
  - [Manual Registration](#manual-registration)
  - [Nested Dependencies](#nested-dependencies)
  - [Multiple Controllers](#multiple-controllers)
- [Best Practices](#best-practices)
- [Examples](#examples)
- [Contributing](#contributing)
- [License](#license)

## Why FastAPI Construct?

Traditional FastAPI dependency injection requires `Depends()` in function signatures, leading to verbose code:

```python
# Traditional FastAPI
@app.get("/users/{user_id}")
async def get_user(
    user_id: int,
    db: AsyncSession = Depends(get_db),
    service: UserService = Depends(get_user_service)
):
    return await service.get_user(db, user_id)
```

With FastAPI Construct, dependencies are injected in the constructor, keeping route handlers clean:

```python
# FastAPI Construct - Controllers
@controller(prefix="/users")
class UserController:
    def __init__(self, service: IUserService):
        self.service = service

    @get("/{user_id}")
    async def get_user(self, user_id: int):
        return await self.service.get_user(user_id)
```

Or use `@inject` for helper functions used as dependencies:

```python
# FastAPI Construct - Function Injection
@inject
def get_user_data(user_id: int, service: IUserService) -> dict:
    return service.get_user(user_id)

@app.get("/users/{user_id}")
def get_user(user_id: int, data: dict = Depends(get_user_data)):
    return data
```

## Installation

Install from PyPI using pip:

```bash
pip install fastapi-construct
```

Or using `uv`:

```bash
uv add fastapi-construct
```

**Requirements:**
- Python 3.12+
- FastAPI 0.122.0+

## Quick Start

### 1. Define Your Service Layer

Create interfaces and implementations using the `@injectable` decorator:

```python
from abc import ABC, abstractmethod
from fastapi_construct import injectable, ServiceLifetime

class IUserService(ABC):
    @abstractmethod
    async def get_user(self, user_id: int) -> dict:
        ...

    @abstractmethod
    async def create_user(self, name: str, email: str) -> dict:
        ...

@injectable(IUserService, lifetime=ServiceLifetime.SCOPED)
class UserService(IUserService):
    def __init__(self, db: AsyncSession):
        self.db = db

    async def get_user(self, user_id: int) -> dict:
        # Your database logic here
        return {"id": user_id, "name": "John Doe"}

    async def create_user(self, name: str, email: str) -> dict:
        # Your database logic here
        return {"id": 1, "name": name, "email": email}
```

### 2. Create a Controller

Use the `@controller` decorator to create class-based controllers:

```python
from fastapi_construct import controller, get, post

@controller(prefix="/api/users", tags=["users"])
class UserController:
    def __init__(self, service: IUserService):
        self.service = service

    @get("/{user_id}")
    async def get_user(self, user_id: int):
        """Get a user by ID."""
        return await self.service.get_user(user_id)

    @post("/")
    async def create_user(self, name: str, email: str):
        """Create a new user."""
        return await self.service.create_user(name, email)
```

### 3. Register and Run Your App

Include the controller router in your FastAPI application:

```python
from fastapi import FastAPI
from fastapi_construct import add_scoped
from sqlalchemy.ext.asyncio import AsyncSession
from .database import get_db
from .controllers import UserController

# Register external dependencies
add_scoped(AsyncSession, get_db)

# Create FastAPI app
app = FastAPI(title="My API")

# Include controller routers
app.include_router(UserController.router)
```

## Features

### Dependency Injection

FastAPI Construct uses constructor-based dependency injection, making your code cleaner and more testable:

```python
@injectable(IEmailService)
class EmailService(IEmailService):
    def send_email(self, to: str, subject: str, body: str):
        # Email logic here
        pass

@injectable(IUserService)
class UserService(IUserService):
    def __init__(self, email_service: IEmailService):
        self.email_service = email_service

    async def create_user(self, email: str):
        # Create user logic
        self.email_service.send_email(email, "Welcome", "Thanks for joining!")
        return {"email": email}
```

### Function Injection

Use the `@inject` decorator to inject dependencies into helper functions that can then be used as FastAPI dependencies:

```python
from fastapi_construct import inject

# Define a helper function with @inject
@inject
def get_current_user(token: str, auth_service: IAuthService) -> User:
    """
    Dependencies are automatically injected based on type hints.
    No need to use Depends() for registered services.
    """
    return auth_service.validate_token(token)

# Use the injected function as a dependency in endpoints
@app.get("/profile")
def get_profile(user: User = Depends(get_current_user)):
    return {"user": user}

# Or create reusable business logic functions
@inject
def process_order(order_data: dict, service: IOrderService) -> dict:
    return service.process(order_data)

@app.post("/orders")
def create_order(result: dict = Depends(process_order)):
    return result
```

The `@inject` decorator works by:
1. Inspecting the function signature
2. Replacing type-annotated parameters with `Depends(provider)` for registered services
3. Allowing FastAPI to resolve dependencies automatically at runtime

> **Note**: Use `@inject` on helper/utility functions that you'll use with `Depends()`, not directly on route handler functions. For route handlers, use the `@controller` decorator with class-based controllers instead.

### Service Lifecycles

Control when and how your services are instantiated:

| Lifetime | Description | Use Case |
|----------|-------------|----------|
| **SCOPED** (default) | One instance per HTTP request | Database sessions, request-scoped services |
| **TRANSIENT** | New instance every injection | Lightweight helpers, stateless services |
| **SINGLETON** | One instance for app lifetime | Configuration, caches, shared resources |

```python
from fastapi_construct import injectable, ServiceLifetime

@injectable(IConfigService, lifetime=ServiceLifetime.SINGLETON)
class ConfigService(IConfigService):
    def __init__(self):
        self.settings = self._load_settings()

@injectable(IUserService, lifetime=ServiceLifetime.SCOPED)
class UserService(IUserService):
    def __init__(self, db: AsyncSession):
        self.db = db

@injectable(IHelperService, lifetime=ServiceLifetime.TRANSIENT)
class HelperService(IHelperService):
    def process_data(self, data: dict) -> dict:
        return {"processed": True, **data}
```

### Class-based Controllers

Organize your routes using class-based controllers with clean decorators:

```python
from fastapi_construct import controller, get, post, put, delete, patch

@controller(prefix="/api/items", tags=["items"])
class ItemController:
    def __init__(self, item_service: IItemService):
        self.item_service = item_service

    @get("/")
    async def list_items(self, skip: int = 0, limit: int = 10):
        """List all items with pagination."""
        return await self.item_service.list_items(skip, limit)

    @get("/{item_id}")
    async def get_item(self, item_id: int):
        """Get a specific item by ID."""
        return await self.item_service.get_item(item_id)

    @post("/", status_code=201)
    async def create_item(self, name: str, description: str):
        """Create a new item."""
        return await self.item_service.create_item(name, description)

    @put("/{item_id}")
    async def update_item(self, item_id: int, name: str, description: str):
        """Update an existing item."""
        return await self.item_service.update_item(item_id, name, description)

    @patch("/{item_id}")
    async def partial_update(self, item_id: int, name: str | None = None):
        """Partially update an item."""
        return await self.item_service.partial_update(item_id, name)

    @delete("/{item_id}", status_code=204)
    async def delete_item(self, item_id: int):
        """Delete an item."""
        await self.item_service.delete_item(item_id)
```

### HTTP Method Decorators

FastAPI Construct provides decorators for all HTTP methods:

- `@get(path, **kwargs)` - GET requests
- `@post(path, **kwargs)` - POST requests
- `@put(path, **kwargs)` - PUT requests
- `@patch(path, **kwargs)` - PATCH requests
- `@delete(path, **kwargs)` - DELETE requests

All decorators support FastAPI's standard parameters:

```python
@get(
    "/{user_id}",
    response_model=UserResponse,
    status_code=200,
    summary="Get user by ID",
    description="Retrieve a user's details by their unique identifier",
    tags=["users"]
)
async def get_user(self, user_id: int):
    return await self.service.get_user(user_id)
```

## Advanced Usage

### Manual Registration

For third-party libraries or types you don't control, use manual registration:

```python
from fastapi_construct import add_singleton, add_scoped, add_transient
from redis.asyncio import Redis
from httpx import AsyncClient

# Register a Redis client as singleton
def get_redis():
    return Redis(host="localhost", port=6379)

add_singleton(Redis, get_redis)

# Register httpx client as scoped
async def get_http_client():
    async with AsyncClient() as client:
        yield client

add_scoped(AsyncClient, get_http_client)

# Now use them in your services
@injectable(ICacheService)
class CacheService(ICacheService):
    def __init__(self, redis: Redis, http: AsyncClient):
        self.redis = redis
        self.http = http
```

### Nested Dependencies

FastAPI Construct automatically resolves nested dependency chains:

```python
@injectable(IDatabase)
class Database(IDatabase):
    def query(self, sql: str):
        # Database logic
        pass

@injectable(IRepository)
class UserRepository(IRepository):
    def __init__(self, db: IDatabase):
        self.db = db

    def get_user(self, user_id: int):
        return self.db.query(f"SELECT * FROM users WHERE id = {user_id}")

@injectable(IUserService)
class UserService(IUserService):
    def __init__(self, repo: IRepository):
        self.repo = repo

    def get_user(self, user_id: int):
        return self.repo.get_user(user_id)

@controller(prefix="/users")
class UserController:
    def __init__(self, service: IUserService):
        # UserService -> UserRepository -> Database
        # All automatically injected!
        self.service = service
```

### Multiple Controllers

Organize your application with multiple controllers:

```python
from fastapi import FastAPI

# Define controllers
@controller(prefix="/api/v1/users", tags=["users"])
class UserController:
    ...

@controller(prefix="/api/v1/posts", tags=["posts"])
class PostController:
    ...

@controller(prefix="/api/v1/comments", tags=["comments"])
class CommentController:
    ...

```python
# Register all controllers
app = FastAPI()
app.include_router(UserController.router)
app.include_router(PostController.router)
app.include_router(CommentController.router)
```

### Container & Error Handling

FastAPI Construct uses a `Container` class to manage dependencies. While the global helper functions (`add_scoped`, etc.) are sufficient for most cases, you can access the container directly for advanced scenarios.

#### Circular Dependencies

The library automatically detects circular dependencies during resolution and raises a `CircularDependencyError` with a helpful message, preventing infinite recursion crashes.

```python
class A:
    def __init__(self, b: B): ...

class B:
    def __init__(self, a: A): ...

# This will raise CircularDependencyError when resolved
container.resolve(A)
```

#### Custom Container

You can create your own `Container` instance for isolation (e.g., for testing):

```python
from fastapi_construct.container import Container

my_container = Container()
my_container.register(IService, ServiceImpl)
instance = my_container.resolve(IService)
```

## Best Practices

### 1. Use Interfaces for Abstraction

Define interfaces (abstract base classes) for better testability and loose coupling:

```python
from abc import ABC, abstractmethod

class IUserService(ABC):
    @abstractmethod
    async def get_user(self, user_id: int) -> dict:
        ...

# Easy to mock in tests
class MockUserService(IUserService):
    async def get_user(self, user_id: int) -> dict:
        return {"id": user_id, "name": "Test User"}
```

### 2. Choose Appropriate Lifetimes

- Use **SCOPED** for database sessions and request-specific state
- Use **SINGLETON** for expensive-to-create resources (DB pools, config)
- Use **TRANSIENT** for lightweight, stateless services

### 3. Keep Controllers Thin

Controllers should delegate business logic to services:

```python
# Good ✅
@controller(prefix="/users")
class UserController:
    def __init__(self, service: IUserService):
        self.service = service

    @post("/")
    async def create_user(self, user_data: UserCreate):
        return await self.service.create_user(user_data)

# Bad ❌
@controller(prefix="/users")
class UserController:
    def __init__(self, db: Database):
        self.db = db

    @post("/")
    async def create_user(self, user_data: UserCreate):
        # Too much logic in controller!
        user = User(**user_data.dict())
        self.db.add(user)
        await self.db.commit()
        return user
```

### 4. Organize by Feature

Structure your project by feature, not by type:

```
src/
├── users/
│   ├── __init__.py
│   ├── controllers.py
│   ├── services.py
│   ├── repositories.py
│   └── models.py
├── posts/
│   ├── __init__.py
│   ├── controllers.py
│   ├── services.py
│   └── models.py
└── main.py
```

## Examples

### Complete CRUD Example

```python
from abc import ABC, abstractmethod
from fastapi import FastAPI
from fastapi_construct import (
    injectable,
    controller,
    get,
    post,
    put,
    delete,
    ServiceLifetime,
)

# Interface
class IProductService(ABC):
    @abstractmethod
    async def list_products(self) -> list[dict]:
        ...

    @abstractmethod
    async def get_product(self, product_id: int) -> dict:
        ...

    @abstractmethod
    async def create_product(self, name: str, price: float) -> dict:
        ...

    @abstractmethod
    async def update_product(self, product_id: int, name: str, price: float) -> dict:
        ...

    @abstractmethod
    async def delete_product(self, product_id: int) -> None:
        ...

# Service implementation
@injectable(IProductService, lifetime=ServiceLifetime.SCOPED)
class ProductService(IProductService):
    def __init__(self):
        self.products = {
            1: {"id": 1, "name": "Product 1", "price": 10.99},
            2: {"id": 2, "name": "Product 2", "price": 20.99},
        }
        self.next_id = 3

    async def list_products(self) -> list[dict]:
        return list(self.products.values())

    async def get_product(self, product_id: int) -> dict:
        return self.products.get(product_id, {})

    async def create_product(self, name: str, price: float) -> dict:
        product = {"id": self.next_id, "name": name, "price": price}
        self.products[self.next_id] = product
        self.next_id += 1
        return product

    async def update_product(self, product_id: int, name: str, price: float) -> dict:
        if product_id in self.products:
            self.products[product_id] = {"id": product_id, "name": name, "price": price}
            return self.products[product_id]
        return {}

    async def delete_product(self, product_id: int) -> None:
        self.products.pop(product_id, None)

# Controller
@controller(prefix="/api/products", tags=["products"])
class ProductController:
    def __init__(self, service: IProductService):
        self.service = service

    @get("/")
    async def list_products(self):
        """List all products."""
        return await self.service.list_products()

    @get("/{product_id}")
    async def get_product(self, product_id: int):
        """Get a product by ID."""
        return await self.service.get_product(product_id)

    @post("/", status_code=201)
    async def create_product(self, name: str, price: float):
        """Create a new product."""
        return await self.service.create_product(name, price)

    @put("/{product_id}")
    async def update_product(self, product_id: int, name: str, price: float):
        """Update a product."""
        return await self.service.update_product(product_id, name, price)

    @delete("/{product_id}", status_code=204)
    async def delete_product(self, product_id: int):
        """Delete a product."""
        await self.service.delete_product(product_id)

# Application
app = FastAPI(title="Products API")
app.include_router(ProductController.router)
```

## Contributing

Contributions are welcome! Please follow these steps:

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/amazing-feature`)
3. Make your changes
4. Add tests for your changes
5. Run tests (`pytest tests/`)
6. Run linting (`ruff check . && ruff format .`)
7. Commit your changes (`git commit -m 'Add amazing feature'`)
8. Push to the branch (`git push origin feature/amazing-feature`)
9. Open a Pull Request

Please ensure:
- All tests pass
- Code follows Ruff formatting standards
- New features include tests
- Documentation is updated

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

## Acknowledgments

Inspired by:
- [NestJS](https://nestjs.com/) - A progressive Node.js framework
- [ASP.NET Core](https://docs.microsoft.com/en-us/aspnet/core/) - Microsoft's web framework
- [FastAPI](https://fastapi.tiangolo.com/) - The amazing Python web framework

---

**Made with ❤️ for the FastAPI community**

[⭐ Star on GitHub](https://github.com/Zozi96/fastapi-construct) | [📝 Report Issues](https://github.com/Zozi96/fastapi-construct/issues) | [📖 Documentation](https://github.com/Zozi96/fastapi-construct#readme)
