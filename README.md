# EVE Diagnostics API

Backend service for diagnostic test bookings with a simulated payment flow, built for the EVE Healthcare SDE Intern backend assignment.

**Stack:** Python 3.12, FastAPI, SQLAlchemy 2, PostgreSQL (SQLite fallback for local dev), JWT (PyJWT), bcrypt, pytest.

## Run locally

Verified locally via Option B (Python venv + SQLite). Option A (Docker) has not been tested in this environment.

### Option A — Docker (PostgreSQL)

```bash
docker compose up --build
docker compose exec api python -m scripts.seed   # optional sample data + admin user
```

### Option B — Plain Python (SQLite by default)

```bash
python -m venv .venv && source .venv/bin/activate      # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env   # or export vars; skip DATABASE_URL to use SQLite
export ADMIN_EMAILS=admin@example.com
python -m scripts.seed
uvicorn app.main:app --reload
```

Swagger UI: http://localhost:8000/docs (click Authorize and paste the JWT).

**Tests:** `pytest -q` (uses an in-memory SQLite database, no setup needed).

## Configuration (env vars)

| Var | Default | Purpose |
|---|---|---|
| DATABASE_URL | sqlite:///./eve.db | e.g. `postgresql+psycopg2://eve:eve@localhost:5432/eve` |
| SECRET_KEY | dev value | JWT signing key |
| WEBHOOK_SECRET | dev value | HMAC key for the payment webhook |
| ADMIN_EMAILS | (empty) | comma-separated emails that become admin on signup |
| ACCESS_TOKEN_EXPIRE_MINUTES | 60 | JWT lifetime |

## Development seed data

`python -m scripts.seed` creates sample centres/tests and one admin user (`admin@example.com` / `admin12345`) from `ADMIN_EMAILS`. These are development-only credentials — never use them, or deploy this seed script, in a production environment.

## Endpoints

| Method | Path | Auth | Notes |
|---|---|---|---|
| POST | /auth/signup | - | name, email, password (min 8) |
| POST | /auth/login | - | returns `access_token` |
| GET | /auth/me | user | |
| POST | /centres/ | admin | name, location |
| GET | /centres/?location=&limit=&offset= | user | paginated, includes tests + prices |
| GET | /centres/{id} | user | |
| POST | /centres/{id}/tests | admin | name, price |
| POST | /bookings/ | user | centre_id, test_id, appointment_at |
| GET | /bookings/?status=&limit=&offset= | user | own bookings only |
| GET | /bookings/{id} | user | 404 if not yours |
| POST | /bookings/{id}/cancel | user | |
| POST | /payments/ | user | mock payment; SUCCESS/FAILED updates booking |
| POST | /payments/webhook/ | HMAC | idempotent status update |

### Example flow

```bash
curl -X POST localhost:8000/auth/signup -H 'Content-Type: application/json' \
  -d '{"name":"Ravi","email":"ravi@example.com","password":"password123"}'

TOKEN=$(curl -s -X POST localhost:8000/auth/login -H 'Content-Type: application/json' \
  -d '{"email":"ravi@example.com","password":"password123"}' | python -c "import sys,json;print(json.load(sys.stdin)['access_token'])")

curl -X POST localhost:8000/bookings/ -H "Authorization: Bearer $TOKEN" -H 'Content-Type: application/json' \
  -d '{"centre_id":1,"test_id":1,"appointment_at":"2030-01-15T10:00:00Z"}'

curl -X POST localhost:8000/payments/ -H "Authorization: Bearer $TOKEN" -H 'Content-Type: application/json' \
  -d '{"booking_id":1}'          # add "outcome":"SUCCESS"|"FAILED" to force a result
```

Webhook (signature = hex HMAC-SHA256 of the raw body with `WEBHOOK_SECRET`):

```bash
BODY='{"event_id":"evt_1","payment_id":1,"status":"SUCCESS"}'
SIG=$(printf '%s' "$BODY" | openssl dgst -sha256 -hmac "$WEBHOOK_SECRET" | awk '{print $NF}')
curl -X POST localhost:8000/payments/webhook/ -H "X-Signature: $SIG" -H 'Content-Type: application/json' -d "$BODY"
```

## Database design

`users` 1-N `bookings`; `centres` 1-N `diagnostic_tests` (price is per centre); `bookings` reference a centre and a test; `bookings` 1-N `payments` (retries are allowed); `webhook_events` (PK = `event_id`) stores processed events.

- Amounts are `NUMERIC(10,2)`; the booking stores a price snapshot so later price changes don't alter it.
- Unique constraints: user email, (centre name, location), (centre, test name), payment `provider_ref`, webhook `event_id`.
- Index on `bookings(user_id, status)` and `centres.location`.

## Booking state machine

PENDING → CONFIRMED (payment SUCCESS)
PENDING → FAILED (payment FAILED)
FAILED → CONFIRMED (retry succeeds)
PENDING / FAILED / CONFIRMED → CANCELLED

Paying a CONFIRMED or CANCELLED booking returns 409.

## Idempotency & edge cases

- **Webhook idempotency:** `event_id` is inserted into `webhook_events` (unique). A replay violates the constraint, is rolled back, and gets `200 {"status":"duplicate"}` — no new payment, no booking change. The payment row is locked (`SELECT ... FOR UPDATE`) so concurrent duplicates serialise on PostgreSQL.
- **Monotonic transitions:** a SUCCESS payment is never downgraded by a later FAILED event; a late SUCCESS for a CANCELLED booking updates the payment but leaves the booking cancelled (logged).
- **Webhook authenticity:** HMAC signature, constant-time compare — 401 if missing or invalid.
- Invalid payloads → 422; unknown booking/payment/centre/test → 404; other users' bookings → 404 (no id probing); past appointment → 422; duplicate active booking (same user/test/time) → 409; duplicate signup → 409; same error for wrong email or password on login.

## Assumptions

- Only admins (`ADMIN_EMAILS`) create centres/tests; all authenticated users can browse and book.
- Cancelling does not simulate a refund. `/payments/` outcome is random (80% success) unless `outcome` is passed.
- The mock provider is represented by the signed webhook endpoint (callers must know `WEBHOOK_SECRET`).
- Tables are created at startup with `create_all`.

## What I'd improve with more time

Alembic migrations, refresh tokens, slot capacity per centre, Redis rate limiting and caching of centre listings, a background retry queue (Celery) for webhook processing, refunds on cancellation, structured JSON logging, a timestamp/replay-window check on webhooks, and a CI pipeline with a PostgreSQL service container.