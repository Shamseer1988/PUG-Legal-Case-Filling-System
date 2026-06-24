"""Jinja2 renderer for the Phase 2 case-print HTML view + ReportLab PDF."""

import io
from datetime import datetime, timezone
from decimal import Decimal
from functools import lru_cache
from pathlib import Path
from typing import Any

from jinja2 import Environment, FileSystemLoader, select_autoescape
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.pdfgen.canvas import Canvas
from reportlab.platypus import (
    BaseDocTemplate,
    Frame,
    Image,
    PageTemplate,
    Paragraph,
    Spacer,
    Table,
    TableStyle,
)
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.case import Case
from app.models.masters import Bank, CaseType, Customer, Division, Lawyer, Salesman
from app.models.user import User
from app.services import storage

TEMPLATES = Path(__file__).resolve().parent.parent / "templates"

# ---------- Brand palette (shared with pdf_renderer) ----------
NAVY = colors.HexColor("#1a234a")
NAVY_DARK = colors.HexColor("#0b1020")
GOLD = colors.HexColor("#c9a14a")
GOLD_LIGHT = colors.HexColor("#f5ecd7")
LIGHT = colors.HexColor("#f7f8fc")
BORDER = colors.HexColor("#e3e7f0")
MUTED = colors.HexColor("#8a91a3")
TEXT_DARK = colors.HexColor("#1c2233")
TEXT_LABEL = colors.HexColor("#5b6478")


@lru_cache
def env() -> Environment:
    return Environment(
        loader=FileSystemLoader(str(TEMPLATES)),
        autoescape=select_autoescape(["html", "xml"]),
    )


def _user_name(db: Session, uid: int | None) -> str:
    if not uid:
        return ""
    u = db.get(User, uid)
    return u.full_name if u else ""


def _user_signature_path(db: Session, uid: int | None) -> str:
    """Return the on-disk path to a user's uploaded signature image,
    or "" if they haven't uploaded one."""
    if not uid:
        return ""
    u = db.get(User, uid)
    if not u or not u.signature_path:
        return ""
    p = storage.get_user_signature_path(u.signature_path)
    return str(p) if p.exists() else ""


def _lawyer_name(db: Session, lid: int | None) -> str:
    if not lid:
        return ""
    lw = db.get(Lawyer, lid)
    return lw.name if lw else ""


def render_case_print(db: Session, case: Case) -> str:
    customer = db.get(Customer, case.customer_id) if case.customer_id else None
    division = db.get(Division, case.division_id) if case.division_id else None
    salesman = db.get(Salesman, case.salesman_id) if case.salesman_id else None
    bank = db.get(Bank, case.bank_id) if case.bank_id else None

    # Pre-load all banks referenced by cheques so the template can look them up
    bank_ids = {c.bank_id for c in case.cheques if c.bank_id}
    bank_by_id: dict[int, Bank] = {}
    if bank_ids:
        for b in db.query(Bank).filter(Bank.id.in_(bank_ids)).all():
            bank_by_id[b.id] = b

    signatory_grid = [
        {"role": "Accountant", "name": _user_name(db, case.created_by_id)},
        {"role": "Sales Manager", "name": _user_name(db, case.sales_manager_id)},
        {"role": "Division Manager", "name": _user_name(db, case.division_manager_id)},
        {"role": "Auditor", "name": _user_name(db, case.auditor_id)},
        {"role": "Finance Manager", "name": _user_name(db, case.fm_id)},
        {"role": "Executive Director", "name": _user_name(db, case.ed_id)},
        {"role": "Chairman / MD", "name": _user_name(db, case.chairman_id)},
        {"role": "Lawyer", "name": _lawyer_name(db, case.lawyer_id)},
    ]

    refs = {
        "customer": customer,
        "division": division,
        "salesman": salesman,
        "bank": bank,
        "bank_by_id": bank_by_id,
    }

    tmpl = env().get_template("case_print.html")
    return tmpl.render(
        case=case,
        refs=refs,
        signatory_grid=signatory_grid,
        now=datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
    )


