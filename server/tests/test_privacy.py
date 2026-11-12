from fastapi.testclient import TestClient

from server.main import app


def test_privacy_policy_is_public_and_contains_required_disclosures():
    response = TestClient(app).get("/privacy")
    assert response.status_code == 200
    assert "Drishti Privacy Policy" in response.text
    assert "SIH26171 project team" in response.text
    assert "does not sell user data" in response.text
    assert "Chrome Web Store User Data Policy" in response.text
    assert "127.0.0.1" in response.text
    assert "raw screenshot is never sent" in response.text
    assert "~/.drishti/tasks" in response.text
