from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, selectinload

from app.database import get_db
from app.deps import get_current_user, require_admin
from app.models import Centre, DiagnosticTest
from app.schemas import CentreIn, CentreOut, Page, TestIn, TestOut

router = APIRouter(prefix="/centres", tags=["centres"], dependencies=[Depends(get_current_user)])


@router.post("/", response_model=CentreOut, status_code=201, dependencies=[Depends(require_admin)])
def create_centre(body: CentreIn, db: Session = Depends(get_db)):
    centre = Centre(name=body.name.strip(), location=body.location.strip())
    db.add(centre)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(409, "Centre with this name and location already exists")
    return centre


@router.get("/", response_model=Page[CentreOut])
def list_centres(
    location: str | None = None,
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
):
    q = select(Centre)
    if location:
        q = q.where(func.lower(Centre.location) == location.strip().lower())
    total = db.scalar(select(func.count()).select_from(q.subquery()))
    items = db.scalars(q.options(selectinload(Centre.tests)).order_by(Centre.id).limit(limit).offset(offset)).all()
    return {"items": items, "total": total, "limit": limit, "offset": offset}


@router.get("/{centre_id}", response_model=CentreOut)
def get_centre(centre_id: int, db: Session = Depends(get_db)):
    centre = db.scalar(select(Centre).options(selectinload(Centre.tests)).where(Centre.id == centre_id))
    if not centre:
        raise HTTPException(404, "Centre not found")
    return centre


@router.post("/{centre_id}/tests", response_model=TestOut, status_code=201, dependencies=[Depends(require_admin)])
def add_test(centre_id: int, body: TestIn, db: Session = Depends(get_db)):
    if not db.get(Centre, centre_id):
        raise HTTPException(404, "Centre not found")
    test = DiagnosticTest(centre_id=centre_id, name=body.name.strip(), price=body.price)
    db.add(test)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(409, "This centre already offers a test with that name")
    return test
