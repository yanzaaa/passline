import pytest
from fastapi.testclient import TestClient
from passline.dashboard.app import app
def test_upload_empty():
    client = TestClient(app)
    response = client.post("/api/upload", files={"file": ("test.srt", b"")})
    assert response.status_code == 422
    assert response.json()["detail"] == "not a readable subtitle file"

def test_upload_binary():
    client = TestClient(app)
    import os
    response = client.post("/api/upload", files={"file": ("test.srt", os.urandom(5000))})
    assert response.status_code == 422
    assert response.json()["detail"] == "not a readable subtitle file"
