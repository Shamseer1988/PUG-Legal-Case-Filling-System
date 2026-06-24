"""Master data CRUD: divisions, banks, salesmen, customers, lawyers, case types."""

from typing import Any

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from fastapi.responses import FileResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.core.data_scope import allowed_division_ids
from app.core.deps import require_permission
from app.core.permissions import MASTERS_READ, MASTERS_WRITE
from app.db.session import get_db
from app.models.masters import (
    Bank,
    CaseType,
    Customer,
    CustomerPartner,
    Division,
    Lawyer,
    LawyerDivisionMap,
    Salesman,
)
from app.models.user import User
from app.schemas.masters import (
    BankCreate,
    BankRead,
    BankUpdate,
    CaseTypeCreate,
    CaseTypeRead,
    CaseTypeUpdate,
    CustomerCreate,
    CustomerPartnerCreate,
    CustomerPartnerRead,
    CustomerPartnerUpdate,
    CustomerRead,
    CustomerUpdate,
    DivisionCreate,
    DivisionRead,
    DivisionUpdate,
    LawyerCreate,
    LawyerRead,
    LawyerUpdate,
    SalesmanCreate,
    SalesmanRead,
    SalesmanUpdate,
)
from app.services import audit_service, storage

router = APIRouter(tags=["masters"])


def _register(
    router: APIRouter,
    *,
    path: str,
    model: type,
    read_schema: type[BaseModel],
    create_schema: type[BaseModel],
    update_schema: type[BaseModel],
    order_by: Any,
    unique_field: str | None = None,
    scope_column: Any | None = None,
) -> None:
    @router.get(path, response_model=list[read_schema])
    def list_items(
        db: Session = Depends(get_db),
        user: User = Depends(require_permission(MASTERS_READ)),
    ):
        # Phase 39: division-scope the master list when the model
        # carries a division and the user is not cross-division.
        # ``allowed_division_ids`` returns None for super/is_all_divisions/
        # wildcard users so they keep seeing the full master.
        q = db.query(model)
        if scope_column is not None:
            allowed = allowed_division_ids(user)
            if allowed is not None:
                if not allowed:
                    return []
                q = q.filter(scope_column.in_(allowed))
        return [read_schema.model_validate(x) for x in q.order_by(order_by).all()]

    entity_type = model.__name__

    @router.post(path, response_model=read_schema, status_code=status.HTTP_201_CREATED)
    def create_item(
        payload: create_schema,
        db: Session = Depends(get_db),
        _: User = Depends(require_permission(MASTERS_WRITE)),
    ):
        if unique_field:
            value = getattr(payload, unique_field)
            if db.query(model).filter(getattr(model, unique_field) == value).first():
                raise HTTPException(
                    status_code=409, detail=f"{unique_field} already exists: {value}"
                )
        obj = model(**payload.model_dump())
        db.add(obj)
        db.flush()
        audit_service.audit_create(
            db,
            entity_type,
            obj.id,
            f"Created {entity_type}: {getattr(obj, 'name', '') or getattr(obj, 'code', obj.id)}",
            audit_service.snapshot(obj),
        )
        db.commit()
        db.refresh(obj)
        return read_schema.model_validate(obj)

    @router.get(path + "/{item_id}", response_model=read_schema)
    def get_item(
        item_id: int,
        db: Session = Depends(get_db),
        _: User = Depends(require_permission(MASTERS_READ)),
    ):
        obj = db.get(model, item_id)
        if not obj:
            raise HTTPException(status_code=404, detail="Not found")
        return read_schema.model_validate(obj)

    @router.patch(path + "/{item_id}", response_model=read_schema)
    def update_item(
        item_id: int,
        payload: update_schema,
        db: Session = Depends(get_db),
        _: User = Depends(require_permission(MASTERS_WRITE)),
    ):
        obj = db.get(model, item_id)
        if not obj:
            raise HTTPException(status_code=404, detail="Not found")
        before = audit_service.snapshot(obj)
        for k, v in payload.model_dump(exclude_unset=True).items():
            setattr(obj, k, v)
        db.flush()
        after = audit_service.snapshot(obj)
        audit_service.audit_update(
            db,
            entity_type,
            obj.id,
            f"Updated {entity_type} #{obj.id}",
            before,
            after,
        )
        db.commit()
        db.refresh(obj)
        return read_schema.model_validate(obj)

    @router.delete(path + "/{item_id}", status_code=status.HTTP_204_NO_CONTENT)
    def delete_item(
        item_id: int,
        db: Session = Depends(get_db),
        _: User = Depends(require_permission(MASTERS_WRITE)),
    ):
        obj = db.get(model, item_id)
        if not obj:
            raise HTTPException(status_code=404, detail="Not found")
        before = audit_service.snapshot(obj)
        label = getattr(obj, "name", "") or getattr(obj, "code", obj.id)
        audit_service.audit_delete(
            db, entity_type, obj.id, f"Deleted {entity_type}: {label}", before
        )
        db.delete(obj)
        db.commit()


