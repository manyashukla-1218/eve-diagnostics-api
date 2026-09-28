from decimal import Decimal

from tests.conftest import auth_headers, future, make_booking, send_webhook


def test_booking_created_pending_with_price_snapshot(client, catalog):
    u = auth_headers(client)
    b = make_booking(client, u, catalog)
    assert b["status"] == "PENDING" and Decimal(b["amount"]) == Decimal("350.00")
    assert client.get("/bookings/", headers=u).json()["total"] == 1


def test_booking_validation(client, catalog):
    u = auth_headers(client)
    base = {"centre_id": catalog["centre_id"], "test_id": catalog["test_id"], "appointment_at": future()}
    assert client.post("/bookings/", json={**base, "appointment_at": future(-1)}, headers=u).status_code == 422
    assert client.post("/bookings/", json={**base, "centre_id": 999}, headers=u).status_code == 404
    assert client.post("/bookings/", json={**base, "test_id": 999}, headers=u).status_code == 404
    assert client.post("/bookings/", json={"centre_id": 1}, headers=u).status_code == 422
    assert client.post("/bookings/", json=base).status_code == 401
    same = {**base, "appointment_at": future(3)}
    assert client.post("/bookings/", json=same, headers=u).status_code == 201
    assert client.post("/bookings/", json=same, headers=u).status_code == 409


def test_cannot_touch_other_users_booking(client, catalog):
    a, b = auth_headers(client, "a@example.com"), auth_headers(client, "b@example.com")
    bk = make_booking(client, a, catalog)
    assert client.get(f"/bookings/{bk['id']}", headers=b).status_code == 404
    assert client.post(f"/bookings/{bk['id']}/cancel", headers=b).status_code == 404
    assert client.post("/payments/", json={"booking_id": bk["id"]}, headers=b).status_code == 404
    assert client.get("/bookings/", headers=b).json()["total"] == 0


def test_cancel(client, catalog):
    u = auth_headers(client)
    bk = make_booking(client, u, catalog)
    assert client.post(f"/bookings/{bk['id']}/cancel", headers=u).json()["status"] == "CANCELLED"
    assert client.post(f"/bookings/{bk['id']}/cancel", headers=u).status_code == 409
    assert client.post("/payments/", json={"booking_id": bk["id"]}, headers=u).status_code == 409


def test_payment_success_confirms_and_blocks_double_pay(client, catalog):
    u = auth_headers(client)
    bk = make_booking(client, u, catalog)
    p = client.post("/payments/", json={"booking_id": bk["id"], "outcome": "SUCCESS"}, headers=u)
    assert p.status_code == 201 and p.json()["status"] == "SUCCESS"
    assert client.get(f"/bookings/{bk['id']}", headers=u).json()["status"] == "CONFIRMED"
    assert client.post("/payments/", json={"booking_id": bk["id"]}, headers=u).status_code == 409


def test_payment_failure_then_retry(client, catalog):
    u = auth_headers(client)
    bk = make_booking(client, u, catalog)
    client.post("/payments/", json={"booking_id": bk["id"], "outcome": "FAILED"}, headers=u)
    assert client.get(f"/bookings/{bk['id']}", headers=u).json()["status"] == "FAILED"
    client.post("/payments/", json={"booking_id": bk["id"], "outcome": "SUCCESS"}, headers=u)
    assert client.get(f"/bookings/{bk['id']}", headers=u).json()["status"] == "CONFIRMED"


def test_payment_invalid_booking_and_body(client, catalog):
    u = auth_headers(client)
    assert client.post("/payments/", json={"booking_id": 999}, headers=u).status_code == 404
    assert client.post("/payments/", json={"booking_id": 1, "outcome": "MAYBE"}, headers=u).status_code == 422


def _failed_payment(client, catalog):
    u = auth_headers(client)
    bk = make_booking(client, u, catalog)
    p = client.post("/payments/", json={"booking_id": bk["id"], "outcome": "FAILED"}, headers=u).json()
    return u, bk, p


def test_webhook_is_idempotent(client, catalog):
    u, bk, p = _failed_payment(client, catalog)
    evt = {"event_id": "evt_1", "payment_id": p["id"], "status": "SUCCESS"}
    r1, r2, r3 = (send_webhook(client, evt) for _ in range(3))
    assert r1.json()["status"] == "processed" and r1.json()["result"] == "applied"
    assert r2.status_code == r3.status_code == 200 and r2.json()["status"] == "duplicate"
    assert client.get(f"/bookings/{bk['id']}", headers=u).json()["status"] == "CONFIRMED"
    assert client.post("/payments/", json={"booking_id": bk["id"]}, headers=u).status_code == 409


def test_webhook_never_downgrades_success(client, catalog):
    u = auth_headers(client)
    bk = make_booking(client, u, catalog)
    p = client.post("/payments/", json={"booking_id": bk["id"], "outcome": "SUCCESS"}, headers=u).json()
    r = send_webhook(client, {"event_id": "evt_x", "payment_id": p["id"], "status": "FAILED"})
    assert r.status_code == 200 and r.json()["result"] == "no_change"
    assert client.get(f"/bookings/{bk['id']}", headers=u).json()["status"] == "CONFIRMED"


def test_webhook_security_and_validation(client, catalog):
    _, _, p = _failed_payment(client, catalog)
    evt = {"event_id": "e", "payment_id": p["id"], "status": "SUCCESS"}
    assert send_webhook(client, evt, signature="bad").status_code == 401
    assert send_webhook(client, evt, secret="other-secret").status_code == 401
    assert client.post("/payments/webhook/", json=evt).status_code == 401
    assert send_webhook(client, {"event_id": "e2", "payment_id": 999, "status": "SUCCESS"}).status_code == 404
    assert send_webhook(client, {"event_id": "e3", "payment_id": p["id"], "status": "WEIRD"}).status_code == 422
    assert send_webhook(client, {"payment_id": p["id"]}).status_code == 422


def test_webhook_late_success_on_cancelled_booking(client, catalog):
    u, bk, p = _failed_payment(client, catalog)
    client.post(f"/bookings/{bk['id']}/cancel", headers=u)
    r = send_webhook(client, {"event_id": "late", "payment_id": p["id"], "status": "SUCCESS"})
    assert r.json()["result"] == "payment_updated_booking_unchanged"
    assert client.get(f"/bookings/{bk['id']}", headers=u).json()["status"] == "CANCELLED"