# =====================================================================
#  SERVER-SIDE PDF — Case Application Form
# =====================================================================

def _fmt_amount(v: Decimal | int | float | None) -> str:
    if v is None:
        return "0.00"
    return f"{float(v):,.2f}"


def _draw_case_chrome(
    canvas: Canvas, doc: BaseDocTemplate, case_no: str, status: str, stage: str
) -> None:
    """Branded header + gold strip + footer on every page."""
    w, h = doc.pagesize

    # Header bar
    canvas.saveState()
    canvas.setFillColor(NAVY_DARK)
    canvas.rect(0, h - 18 * mm, w, 18 * mm, fill=1, stroke=0)

    # Logo circle
    canvas.setFillColor(GOLD)
    canvas.circle(15 * mm, h - 9 * mm, 5.5 * mm, stroke=0, fill=1)
    canvas.setFillColor(NAVY_DARK)
    canvas.setFont("Helvetica-Bold", 9)
    canvas.drawCentredString(15 * mm, h - 10.3 * mm, "PUG")

    # Brand text
    canvas.setFillColor(GOLD)
    canvas.setFont("Helvetica-Bold", 7)
    canvas.drawString(24 * mm, h - 6.5 * mm, settings.brand_company_name.upper())
    canvas.setFillColor(colors.white)
    canvas.setFont("Helvetica-Bold", 11)
    canvas.drawString(24 * mm, h - 11.5 * mm, "Legal Case Application Form")

    # Case info (right)
    canvas.setFillColor(colors.white)
    canvas.setFont("Helvetica-Bold", 9)
    canvas.drawRightString(w - 12 * mm, h - 6 * mm, f"Case No: {case_no}")
    canvas.setFont("Helvetica", 8)
    canvas.setFillColor(GOLD)
    canvas.drawRightString(w - 12 * mm, h - 10 * mm, f"Status: {status} · {stage}")
    canvas.setFillColor(colors.HexColor("#aabbdd"))
    canvas.drawRightString(
        w - 12 * mm,
        h - 14 * mm,
        f"Printed: {datetime.now(timezone.utc):%Y-%m-%d %H:%M UTC}",
    )

    # Gold strip
    canvas.setFillColor(GOLD)
    canvas.rect(0, h - 19.5 * mm, w, 1.5 * mm, fill=1, stroke=0)

    # Footer
    canvas.setStrokeColor(BORDER)
    canvas.setLineWidth(0.4)
    canvas.line(12 * mm, 14 * mm, w - 12 * mm, 14 * mm)
    canvas.setFillColor(MUTED)
    canvas.setFont("Helvetica", 7.5)
    canvas.drawString(
        12 * mm, 9 * mm,
        f"© {settings.brand_company_name}  ·  Legal Case Control System  ·  {case_no}",
    )
    canvas.drawRightString(
        w - 12 * mm, 9 * mm,
        f"Page {doc.page}",
    )
    canvas.restoreState()


def _section_heading(title: str, styles: dict[str, ParagraphStyle]) -> list[Any]:
    """Return flowables for a branded section heading with gold left bar."""
    return [
        Spacer(1, 5 * mm),
        Table(
            [[Paragraph(f"<b>{title}</b>", styles["section"])]],
            colWidths=["100%"],
            style=TableStyle([
                ("BACKGROUND", (0, 0), (-1, -1), LIGHT),
                ("LEFTPADDING", (0, 0), (-1, -1), 10),
                ("TOPPADDING", (0, 0), (-1, -1), 4),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
                ("LINEAFTER", (0, 0), (0, -1), 0, LIGHT),
                ("LINEBEFORE", (0, 0), (0, -1), 3, GOLD),
            ]),
        ),
        Spacer(1, 2 * mm),
    ]


