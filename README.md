# FastAPI Construct

FastAPI Construct is a lightweight library that brings NestJS / ASP.NET Core style architecture to FastAPI. It provides:

- Class-based controllers (clean route grouping with `@controller`).
- Constructor dependency injection using Python type hints (no `Depends()` boilerplate in `__init__`).
- Service lifecycles: `SCOPED` (per request), `TRANSIENT`, and `SINGLETON`.

The goal is cleaner, more testable, and framework-agnostic code.

## Features

- Clean constructors: keep `__init__` signatures simple and type-hinted.
- Auto-wiring: the container resolves and injects dependencies by type.
- Controller routing: define routes inside classes with decorators like `@get`, `@post`.
- Lifecycle management: control when instances are created and reused.

## Installation

Install from PyPI:

```bash
pip install fastapi-construct
```

Or, if you use the `uv` package manager:

```bash
uv add fastapi-construct
```

## Quick Start

1) Define interfaces and implementations. Use `@injectable` to register implementations.

```python
from abc import ABC, abstractmethod
from fastapi_construct import injectable, ServiceLifetime

class IUserService(ABC):
    @abstractmethod
    def get_user(self, user_id: int) -> dict:
        ...

@injectable(IUserService, lifetime=ServiceLifetime.SCOPED)
class UserService(IUserService):
    def get_user(self, user_id: int) -> dict:
        return {"id": user_id, "name": "John Doe"}
```

2) Create a controller. Constructor injection happens automatically.

```python
from fastapi_construct import controller, get
from .services import IUserService

@controller(prefix="/users", tags=["users"])
class UserController:
    def __init__(self, service: IUserService):
        self.service = service

    @get("/{user_id}")
    async def get_user(self, user_id: int):
        return self.service.get_user(user_id)
```

3) Register external dependencies (optional) and include the controller router in your FastAPI app.

```python
from fastapi import FastAPI
from fastapi_construct import add_scoped
from sqlalchemy.ext.asyncio import AsyncSession
from .database import get_db
from .controllers import UserController

# Example: bind AsyncSession to your DB provider
add_scoped(AsyncSession, get_db)

app = FastAPI()
app.include_router(UserController.router)
```

## Dependency Lifecycles

- `SCOPED` (default) — one instance per HTTP request. Good for DB sessions and request-scoped services.
- `TRANSIENT` — a new instance every injection. Good for lightweight helpers.
- `SINGLETON` — one instance for the app lifetime. Good for config or caches.

```python
from fastapi_construct import injectable, ServiceLifetime

@injectable(IMyService, lifetime=ServiceLifetime.SINGLETON)
class MySingletonService(IMyService):
    ...
```

## Manual Registration (3rd-party libraries)

To inject types you don't control (e.g., a 3rd-party client or DB session factory), use the `add_*` helpers:

```python
from fastapi_construct import add_singleton, add_scoped
from some_lib import Client

# Register a 3rd-party client as a singleton
add_singleton(Client, Client)
```

## Contributing

Contributions are welcome — please open a PR with tests and a clear description of the change.

## License

This project is licensed under the MIT License.