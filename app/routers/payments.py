import hashlib
import hmac
import json
import logging
import random
import uuid

from fastapi import APIRouter, Depends, Header, HTTPException, Request
from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.config import settings
from app.database import get_db
from app.deps import get_current_user
from app.models import Booking, BookingStatus, Payment, PaymentStatus, User, WebhookEvent
from app.schemas import PaymentIn, PaymentOut, WebhookIn

log = logging.getLogger("payments")
router = APIRouter(prefix="/payments", tags=["payments"])


@router.post("/", response_model=PaymentOut, status_code=201)
def make_payment(body: PaymentIn, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    """Mock payment: randomly SUCCESS/FAILED (or forced via `outcome`) and updates the booking."""
    booking = db.scalar(
        select(Booking)
        .where(Booking.id == body.booking_id, Booking.user_id == user.id)
        .with_for_update()  # serialises concurrent payments for one booking on PostgreSQL
    )
    if not booking:
        raise HTTPException(404, "Booking not found")
    if booking.status == BookingStatus.CONFIRMED:
        raise HTTPException(409, "Booking is already paid")
    if booking.status == BookingStatus.CANCELLED:
        raise HTTPException(409, "Cannot pay for a cancelled booking")

    outcome = body.outcome or random.choices(["SUCCESS", "FAILED"], weights=[80, 20])[0]
    payment = Payment(
        booking_id=booking.id, amount=booking.amount,
        status=PaymentStatus(outcome), provider_ref=uuid.uuid4().hex,
    )
    booking.status = BookingStatus.CONFIRMED if outcome == "SUCCESS" else BookingStatus.FAILED
    db.add(payment)
    db.commit()
    log.info("payment id=%s booking=%s status=%s", payment.id, booking.id, outcome)
    return payment


@router.post("/webhook/")
async def payment_webhook(
    request: Request,
    x_signature: str | None = Header(default=None),
    db: Session = Depends(get_db),
):
    """Idempotent webhook. Auth = HMAC-SHA256(raw body, WEBHOOK_SECRET) in `X-Signature`.

    Idempotency: `event_id` is stored under a UNIQUE key; a replay hits the constraint and returns 200
    without touching payments/bookings. State changes are also monotonic (a SUCCESS payment is never
    downgraded), so even a *different* event id cannot corrupt the booking.
    """
    raw = await request.body()
    expected = hmac.new(settings.WEBHOOK_SECRET.encode(), raw, hashlib.sha256).hexdigest()
    if not x_signature or not hmac.compare_digest(x_signature.encode(), expected.encode()):
        raise HTTPException(401, "Invalid webhook signature")
    try:
        event = WebhookIn.model_validate_json(raw)
    except ValidationError as e:
        raise HTTPException(422, json.loads(e.json()))

    payment = db.scalar(select(Payment).where(Payment.id == event.payment_id).with_for_update())
    if not payment:
        raise HTTPException(404, "Payment not found")

    db.add(WebhookEvent(event_id=event.event_id, payment_id=payment.id))
    try:
        db.flush()
    except IntegrityError:
        db.rollback()
        log.info("duplicate webhook event_id=%s ignored", event.event_id)
        return {"status": "duplicate", "detail": "event already processed"}

    new_status = PaymentStatus(event.status)
    result = "no_change"
    if payment.status == PaymentStatus.FAILED and new_status == PaymentStatus.SUCCESS:
        payment.status = PaymentStatus.SUCCESS
        booking = db.get(Booking, payment.booking_id)
        if booking.status in (BookingStatus.PENDING, BookingStatus.FAILED):
            booking.status = BookingStatus.CONFIRMED
            result = "applied"
        else:  # already CONFIRMED or CANCELLED: record payment, leave booking alone
            log.warning("late success for booking=%s in state=%s", booking.id, booking.status)
            result = "payment_updated_booking_unchanged"
    db.commit()
    return {"status": "processed", "result": result}
