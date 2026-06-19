"""Master data CRUD: divisions, banks, salesmen, customers, lawyers, case types."""

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.core.deps import require_permission
from app.core.permissions import MASTERS_READ, MASTERS_WRITE
from app.db.session import get_db
from app.models.masters import Bank, CaseType, Customer, Division, Lawyer, Salesman
from app.models.user import User
from app.schemas.masters import (
    BankCreate,
    BankRead,
    BankUpdate,
    CaseTypeCreate,
    CaseTypeRead,
    CaseTypeUpdate,
    CustomerCreate,
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
from app.services import audit_service

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
) -> None:
    @router.get(path, response_model=list[read_schema])
    def list_items(
        db: Session = Depends(get_db),
        _: User = Depends(require_permission(MASTERS_READ)),
    ):
        return [read_schema.model_validate(x) for x in db.query(model).order_by(order_by).all()]

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
)
_register(
    router,
    path="/lawyers",
    model=Lawyer,
    read_schema=LawyerRead,
    create_schema=LawyerCreate,
    update_schema=LawyerUpdate,
    order_by=Lawyer.name,
    unique_field=None,
)
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
