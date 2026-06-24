"""Report registry, JSON data, and Excel / PDF downloads."""

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import Response
from sqlalchemy.orm import Session

from app.core.deps import get_current_user, require_permission
from app.core.permissions import has_permission
from app.db.session import get_db
from app.models.user import User
from app.services import excel_renderer, pdf_renderer, reports

router = APIRouter(prefix="/reports", tags=["reports"])


@router.get("")
def list_reports(_: User = Depends(get_current_user)) -> list[dict]:
    return reports.list_reports()


def _run(request: Request, db: Session, user: User, key: str) -> dict:
    rd = reports.get_report(key)
    if not rd:
        raise HTTPException(status_code=404, detail="Report not found")
    perms = user.role.permissions if user.role else []
    if not user.is_super and not has_permission(perms, rd.permission):
        raise HTTPException(
            status_code=403, detail=f"Missing permission: {rd.permission}"
        )
    params: dict[str, str] = {}
    for p in rd.params:
        val = request.query_params.get(p.name)
        if val is not None:
            params[p.name] = val
    data = rd.query(db, user, params)
    data["params"] = params
    data["key"] = key
    data["landscape"] = rd.landscape
    return data


@router.get("/{key}")
def run_report(
    key: str,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict:
    return _run(request, db, user, key)


@router.get("/{key}.xlsx")
def export_xlsx(
    key: str,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> Response:
    data = _run(request, db, user, key)
    blob = excel_renderer.render_xlsx(
        title=data["title"],
        subtitle=data["subtitle"],
        columns=data["columns"],
        rows=data["rows"],
        params=data["params"],
    )
    fname = f"{key}-{datetime.now(timezone.utc):%Y%m%d-%H%M}.xlsx"
    return Response(
        content=blob,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="{fname}"'},
    )


@router.get("/{key}.pdf")
def export_pdf(
    key: str,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> Response:
    data = _run(request, db, user, key)
    blob = pdf_renderer.render_pdf(
        title=data["title"],
        subtitle=data["subtitle"],
        columns=data["columns"],
        rows=data["rows"],
        params=data["params"],
        landscape_mode=data.get("landscape"),
    )
    fname = f"{key}-{datetime.now(timezone.utc):%Y%m%d-%H%M}.pdf"
    return Response(
        content=blob,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{fname}"'},
    )