def _kv_table(
    pairs: list[tuple[str, str]],
    doc_width: float,
    styles: dict[str, ParagraphStyle],
) -> Table:
    """Two-column key-value table."""
    data = [
        [Paragraph(k, styles["label"]), Paragraph(v, styles["value"])]
        for k, v in pairs
    ]
    tbl = Table(data, colWidths=[doc_width * 0.35, doc_width * 0.65])
    tbl.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (0, -1), 8),
        ("RIGHTPADDING", (0, 0), (-1, -1), 6),
        ("TOPPADDING", (0, 0), (-1, -1), 3),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
        ("LINEBELOW", (0, 0), (-1, -2), 0.3, BORDER),
    ]))
    return tbl


def render_case_pdf(db: Session, case: Case) -> bytes:
    """Produce a branded A4 PDF for the case application form."""
    customer = db.get(Customer, case.customer_id) if case.customer_id else None
    division = db.get(Division, case.division_id) if case.division_id else None
    salesman = db.get(Salesman, case.salesman_id) if case.salesman_id else None
    bank = db.get(Bank, case.bank_id) if case.bank_id else None
    case_type = db.get(CaseType, case.case_type_id) if case.case_type_id else None

    bank_ids = {c.bank_id for c in case.cheques if c.bank_id}
    bank_by_id: dict[int, Bank] = {}
    if bank_ids:
        for b in db.query(Bank).filter(Bank.id.in_(bank_ids)).all():
            bank_by_id[b.id] = b

    # (role label, signer name, on-disk signature image path or "")
    # The Lawyer is a master record (no User row), so they never get a
    # signature image — only the name is shown for that slot.
    signatory_grid: list[tuple[str, str, str]] = [
        ("Accountant", _user_name(db, case.created_by_id), _user_signature_path(db, case.created_by_id)),
        ("Sales Manager", _user_name(db, case.sales_manager_id), _user_signature_path(db, case.sales_manager_id)),
        ("Division Manager", _user_name(db, case.division_manager_id), _user_signature_path(db, case.division_manager_id)),
        ("Auditor", _user_name(db, case.auditor_id), _user_signature_path(db, case.auditor_id)),
        ("Finance Manager", _user_name(db, case.fm_id), _user_signature_path(db, case.fm_id)),
        ("Executive Director", _user_name(db, case.ed_id), _user_signature_path(db, case.ed_id)),
        ("Chairman / MD", _user_name(db, case.chairman_id), _user_signature_path(db, case.chairman_id)),
        ("Lawyer", _lawyer_name(db, case.lawyer_id), ""),
    ]

    # --- Document setup ---
    buf = io.BytesIO()
    page = A4
    doc = BaseDocTemplate(
        buf,
        pagesize=page,
        leftMargin=14 * mm,
        rightMargin=14 * mm,
        topMargin=24 * mm,
        bottomMargin=20 * mm,
    )
    frame = Frame(
        doc.leftMargin, doc.bottomMargin, doc.width, doc.height,
        leftPadding=0, rightPadding=0, topPadding=0, bottomPadding=0,
        id="main",
    )
    doc.addPageTemplates(
        PageTemplate(
            id="case",
            frames=[frame],
            onPage=lambda c, d: _draw_case_chrome(
                c, d, case.case_no, case.status, case.current_stage
            ),
        )
    )

    # --- Styles ---
    ss = getSampleStyleSheet()
    st: dict[str, ParagraphStyle] = {}
    st["section"] = ParagraphStyle(
        "section", parent=ss["Normal"],
        fontSize=10, leading=13, textColor=NAVY,
        fontName="Helvetica-Bold",
        spaceAfter=0,
    )
    st["label"] = ParagraphStyle(
        "label", parent=ss["Normal"],
        fontSize=9, leading=12, textColor=TEXT_LABEL,
        fontName="Helvetica-Bold",
    )
    st["value"] = ParagraphStyle(
        "value", parent=ss["Normal"],
        fontSize=9, leading=12, textColor=TEXT_DARK,
    )
    st["body"] = ParagraphStyle(
        "body", parent=ss["Normal"],
        fontSize=9, leading=12, textColor=TEXT_DARK,
    )
    st["th"] = ParagraphStyle(
        "th", parent=ss["Normal"],
        fontSize=8.5, leading=11, textColor=colors.white,
        fontName="Helvetica-Bold",
    )
    st["td"] = ParagraphStyle(
        "td", parent=ss["Normal"],
        fontSize=8.5, leading=11, textColor=TEXT_DARK,
    )
    st["td_r"] = ParagraphStyle(
        "td_r", parent=ss["Normal"],
        fontSize=8.5, leading=11, textColor=TEXT_DARK,
        alignment=2,  # right
    )
    st["sig_role"] = ParagraphStyle(
        "sig_role", parent=ss["Normal"],
        fontSize=7.5, leading=10, textColor=GOLD,
        fontName="Helvetica-Bold",
    )
    st["sig_name"] = ParagraphStyle(
        "sig_name", parent=ss["Normal"],
        fontSize=8.5, leading=11, textColor=TEXT_DARK,
    )
    st["small_muted"] = ParagraphStyle(
        "small_muted", parent=ss["Normal"],
        fontSize=7.5, leading=10, textColor=MUTED,
    )

    elements: list[Any] = [Spacer(1, 2 * mm)]
    half = doc.width / 2 - 2 * mm

    # ==================== CASE FILING ====================
    elements.extend(_section_heading("CASE FILING", st))

    # Flags row
    def _flag(label: str, on: bool) -> str:
        if on:
            return (
                f'<font face="Helvetica-Bold" color="#0b1020">'
                f'<span backColor="#c9a14a">&nbsp; {label} &nbsp;</span></font>'
            )
        return (
            f'<font color="#8a91a3">'
            f'<span backColor="#f7f8fc">&nbsp; {label} &nbsp;</span></font>'
        )

    flag_text = (
        f'{_flag("Criminal", case.is_criminal)}  &nbsp; '
        f'{_flag("Civil", case.is_civil)}  &nbsp; '
        f'{_flag("Both", case.is_criminal and case.is_civil)}'
    )
    # Phase 38: Case Type column dropped on both the form and the
    # print view (the Criminal/Civil/Both flags already capture it).
    # ``case_type`` is still resolved above for backwards-compat
    # with cases created before that change, but no longer rendered.
    flag_row = Table(
        [[Paragraph(flag_text, st["body"])]],
        colWidths=[doc.width],
    )
    flag_row.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
    ]))
    elements.append(flag_row)

    # ==================== CUSTOMER & DIVISION ====================
    elements.extend(_section_heading("CUSTOMER & DIVISION", st))

    left_kv = _kv_table([
        ("Customer", customer.name if customer else str(case.customer_id)),
        ("Customer Code", customer.code if customer else "-"),
        ("Customer Type", case.customer_type or "-"),
        ("Division", division.name if division else str(case.division_id)),
        ("Salesman", salesman.name if salesman else "-"),
    ], half, st)

    right_kv = _kv_table([
        ("Case Date", case.created_at.strftime("%Y-%m-%d") if case.created_at else "-"),
        ("Deposit Date", str(case.deposit_date) if case.deposit_date else "-"),
        ("Bank (Default)", bank.name if bank else "-"),
        ("Actual Due Amount", _fmt_amount(case.actual_due_amount)),
        ("Legal Filing Amount", _fmt_amount(case.legal_filing_amount)),
    ], half, st)

    two_col = Table(
        [[left_kv, right_kv]],
        colWidths=[half, half],
    )
    two_col.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 0),
        ("RIGHTPADDING", (0, 0), (-1, -1), 0),
    ]))
    elements.append(two_col)

    # ==================== CHEQUE SIGNATORIES (Phase 40) ====================
    # Joint-signing companies often have more than one authorised
    # signatory on a returned cheque; we print every selected partner
    # name + ID# so the legal team has the human face behind the
    # signature on the same page as the case data.
    if case.cheque_signatories:
        sig_lines = []
        for p in case.cheque_signatories:
            label = p.name
            if p.id_number:
                label += f' <font color="#8a91a3">(ID# {p.id_number})</font>'
            sig_lines.append(label)
        sig_text = " &nbsp;.&nbsp; ".join(sig_lines)
        elements.append(
            Paragraph(
                f'<b>Cheque Signatories:</b> {sig_text}',
                st["body"],
            )
        )

    # ==================== CHEQUE DETAILS ====================
    elements.extend(_section_heading("CHEQUE DETAILS", st))

    if case.cheques:
        cheque_header = [
            Paragraph("#", st["th"]),
            Paragraph("Cheque No", st["th"]),
            Paragraph("Bank", st["th"]),
            Paragraph("Amount", st["th"]),
            Paragraph("Date", st["th"]),
            Paragraph("Type", st["th"]),
            Paragraph("Bounce Reason", st["th"]),
        ]
        cheque_data: list[list[Any]] = [cheque_header]
        total_amount = Decimal("0")
        for idx, ch in enumerate(case.cheques, 1):
            bk = bank_by_id.get(ch.bank_id) if ch.bank_id else None  # type: ignore[arg-type]
            bank_text = bk.name if bk else (ch.bank_name_text or "-")
            total_amount += ch.amount or Decimal("0")
            cheque_data.append([
                Paragraph(str(idx), st["td"]),
                Paragraph(ch.cheque_number, st["td"]),
                Paragraph(bank_text, st["td"]),
                Paragraph(_fmt_amount(ch.amount), st["td_r"]),
                Paragraph(str(ch.cheque_date) if ch.cheque_date else "-", st["td"]),
                Paragraph(ch.cheque_type or "-", st["td"]),
                Paragraph(ch.bounce_reason or "-", st["td"]),
            ])
        # Total row
        cheque_data.append([
            Paragraph("", st["td"]),
            Paragraph("", st["td"]),
            Paragraph("<b>Total</b>", st["td"]),
            Paragraph(f"<b>{_fmt_amount(total_amount)}</b>", st["td_r"]),
            Paragraph("", st["td"]),
            Paragraph("", st["td"]),
            Paragraph("", st["td"]),
        ])

        n_cheques = len(cheque_data)
        cw = [
            doc.width * 0.05,   # #
            doc.width * 0.14,   # Cheque No
            doc.width * 0.22,   # Bank
            doc.width * 0.14,   # Amount
            doc.width * 0.12,   # Date
            doc.width * 0.10,   # Type
            doc.width * 0.23,   # Bounce Reason
        ]
        cheque_tbl = Table(cheque_data, colWidths=cw, repeatRows=1)
        cheque_tbl.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), NAVY),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
            ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
            ("FONTSIZE", (0, 0), (-1, 0), 8.5),
            ("TOPPADDING", (0, 0), (-1, 0), 5),
            ("BOTTOMPADDING", (0, 0), (-1, 0), 5),
            ("GRID", (0, 0), (-1, -1), 0.3, BORDER),
            ("ROWBACKGROUNDS", (0, 1), (-1, -2), [colors.white, LIGHT]),
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("LEFTPADDING", (0, 0), (-1, -1), 5),
            ("RIGHTPADDING", (0, 0), (-1, -1), 5),
            ("TOPPADDING", (0, 1), (-1, -1), 3),
            ("BOTTOMPADDING", (0, 1), (-1, -1), 3),
            ("ALIGN", (3, 1), (3, -1), "RIGHT"),
            # Total row styling
            ("BACKGROUND", (0, n_cheques - 1), (-1, n_cheques - 1), GOLD_LIGHT),
            ("FONTNAME", (0, n_cheques - 1), (-1, n_cheques - 1), "Helvetica-Bold"),
            ("LINEABOVE", (0, n_cheques - 1), (-1, n_cheques - 1), 1, GOLD),
        ]))
        elements.append(cheque_tbl)
    else:
        elements.append(
            Paragraph("<i>No cheques attached.</i>", st["small_muted"])
        )

    # ==================== COMMANDS / REMARKS ====================
    elements.extend(_section_heading("COMMANDS / REMARKS", st))

    remarks_text = case.commands.strip() if case.commands else "-"
    remarks_tbl = Table(
        [[Paragraph(remarks_text.replace("\n", "<br/>"), st["body"])]],
        colWidths=[doc.width],
    )
    remarks_tbl.setStyle(TableStyle([
        ("BOX", (0, 0), (-1, -1), 0.4, BORDER),
        ("LEFTPADDING", (0, 0), (-1, -1), 8),
        ("RIGHTPADDING", (0, 0), (-1, -1), 8),
        ("TOPPADDING", (0, 0), (-1, -1), 6),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
    ]))
    elements.append(remarks_tbl)

    # ==================== ATTACHMENTS ====================
    elements.extend(_section_heading("ATTACHMENTS", st))

    if case.attachments:
        # Phase 39: inline list of categories separated by bullets
        # so the printed form reads as a single flowing sentence
        # (e.g. "Credit Application . Computer Card . Shop Address").
        # Multiples in the same category collapse to one entry -
        # the printed form is a checklist of which kinds of
        # supporting documents are on file, not a per-file
        # manifest.
        seen: list[str] = []
        for att in case.attachments:
            cat = (att.category or "-").strip()
            if cat and cat not in seen:
                seen.append(cat)
        inline = " &nbsp;.&nbsp; ".join(seen)
        elements.append(Paragraph(inline, st["body"]))
    else:
        elements.append(
            Paragraph("<i>No attachments uploaded.</i>", st["small_muted"])
        )

    # ==================== SIGNATORIES ====================
    elements.extend(_section_heading("SIGNATORIES", st))

    # 4 columns × 2 rows
    sig_col_w = doc.width / 4 - 6 * mm
    sig_cells: list[list[Any]] = [[], []]
    for i, (role, name, sig_path) in enumerate(signatory_grid):
        row_idx = i // 4
        # Signature image (if present) or a fixed-height spacer to keep
        # cell heights consistent across the grid.
        if sig_path:
            try:
                sig_flowable: Any = Image(
                    sig_path, width=sig_col_w * 0.7, height=12 * mm, kind="proportional"
                )
            except Exception:
                sig_flowable = Spacer(1, 14 * mm)
        else:
            sig_flowable = Spacer(1, 14 * mm)
        cell_content = Table(
            [
                [Paragraph(role.upper(), st["sig_role"])],
                [Paragraph(name or "&nbsp;", st["sig_name"])],
                [sig_flowable],
                [Paragraph("Signature &amp; Date", st["small_muted"])],
            ],
            colWidths=[sig_col_w],
        )
        cell_content.setStyle(TableStyle([
            ("TOPPADDING", (0, 0), (-1, -1), 2),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 1),
            ("ALIGN", (0, 2), (0, 2), "CENTER"),
            ("LINEBELOW", (0, 2), (0, 2), 0.5, NAVY),
        ]))
        sig_cells[row_idx].append(cell_content)

    # Pad rows to 4 if needed
    for row in sig_cells:
        while len(row) < 4:
            row.append("")

    sig_tbl = Table(
        sig_cells,
        colWidths=[doc.width / 4] * 4,
    )
    sig_tbl.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("BOX", (0, 0), (-1, -1), 0.3, BORDER),
        ("INNERGRID", (0, 0), (-1, -1), 0.3, BORDER),
        ("LEFTPADDING", (0, 0), (-1, -1), 5),
        ("RIGHTPADDING", (0, 0), (-1, -1), 5),
        ("TOPPADDING", (0, 0), (-1, -1), 6),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
    ]))
    elements.append(sig_tbl)

    # --- Build ---
    doc.build(elements)
    return buf.getvalue()
