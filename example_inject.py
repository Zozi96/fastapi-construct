"""
Example usage of the @inject decorator for dependency injection in functions.
"""

from abc import ABC, abstractmethod

from fastapi import Depends, FastAPI

from fastapi_construct import ServiceLifetime, inject, injectable


# 1. Define an interface
class IGreetingService(ABC):
    @abstractmethod
    def greet(self, name: str) -> str: ...


# 2. Implement the service and register it with @injectable
@injectable(IGreetingService, lifetime=ServiceLifetime.SCOPED)
class GreetingService(IGreetingService):
    def greet(self, name: str) -> str:
        return f"Hello, {name}!"


# 3. Use @inject on a regular function to automatically inject the service
@inject
def get_greeting_message(name: str, service: IGreetingService) -> str:
    """
    This function receives the service automatically injected.
    No need to use Depends() in the function signature.
    """
    return service.greet(name)


# 4. Create a FastAPI application
app = FastAPI(title="@inject Example")


# 5. Use @inject on helper functions that will be used as dependencies
@inject
def get_greeting(name: str, service: IGreetingService) -> str:
    """
    Helper function with automatic dependency injection.
    This can be used as a FastAPI dependency.
    """
    return service.greet(name)


# 6. Use the injected helper function in endpoints
@app.get("/greet/{name}")
def greet_endpoint(name: str, message: str = Depends(get_greeting)):
    """
    The get_greeting function has IGreetingService automatically injected,
    and we use it as a dependency here with Depends().
    """
    return {"message": message, "user": name}


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)
