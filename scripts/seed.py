"""Seed an admin user and sample centres:  python -m scripts.seed"""
from decimal import Decimal

from sqlalchemy import select

from app.database import Base, SessionLocal, engine
from app.models import Centre, DiagnosticTest, User
from app.security import hash_password

Base.metadata.create_all(engine)
with SessionLocal() as db:
    if not db.scalar(select(User).where(User.email == "admin@example.com")):
        db.add(User(name="Admin", email="admin@example.com", password_hash=hash_password("admin12345"), is_admin=True))
    if not db.scalar(select(Centre)):
        for name, loc, tests in [
            ("City Diagnostics", "Jabalpur", [("CBC", "350.00"), ("Lipid Profile", "600.00")]),
            ("HealthFirst Labs", "Bhopal", [("CBC", "300.00"), ("Thyroid Panel", "750.00")]),
        ]:
            db.add(Centre(name=name, location=loc, tests=[DiagnosticTest(name=n, price=Decimal(p)) for n, p in tests]))
    db.commit()
print("seeded: admin@example.com / admin12345")