_register(
    router,
    path="/divisions",
    model=Division,
    read_schema=DivisionRead,
    create_schema=DivisionCreate,
    update_schema=DivisionUpdate,
    order_by=Division.code,
    unique_field="code",
    # Phase 39: non-super users only see divisions they're mapped to.
    scope_column=Division.id,
)
_register(
    router,
    path="/banks",
    model=Bank,
    read_schema=BankRead,
    create_schema=BankCreate,
    update_schema=BankUpdate,
    order_by=Bank.code,
    unique_field="code",
)
_register(
    router,
    path="/salesmen",
    model=Salesman,
    read_schema=SalesmanRead,
    create_schema=SalesmanCreate,
    update_schema=SalesmanUpdate,
    order_by=Salesman.code,
    unique_field="code",
    scope_column=Salesman.division_id,
)
_register(
    router,
    path="/customers",
    model=Customer,
    read_schema=CustomerRead,
    create_schema=CustomerCreate,
    update_schema=CustomerUpdate,
    order_by=Customer.code,
    unique_field="code",
    scope_column=Customer.division_id,
)
# ---------- Lawyers (custom: division M2M + "All Companies" flag) ----------
def _lawyer_to_read(obj: Lawyer) -> LawyerRead:
    return LawyerRead(
        id=obj.id,
        name=obj.name,
        firm=obj.firm,
        email=obj.email,
        phone=obj.phone,
        is_active=obj.is_active,
        is_all_divisions=obj.is_all_divisions,
        division_ids=[d.id for d in obj.divisions],
    )


def _set_lawyer_divisions(db: Session, lawyer: Lawyer, division_ids: list[int]) -> None:
    db.query(LawyerDivisionMap).filter(LawyerDivisionMap.lawyer_id == lawyer.id).delete()
    for did in division_ids or []:
        db.add(LawyerDivisionMap(lawyer_id=lawyer.id, division_id=did))


@router.get("/lawyers", response_model=list[LawyerRead])
def list_lawyers(
    db: Session = Depends(get_db),
    _: User = Depends(require_permission(MASTERS_READ)),
) -> list[LawyerRead]:
    return [_lawyer_to_read(x) for x in db.query(Lawyer).order_by(Lawyer.name).all()]


@router.post("/lawyers", response_model=LawyerRead, status_code=status.HTTP_201_CREATED)
def create_lawyer(
    payload: LawyerCreate,
    db: Session = Depends(get_db),
    _: User = Depends(require_permission(MASTERS_WRITE)),
) -> LawyerRead:
    data = payload.model_dump()
    division_ids = data.pop("division_ids", [])
    obj = Lawyer(**data)
    db.add(obj)
    db.flush()
    if not obj.is_all_divisions:
        _set_lawyer_divisions(db, obj, division_ids)
    audit_service.audit_create(
        db,
        "Lawyer",
        obj.id,
        f"Created Lawyer: {obj.name}",
        {**audit_service.snapshot(obj), "division_ids": division_ids},
    )
    db.commit()
    db.refresh(obj)
    return _lawyer_to_read(obj)


@router.get("/lawyers/{item_id}", response_model=LawyerRead)
def get_lawyer(
    item_id: int,
    db: Session = Depends(get_db),
    _: User = Depends(require_permission(MASTERS_READ)),
) -> LawyerRead:
    obj = db.get(Lawyer, item_id)
    if not obj:
        raise HTTPException(status_code=404, detail="Not found")
    return _lawyer_to_read(obj)


