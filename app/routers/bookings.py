from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.database import get_db
from app.deps import get_current_user
from app.models import Booking, BookingStatus, Centre, DiagnosticTest, User
from app.schemas import BookingIn, BookingOut, Page

router = APIRouter(prefix="/bookings", tags=["bookings"])


def _utc(dt: datetime) -> datetime:
    return dt.replace(tzinfo=timezone.utc) if dt.tzinfo is None else dt.astimezone(timezone.utc)


def _own_booking(db: Session, booking_id: int, user: User) -> Booking:
    # 404 (not 403) for other people's bookings so ids can't be probed
    b = db.scalar(select(Booking).where(Booking.id == booking_id, Booking.user_id == user.id))
    if not b:
        raise HTTPException(404, "Booking not found")
    return b


@router.post("/", response_model=BookingOut, status_code=201)
def create_booking(body: BookingIn, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    if not db.get(Centre, body.centre_id):
        raise HTTPException(404, "Centre not found")
    test = db.get(DiagnosticTest, body.test_id)
    if not test or test.centre_id != body.centre_id:
        raise HTTPException(404, "Test not offered at this centre")
    appt = _utc(body.appointment_at)
    if appt <= datetime.now(timezone.utc):
        raise HTTPException(422, "appointment_at must be in the future")
    dup = db.scalar(
        select(Booking.id).where(
            Booking.user_id == user.id,
            Booking.test_id == test.id,
            Booking.appointment_at == appt,
            Booking.status != BookingStatus.CANCELLED,
        )
    )
    if dup:
        raise HTTPException(409, "You already have a booking for this test at that time")
    booking = Booking(
        user_id=user.id, centre_id=test.centre_id, test_id=test.id,
        appointment_at=appt, amount=test.price, status=BookingStatus.PENDING,
    )
    db.add(booking)
    db.commit()
    return booking


@router.get("/", response_model=Page[BookingOut])
def list_bookings(
    status: BookingStatus | None = None,
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    q = select(Booking).where(Booking.user_id == user.id)
    if status:
        q = q.where(Booking.status == status)
    total = db.scalar(select(func.count()).select_from(q.subquery()))
    items = db.scalars(q.order_by(Booking.id.desc()).limit(limit).offset(offset)).all()
    return {"items": items, "total": total, "limit": limit, "offset": offset}


@router.get("/{booking_id}", response_model=BookingOut)
def get_booking(booking_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    return _own_booking(db, booking_id, user)


@router.post("/{booking_id}/cancel", response_model=BookingOut)
def cancel_booking(booking_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    booking = _own_booking(db, booking_id, user)
    if booking.status == BookingStatus.CANCELLED:
        raise HTTPException(409, "Booking already cancelled")
    booking.status = BookingStatus.CANCELLED  # refunds are out of scope for this simulation
    db.commit()
    return booking
