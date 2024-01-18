import os
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, StaticPool
from sqlalchemy.orm import sessionmaker
from main import app, get_db, Base
from models.db import UserItem

DATABASE_URL = "sqlite:///:memory:"
TEST_PASSWORD = os.getenv("TEST_PASSWORD")
HASHED_PASSWORD = os.getenv("TEST_HASH_PASSWORD")

USERNAME = "username"
BEARER = "bearer"
ACCESS_TOKEN = "access_token"
TOKEN_TYPE = "token_type"
DETAIL = "detail"
TEST_ROUTE = {
    "gym_name": "test_gym",
    "date": "2024-01-18T00:00:00",
    "difficulty": "string",
    "characteristics": [{"name": "dyno"}],
    "attempts": 0,
    "sent": True,
    "notes": "string",
}


engine = create_engine(
    DATABASE_URL, connect_args={"check_same_thread": False}, poolclass=StaticPool
)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

client = TestClient(app)


def override_get_db():
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()


def setup():
    Base.metadata.create_all(bind=engine)
    session = TestingSessionLocal()
    user = UserItem(username=USERNAME, hashed_password=HASHED_PASSWORD)
    session.add(user)
    session.commit()


def teardown():
    Base.metadata.drop_all(bind=engine)


app.dependency_overrides[get_db] = override_get_db


def test_get_root():
    res = client.get("/")
    assert res.json() == {"detail": "OK", "status_code": 200}


def post_token_res():
    if not TEST_PASSWORD:
        raise ValueError("Password not provided")
    res = client.post("/token", data={"username": USERNAME, "password": TEST_PASSWORD})
    return res


def get_token(res):
    res_json = res.json()
    return res_json[ACCESS_TOKEN]


def construct_headers(token: str):
    return {"Authorization": f"Bearer {token}"}


def test_post_token():
    res = post_token_res()
    assert res.status_code == 200
    res_json = res.json()
    assert len(res_json[ACCESS_TOKEN])
    assert res_json[TOKEN_TYPE] == BEARER


def test_get_me():
    token_res = post_token_res()
    token = get_token(token_res)
    res = client.get("/users/me", headers=construct_headers(token))
    assert res.status_code == 200
    assert res.json() == {"id": 1, "username": USERNAME}


def test_get_own_items():
    token_res = post_token_res()
    token = get_token(token_res)
    res = client.get("/users/me/items", headers=construct_headers(token))
    assert res.status_code == 200
    assert len(res.json()) == 0


def test_register_invalid_body():
    username = "short"
    password = ""
    res = client.post(
        f"/register?username={username}&password={password}",
    )
    assert res.status_code == 422


def test_register_valid_username_invalid_pw():
    username = "123456"
    password = "12345678"
    res = client.post(
        f"/register?username={username}&password={password}",
    )
    assert res.status_code == 422


def test_register_valid():
    username = "new_user"
    password = "lowerUpper1"
    res = client.post(
        f"/register?username={username}&password={password}",
    )
    assert res.json() == {"status_code": 200, "detail": "User creation successful"}


def test_post_routes_unauthorized():
    res = client.post("/routes")
    assert res.status_code == 401


def test_post_routes_authorized():
    token_res = post_token_res()
    token = get_token(token_res)
    res = client.post("/routes", headers=construct_headers(token), json=TEST_ROUTE)
    assert res.json() == {"status_code": 200, "detail": "Success"}


def test_get_routes_by_characteristic():
    res = client.get("/routes/dyno")
    assert res.json() == [TEST_ROUTE]


def test_get_routes():
    res = client.get("/routes")
    assert res.status_code == 200
    items = res.json()
    assert len(items) == 1


def test_delete_route():
    token_res = post_token_res()
    token = get_token(token_res)
    res = client.delete("/routes/1", headers=construct_headers(token))
    res_json = res.json()
    assert res.status_code == 200
    assert res_json[DETAIL] == "Route 1 deleted"