@router.patch("/lawyers/{item_id}", response_model=LawyerRead)
def update_lawyer(
    item_id: int,
    payload: LawyerUpdate,
    db: Session = Depends(get_db),
    _: User = Depends(require_permission(MASTERS_WRITE)),
) -> LawyerRead:
    obj = db.get(Lawyer, item_id)
    if not obj:
        raise HTTPException(status_code=404, detail="Not found")
    before = {**audit_service.snapshot(obj), "division_ids": [d.id for d in obj.divisions]}
    data = payload.model_dump(exclude_unset=True)
    division_ids = data.pop("division_ids", None)
    for k, v in data.items():
        setattr(obj, k, v)
    if obj.is_all_divisions:
        # "All Companies" wins — drop any per-division mappings so we
        # don't leak them back the next time the flag is unset.
        _set_lawyer_divisions(db, obj, [])
    elif division_ids is not None:
        _set_lawyer_divisions(db, obj, division_ids)
    db.flush()
    after = {**audit_service.snapshot(obj), "division_ids": [d.id for d in obj.divisions]}
    audit_service.audit_update(db, "Lawyer", obj.id, f"Updated Lawyer #{obj.id}", before, after)
    db.commit()
    db.refresh(obj)
    return _lawyer_to_read(obj)


@router.delete("/lawyers/{item_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_lawyer(
    item_id: int,
    db: Session = Depends(get_db),
    _: User = Depends(require_permission(MASTERS_WRITE)),
) -> None:
    obj = db.get(Lawyer, item_id)
    if not obj:
        raise HTTPException(status_code=404, detail="Not found")
    audit_service.audit_delete(db, "Lawyer", obj.id, f"Deleted Lawyer: {obj.name}", audit_service.snapshot(obj))
    db.delete(obj)
    db.commit()
_register(
    router,
    path="/case-types",
    model=CaseType,
    read_schema=CaseTypeRead,
    create_schema=CaseTypeCreate,
    update_schema=CaseTypeUpdate,
    order_by=CaseType.code,
    unique_field="code",
)


# ---------- Customer partners (Phase 40) ----------
def _scope_customer_or_404(
    db: Session, user: User, customer_id: int
) -> Customer:
    """Look up the customer with the same division scoping the
    customers list endpoint already enforces, so an Accountant
    can't peek at another division's partners through this route.
    """
    cust = db.get(Customer, customer_id)
    if not cust:
        raise HTTPException(status_code=404, detail="Customer not found")
    allowed = allowed_division_ids(user)
    if allowed is not None:
        if not allowed or cust.division_id not in allowed:
            raise HTTPException(status_code=404, detail="Customer not found")
    return cust


@router.get(
    "/customers/{customer_id}/partners",
    response_model=list[CustomerPartnerRead],
)
def list_customer_partners(
    customer_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission(MASTERS_READ)),
) -> list[CustomerPartnerRead]:
    cust = _scope_customer_or_404(db, user, customer_id)
    return [CustomerPartnerRead.model_validate(p) for p in cust.partners]


@router.post(
    "/customers/{customer_id}/partners",
    response_model=CustomerPartnerRead,
    status_code=status.HTTP_201_CREATED,
)
def create_customer_partner(
    customer_id: int,
    payload: CustomerPartnerCreate,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission(MASTERS_WRITE)),
) -> CustomerPartnerRead:
    cust = _scope_customer_or_404(db, user, customer_id)
    p = CustomerPartner(customer_id=cust.id, **payload.model_dump())
    db.add(p)
    db.flush()
    audit_service.audit_create(
        db,
        "CustomerPartner",
        p.id,
        f"Added partner {p.name} to customer {cust.code}",
        audit_service.snapshot(p),
    )
    db.commit()
    db.refresh(p)
    return CustomerPartnerRead.model_validate(p)


