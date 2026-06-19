"""Branded PDF renderer (ReportLab) used by the report endpoints."""

from __future__ import annotations

import io
from datetime import datetime
from decimal import Decimal
from typing import Any

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.pdfgen.canvas import Canvas
from reportlab.platypus import (
    BaseDocTemplate,
    Frame,
    PageTemplate,
    Paragraph,
    Spacer,
    Table,
    TableStyle,
)

from app.core.config import settings

NAVY = colors.HexColor("#1a234a")
NAVY_DARK = colors.HexColor("#0b1020")
GOLD = colors.HexColor("#c9a14a")
LIGHT = colors.HexColor("#f7f8fc")
BORDER = colors.HexColor("#e3e7f0")
MUTED = colors.HexColor("#8a91a3")


def _draw_chrome(canvas: Canvas, doc: BaseDocTemplate, title: str, subtitle: str) -> None:
    """Painted on every page: brand header + gold strip + footer with page #."""
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
    canvas.drawString(24 * mm, h - 11.5 * mm, "Legal Case Control System")
    # Title (right side)
    canvas.setFillColor(colors.white)
    canvas.setFont("Helvetica-Bold", 10)
    canvas.drawRightString(w - 12 * mm, h - 7 * mm, title)
    canvas.setFont("Helvetica", 8)
    canvas.setFillColor(GOLD)
    canvas.drawRightString(w - 12 * mm, h - 12 * mm, subtitle[:120])

    # Gold strip
    canvas.setFillColor(GOLD)
    canvas.rect(0, h - 19.5 * mm, w, 1.5 * mm, fill=1, stroke=0)

    # Footer
    canvas.setStrokeColor(BORDER)
    canvas.setLineWidth(0.4)
    canvas.line(12 * mm, 14 * mm, w - 12 * mm, 14 * mm)
    canvas.setFillColor(MUTED)
    canvas.setFont("Helvetica", 8)
    canvas.drawString(
        12 * mm,
        9 * mm,
        f"(c) {settings.brand_company_name}  -  Legal Case Control System",
    )
    canvas.drawRightString(
        w - 12 * mm,
        9 * mm,
        f"Page {doc.page} - Generated {datetime.utcnow():%Y-%m-%d %H:%M UTC}",
    )
    canvas.restoreState()


def render_pdf(
    *,
    title: str,
    subtitle: str,
    columns: list[dict[str, Any]],
    rows: list[dict[str, Any]],
    params: dict[str, Any] | None = None,
    landscape_mode: bool | None = None,
) -> bytes:
    page = landscape(A4) if (landscape_mode if landscape_mode is not None else len(columns) > 6) else A4
    buf = io.BytesIO()
    doc = BaseDocTemplate(
        buf,
        pagesize=page,
        leftMargin=12 * mm,
        rightMargin=12 * mm,
        topMargin=24 * mm,
        bottomMargin=18 * mm,
    )

    sub_for_chrome = subtitle or ""
    if params:
        non_empty = {k: v for k, v in params.items() if v not in (None, "")}
        if non_empty:
            sub_for_chrome = (
                sub_for_chrome + "  |  " if sub_for_chrome else ""
            ) + ", ".join(f"{k}={v}" for k, v in non_empty.items())

    frame = Frame(
        doc.leftMargin,
        doc.bottomMargin,
        doc.width,
        doc.height,
        leftPadding=0,
        rightPadding=0,
        topPadding=0,
        bottomPadding=0,
        id="main",
    )
    doc.addPageTemplates(
        PageTemplate(
            id="branded",
            frames=[frame],
            onPage=lambda c, d: _draw_chrome(c, d, title, sub_for_chrome),
        )
    )

    styles = getSampleStyleSheet()
    body = ParagraphStyle(
        "body",
        parent=styles["BodyText"],
        fontSize=9,
        leading=11,
        textColor=colors.HexColor("#1c2233"),
    )
    head = ParagraphStyle(
        "head",
        parent=styles["BodyText"],
        fontSize=9,
        leading=11,
        textColor=colors.white,
        fontName="Helvetica-Bold",
    )

    # Build table data
    table_data: list[list[Any]] = []
    table_data.append([Paragraph(str(c["label"]), head) for c in columns])
    for row in rows:
        line: list[Any] = []
        for col in columns:
            v = row.get(col["key"])
            ctype = col.get("type", "text")
            line.append(Paragraph(_fmt(v, ctype), body))
        table_data.append(line)

    n_cols = max(len(columns), 1)
    col_widths = [doc.width / n_cols] * n_cols

    tbl = Table(table_data, colWidths=col_widths, repeatRows=1, hAlign="LEFT")
    ts = TableStyle(
        [
            ("BACKGROUND", (0, 0), (-1, 0), NAVY),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
            ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
            ("FONTSIZE", (0, 0), (-1, 0), 9),
            ("BOTTOMPADDING", (0, 0), (-1, 0), 6),
            ("TOPPADDING", (0, 0), (-1, 0), 6),
            ("GRID", (0, 0), (-1, -1), 0.25, BORDER),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, LIGHT]),
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("LEFTPADDING", (0, 0), (-1, -1), 6),
            ("RIGHTPADDING", (0, 0), (-1, -1), 6),
            ("TOPPADDING", (0, 1), (-1, -1), 4),
            ("BOTTOMPADDING", (0, 1), (-1, -1), 4),
        ]
    )
    # Right-align numeric columns
    for i, col in enumerate(columns):
        if col.get("type") in ("number", "int"):
            ts.add("ALIGN", (i, 1), (i, -1), "RIGHT")
    tbl.setStyle(ts)

    elements: list[Any] = [Spacer(1, 4 * mm), tbl]
    if rows:
        elements.append(Spacer(1, 4 * mm))
        elements.append(
            Paragraph(f"<font color='#8a91a3' size='8'>{len(rows)} row(s)</font>", body)
        )

    doc.build(elements)
    return buf.getvalue()


def _fmt(v: Any, ctype: str) -> str:
    if v is None:
        return ""
    if ctype == "number":
        try:
            n = float(v) if not isinstance(v, Decimal) else float(v)
            return f"{n:,.2f}"
        except (TypeError, ValueError):
            return str(v)
    if ctype == "int":
        try:
            return f"{int(v):,}"
        except (TypeError, ValueError):
            return str(v)
    if ctype == "datetime":
        if isinstance(v, datetime):
            return v.strftime("%Y-%m-%d %H:%M")
        return str(v).replace("T", " ")[:16]
    if ctype == "date":
        return str(v)[:10]
    return str(v)
