from fastapi import FastAPI, Response
from fastapi.testclient import TestClient

from fastapi_construct import controller, get


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