@router.patch(
    "/customers/{customer_id}/partners/{partner_id}",
    response_model=CustomerPartnerRead,
)
def update_customer_partner(
    customer_id: int,
    partner_id: int,
    payload: CustomerPartnerUpdate,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission(MASTERS_WRITE)),
) -> CustomerPartnerRead:
    cust = _scope_customer_or_404(db, user, customer_id)
    p = db.get(CustomerPartner, partner_id)
    if not p or p.customer_id != cust.id:
        raise HTTPException(status_code=404, detail="Partner not found")
    before = audit_service.snapshot(p)
    for k, v in payload.model_dump(exclude_unset=True).items():
        setattr(p, k, v)
    db.flush()
    audit_service.audit_update(
        db, "CustomerPartner", p.id, f"Updated partner {p.name}", before,
        audit_service.snapshot(p),
    )
    db.commit()
    db.refresh(p)
    return CustomerPartnerRead.model_validate(p)


@router.delete(
    "/customers/{customer_id}/partners/{partner_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
def delete_customer_partner(
    customer_id: int,
    partner_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission(MASTERS_WRITE)),
) -> None:
    cust = _scope_customer_or_404(db, user, customer_id)
    p = db.get(CustomerPartner, partner_id)
    if not p or p.customer_id != cust.id:
        raise HTTPException(status_code=404, detail="Partner not found")
    audit_service.audit_delete(
        db, "CustomerPartner", p.id, f"Removed partner {p.name}",
        audit_service.snapshot(p),
    )
    # Drop the ID document file on disk - the case_cheque_signatories
    # rows cascade automatically via the FK.
    if p.id_document_stored:
        storage.delete_partner_id_document(p.id, p.id_document_stored)
    db.delete(p)
    db.commit()


@router.post(
    "/customers/{customer_id}/partners/{partner_id}/id-document",
    response_model=CustomerPartnerRead,
)
def upload_partner_id_document(
    customer_id: int,
    partner_id: int,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    user: User = Depends(require_permission(MASTERS_WRITE)),
) -> CustomerPartnerRead:
    cust = _scope_customer_or_404(db, user, customer_id)
    p = db.get(CustomerPartner, partner_id)
    if not p or p.customer_id != cust.id:
        raise HTTPException(status_code=404, detail="Partner not found")
    # Drop the previous file (storage helper also does this, but
    # being explicit makes the audit trail cleaner).
    if p.id_document_stored:
        storage.delete_partner_id_document(p.id, p.id_document_stored)
    stored, size = storage.save_partner_id_document(p.id, file)
    p.id_document_filename = file.filename or stored
    p.id_document_stored = stored
    p.id_document_mime = file.content_type or "application/octet-stream"
    p.id_document_size = size
    db.commit()
    db.refresh(p)
    return CustomerPartnerRead.model_validate(p)


@router.get(
    "/customers/{customer_id}/partners/{partner_id}/id-document",
)
def view_partner_id_document(
    customer_id: int,
    partner_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission(MASTERS_READ)),
) -> FileResponse:
    cust = _scope_customer_or_404(db, user, customer_id)
    p = db.get(CustomerPartner, partner_id)
    if not p or p.customer_id != cust.id:
        raise HTTPException(status_code=404, detail="Partner not found")
    if not p.id_document_stored:
        raise HTTPException(status_code=404, detail="No ID document on file")
    path = storage.get_partner_id_document_path(p.id, p.id_document_stored)
    if not path.exists():
        raise HTTPException(status_code=410, detail="File missing on disk")
    return FileResponse(
        path,
        filename=p.id_document_filename,
        media_type=p.id_document_mime or "application/octet-stream",
        content_disposition_type="inline",
    )


@router.delete(
    "/customers/{customer_id}/partners/{partner_id}/id-document",
    response_model=CustomerPartnerRead,
)
def delete_partner_id_document(
    customer_id: int,
    partner_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission(MASTERS_WRITE)),
) -> CustomerPartnerRead:
    cust = _scope_customer_or_404(db, user, customer_id)
    p = db.get(CustomerPartner, partner_id)
    if not p or p.customer_id != cust.id:
        raise HTTPException(status_code=404, detail="Partner not found")
    if p.id_document_stored:
        storage.delete_partner_id_document(p.id, p.id_document_stored)
    p.id_document_filename = ""
    p.id_document_stored = ""
    p.id_document_mime = ""
    p.id_document_size = 0
    db.commit()
    db.refresh(p)
    return CustomerPartnerRead.model_validate(p)
