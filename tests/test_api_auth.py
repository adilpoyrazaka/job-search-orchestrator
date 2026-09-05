from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient

from src.api.auth import OPERATOR_TOKEN, require_operator

app = FastAPI()


@app.get("/guarded")
def guarded(_: None = Depends(require_operator)):
    return {"ok": True}


client = TestClient(app)


def test_missing_token_is_401_with_challenge():
    r = client.get("/guarded")
    assert r.status_code == 401
    assert r.headers["WWW-Authenticate"] == "Bearer"


def test_wrong_token_is_401_indistinguishable_from_missing():
    missing = client.get("/guarded")
    wrong = client.get("/guarded", headers={"Authorization": "Bearer nope"})
    assert wrong.status_code == 401
    assert wrong.json() == missing.json()


def test_right_token_passes():
    r = client.get("/guarded", headers={"Authorization": f"Bearer {OPERATOR_TOKEN}"})
    assert r.status_code == 200 and r.json() == {"ok": True}
