import re
from datetime import datetime
from decimal import Decimal
from typing import Generic, Literal, TypeVar

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.models import BookingStatus, PaymentStatus

T = TypeVar("T")
_EMAIL = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def _clean_email(v: str) -> str:
    v = v.strip().lower()
    if not _EMAIL.match(v):
        raise ValueError("invalid email address")
    return v


class ORM(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class Page(BaseModel, Generic[T]):
    items: list[T]
    total: int
    limit: int
    offset: int


class SignupIn(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    email: str
    password: str = Field(min_length=8, max_length=128)

    @field_validator("email")
    @classmethod
    def _check_email(cls, v: str) -> str:
        return _clean_email(v)


class LoginIn(BaseModel):
    email: str
    password: str

    @field_validator("email")
    @classmethod
    def _check_email(cls, v: str) -> str:
        return _clean_email(v)


class UserOut(ORM):
    id: int
    name: str
    email: str
    is_admin: bool


class TokenOut(BaseModel):
    access_token: str
    token_type: str = "bearer"


class CentreIn(BaseModel):
    name: str = Field(min_length=1, max_length=150)
    location: str = Field(min_length=1, max_length=150)


class TestIn(BaseModel):
    name: str = Field(min_length=1, max_length=150)
    price: Decimal = Field(gt=0, max_digits=10, decimal_places=2)


class TestOut(ORM):
    id: int
    name: str
    price: Decimal


class CentreOut(ORM):
    id: int
    name: str
    location: str
    tests: list[TestOut] = []


class BookingIn(BaseModel):
    centre_id: int
    test_id: int
    appointment_at: datetime


class BookingOut(ORM):
    id: int
    user_id: int
    centre_id: int
    test_id: int
    appointment_at: datetime
    amount: Decimal
    status: BookingStatus
    created_at: datetime


class PaymentIn(BaseModel):
    booking_id: int
    # optional: force an outcome (handy for demos/tests); random if omitted
    outcome: Literal["SUCCESS", "FAILED"] | None = None


class PaymentOut(ORM):
    id: int
    booking_id: int
    amount: Decimal
    status: PaymentStatus
    provider_ref: str
    created_at: datetime


class WebhookIn(BaseModel):
    event_id: str = Field(min_length=1, max_length=100)
    payment_id: int
    status: Literal["SUCCESS", "FAILED"]
