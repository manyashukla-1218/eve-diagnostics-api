import os

os.environ.update(BCRYPT_ROUNDS="4", ADMIN_EMAILS="admin@example.com", WEBHOOK_SECRET="test-secret")

import hashlib  # noqa: E402
import hmac  # noqa: E402
import json  # noqa: E402
from datetime import datetime, timedelta, timezone  # noqa: E402

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import create_engine  # noqa: E402
from sqlalchemy.orm import sessionmaker  # noqa: E402
from sqlalchemy.pool import StaticPool  # noqa: E402

from app.database import Base, get_db  # noqa: E402
from app.main import app  # noqa: E402


@pytest.fixture()
def client():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)

    def override():
        db = Session()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override
    yield TestClient(app)
    app.dependency_overrides.clear()


def auth_headers(client, email="user@example.com"):
    client.post("/auth/signup", json={"name": "T", "email": email, "password": "password123"})
    token = client.post("/auth/login", json={"email": email, "password": "password123"}).json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture()
def catalog(client):
    admin = auth_headers(client, "admin@example.com")
    c = client.post("/centres/", json={"name": "Lab A", "location": "Jabalpur"}, headers=admin).json()
    t = client.post(f"/centres/{c['id']}/tests", json={"name": "CBC", "price": "350.00"}, headers=admin).json()
    return {"centre_id": c["id"], "test_id": t["id"], "admin": admin}


def future(days=2):
    return (datetime.now(timezone.utc) + timedelta(days=days)).isoformat()


def make_booking(client, headers, catalog, days=2):
    r = client.post(
        "/bookings/",
        json={"centre_id": catalog["centre_id"], "test_id": catalog["test_id"], "appointment_at": future(days)},
        headers=headers,
    )
    assert r.status_code == 201, r.text
    return r.json()


def send_webhook(client, payload: dict, secret="test-secret", signature=None):
    raw = json.dumps(payload).encode()
    sig = signature or hmac.new(secret.encode(), raw, hashlib.sha256).hexdigest()
    return client.post(
        "/payments/webhook/", content=raw, headers={"X-Signature": sig, "Content-Type": "application/json"}
    )
