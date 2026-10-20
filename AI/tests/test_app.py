from fastapi.testclient import TestClient

from AI.inference.app import app

client = TestClient(app)


def test_health_does_not_force_model_load() -> None:
    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok", "model_loaded": False}


def test_invalid_image_is_rejected_before_model_load() -> None:
    response = client.post(
        "/predict",
        files={"file": ("broken.jpg", b"not an image", "image/jpeg")},
    )

    assert response.status_code == 400
    assert response.json()["detail"] == "invalid or unsupported image"


def test_reset_does_not_force_model_load() -> None:
    response = client.post("/reset")

    assert response.status_code == 200
    assert response.json() == {"status": "reset"}
