"""Example FastAPI application using fastapi-construct."""

from abc import ABC, abstractmethod

import uvicorn
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

from fastapi_construct import ServiceLifetime, controller, delete, get, injectable, patch, post, put


# Pydantic models
class ItemCreate(BaseModel):
    name: str
    description: str
    price: float


class ItemUpdate(BaseModel):
    name: str
    description: str
    price: float


class ItemPartialUpdate(BaseModel):
    name: str | None = None
    description: str | None = None
    price: float | None = None


class ItemResponse(BaseModel):
    id: int
    name: str
    description: str
    price: float


# Service layer
class IItemService(ABC):
    @abstractmethod
    def get_all(self) -> list[dict]:
        pass

    @abstractmethod
    def get_by_id(self, item_id: int) -> dict | None:
        pass

    @abstractmethod
    def create(self, item: ItemCreate) -> dict:
        pass

    @abstractmethod
    def update(self, item_id: int, item: ItemUpdate) -> dict | None:
        pass

    @abstractmethod
    def partial_update(self, item_id: int, item: ItemPartialUpdate) -> dict | None:
        pass

    @abstractmethod
    def delete(self, item_id: int) -> bool:
        pass


@injectable(IItemService, lifetime=ServiceLifetime.SINGLETON)
class ItemService(IItemService):
    def __init__(self):
        self.items: dict[int, dict] = {
            1: {"id": 1, "name": "Laptop", "description": "High-performance laptop", "price": 999.99},
            2: {"id": 2, "name": "Mouse", "description": "Wireless mouse", "price": 29.99},
            3: {"id": 3, "name": "Keyboard", "description": "Mechanical keyboard", "price": 79.99},
        }
        self.next_id = 4

    def get_all(self) -> list[dict]:
        return list(self.items.values())

    def get_by_id(self, item_id: int) -> dict | None:
        return self.items.get(item_id)

    def create(self, item: ItemCreate) -> dict:
        new_item = {
            "id": self.next_id,
            "name": item.name,
            "description": item.description,
            "price": item.price,
        }
        self.items[self.next_id] = new_item
        self.next_id += 1
        return new_item

    def update(self, item_id: int, item: ItemUpdate) -> dict | None:
        if item_id not in self.items:
            return None
        updated_item = {
            "id": item_id,
            "name": item.name,
            "description": item.description,
            "price": item.price,
        }
        self.items[item_id] = updated_item
        return updated_item

    def partial_update(self, item_id: int, item: ItemPartialUpdate) -> dict | None:
        if item_id not in self.items:
            return None

        current_item = self.items[item_id]
        if item.name is not None:
            current_item["name"] = item.name
        if item.description is not None:
            current_item["description"] = item.description
        if item.price is not None:
            current_item["price"] = item.price

        return current_item

    def delete(self, item_id: int) -> bool:
        if item_id in self.items:
            del self.items[item_id]
            return True
        return False


@injectable()
class SelfBoundService:
    def get_info(self) -> str:
        return "I am a self-bound service!"


# Controller
@controller(prefix="/api/items", tags=["Items"])
class ItemController:
    def __init__(self, item_service: IItemService, self_bound: SelfBoundService):
        self.item_service = item_service
        self.self_bound = self_bound

    @get("/self-bound-test")
    def test_self_bound(self):
        """Test self-bound service injection."""
        return {"message": self.self_bound.get_info()}

    @get(
        "/",
        response_model=list[ItemResponse],
        summary="List all items",
        description="Retrieve a list of all items in the inventory",
    )
    def list_items(self):
        """Get all items."""
        return self.item_service.get_all()

    @get(
        "/{item_id}",
        response_model=ItemResponse,
        summary="Get item by ID",
        description="Retrieve a specific item by its unique identifier",
    )
    def get_item(self, item_id: int):
        """Get a specific item by ID."""
        item = self.item_service.get_by_id(item_id)
        if not item:
            raise HTTPException(status_code=404, detail="Item not found")
        return item

    @post(
        "/",
        response_model=ItemResponse,
        status_code=201,
        summary="Create new item",
        description="Create a new item in the inventory",
    )
    def create_item(self, item: ItemCreate):
        """Create a new item."""
        return self.item_service.create(item)

    @put(
        "/{item_id}",
        response_model=ItemResponse,
        summary="Update item",
        description="Update all fields of an existing item",
    )
    def update_item(self, item_id: int, item: ItemUpdate):
        """Update an existing item (full update)."""
        updated = self.item_service.update(item_id, item)
        if not updated:
            raise HTTPException(status_code=404, detail="Item not found")
        return updated

    @patch(
        "/{item_id}",
        response_model=ItemResponse,
        summary="Partially update item",
        description="Update one or more fields of an existing item",
    )
    def partial_update_item(self, item_id: int, item: ItemPartialUpdate):
        """Partially update an item."""
        updated = self.item_service.partial_update(item_id, item)
        if not updated:
            raise HTTPException(status_code=404, detail="Item not found")
        return updated

    @delete(
        "/{item_id}",
        status_code=204,
        summary="Delete item",
        description="Remove an item from the inventory",
    )
    def delete_item(self, item_id: int):
        """Delete an item."""
        deleted = self.item_service.delete(item_id)
        if not deleted:
            raise HTTPException(status_code=404, detail="Item not found")


# Create FastAPI app
app = FastAPI(
    title="FastAPI Construct Example",
    description="Example API using fastapi-construct for dependency injection and controllers",
    version="1.0.0",
)

# Include controller router
app.include_router(ItemController.router)


# Root endpoint
@app.get("/", tags=["Root"])
def read_root():
    """Welcome endpoint."""
    return {
        "message": "Welcome to FastAPI Construct Example API",
        "docs": "/docs",
        "redoc": "/redoc",
    }


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)
