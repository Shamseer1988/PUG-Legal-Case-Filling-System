"""Phase 36: cheque field extraction from bank return acknowledgement letters.

Strategy
--------
1. Default engine = **Tesseract** via ``pytesseract``. Free, runs
   on the API host, works on clean printed letters. Quietly
   returns "no match" if either the OS package or the Python
   binding is missing - the upload still succeeds, the user just
   has to type the values themselves.
2. Optional engine = **Vision LLM** (Anthropic or OpenAI). Enabled
   per-deployment by setting ``OCR_VISION_API_KEY`` plus
   ``OCR_VISION_PROVIDER`` in the env. When set we POST the file
   to the provider and parse a JSON object back.

Both engines feed the same ``extract_fields()`` function: it just
returns a small dataclass that the API layer applies onto the
cheque row.

The pipeline is intentionally defensive: every step that can fail
(no tesseract binary, no API key, malformed response, no fields
matched) collapses to a clean ``ChequeOcrResult(success=False)``
so the upload never errors just because OCR was inconclusive.
"""

from __future__ import annotations

import base64
import json
import os
import re
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal, InvalidOperation
from typing import Any

from loguru import logger
from sqlalchemy.orm import Session

from app.models.masters import Bank


# ---------------------------------------------------------------------------
# Result type
# ---------------------------------------------------------------------------
@dataclass
class ChequeOcrResult:
    """One row's worth of auto-fillable cheque data."""

    success: bool = False
    raw_text: str = ""
    cheque_number: str | None = None
    bank_name: str | None = None
    bank_id: int | None = None
    amount: Decimal | None = None
    cheque_date: date | None = None
    cheque_type: str | None = None
    bounce_reason: str | None = None
    engine: str = ""
    warnings: list[str] = field(default_factory=list)

    def to_payload(self) -> dict[str, Any]:
        """Shape the API hands back to the client + persists as JSON."""
        return {
            "success": self.success,
            "engine": self.engine,
            "cheque_number": self.cheque_number,
            "bank_id": self.bank_id,
            "bank_name": self.bank_name,
            "amount": str(self.amount) if self.amount is not None else None,
            "cheque_date": self.cheque_date.isoformat() if self.cheque_date else None,
            "cheque_type": self.cheque_type,
            "bounce_reason": self.bounce_reason,
            "warnings": self.warnings,
        }


# ---------------------------------------------------------------------------
# Engine 1: Tesseract
# ---------------------------------------------------------------------------
def _tesseract_text(blob: bytes, mime: str) -> str | None:
    """Run Tesseract over the bytes; returns the OCR text or None on failure."""
    try:
        import pytesseract  # type: ignore[import-not-found]
        from PIL import Image  # type: ignore[import-not-found]
    except ImportError:
        logger.info("pytesseract/Pillow not installed; OCR engine unavailable.")
        return None

    import io

    try:
        if mime == "application/pdf":
            try:
                from pdf2image import convert_from_bytes  # type: ignore[import-not-found]
            except ImportError:
                logger.info(
                    "pdf2image not installed; OCR cannot read PDFs without it."
                )
                return None
            pages = convert_from_bytes(blob, dpi=200)
            return "\n".join(pytesseract.image_to_string(p) for p in pages)
        # Image path: PIL handles JPG/PNG/TIFF/etc.
        img = Image.open(io.BytesIO(blob))
        return pytesseract.image_to_string(img)
    except Exception as exc:  # pragma: no cover - depends on host setup
        logger.warning("Tesseract OCR failed: {}", exc)
        return None


# ---------------------------------------------------------------------------
# Engine 2: Vision LLM (Anthropic / OpenAI)
# ---------------------------------------------------------------------------
def _vision_llm_extract(blob: bytes, mime: str) -> dict[str, Any] | None:
    """POST the file to a configured vision LLM and parse a JSON
    object back. Returns None if disabled or on any failure."""
    api_key = os.environ.get("OCR_VISION_API_KEY")
    provider = os.environ.get("OCR_VISION_PROVIDER", "anthropic").lower()
    if not api_key:
        return None
    try:
        import urllib.request
    except ImportError:  # pragma: no cover
        return None

    prompt = (
        "You are reading a bank cheque return acknowledgement letter. "
        "Return ONLY a JSON object with these fields (use null if unknown): "
        '{"cheque_number": str, "bank_name": str, "amount": str (decimal), '
        '"cheque_date": "YYYY-MM-DD", "bounce_reason": str}. '
        "No prose, no markdown fences."
    )

    encoded = base64.standard_b64encode(blob).decode("ascii")
    try:
        if provider == "anthropic":
            req = urllib.request.Request(
                "https://api.anthropic.com/v1/messages",
                method="POST",
                headers={
                    "x-api-key": api_key,
                    "anthropic-version": "2023-06-01",
                    "content-type": "application/json",
                },
                data=json.dumps(
                    {
                        "model": os.environ.get(
                            "OCR_VISION_MODEL", "claude-haiku-4-5-20251001"
                        ),
                        "max_tokens": 600,
                        "messages": [
                            {
                                "role": "user",
                                "content": [
                                    {
                                        "type": "image",
                                        "source": {
                                            "type": "base64",
                                            "media_type": mime,
                                            "data": encoded,
                                        },
                                    },
                                    {"type": "text", "text": prompt},
                                ],
                            }
                        ],
                    }
                ).encode("utf-8"),
            )
        else:  # openai-compatible
            req = urllib.request.Request(
                "https://api.openai.com/v1/chat/completions",
                method="POST",
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json",
                },
                data=json.dumps(
                    {
                        "model": os.environ.get("OCR_VISION_MODEL", "gpt-4o-mini"),
                        "messages": [
                            {
                                "role": "user",
                                "content": [
                                    {"type": "text", "text": prompt},
                                    {
                                        "type": "image_url",
                                        "image_url": {
                                            "url": f"data:{mime};base64,{encoded}"
                                        },
                                    },
                                ],
                            }
                        ],
                    }
                ).encode("utf-8"),
            )
        with urllib.request.urlopen(req, timeout=30) as resp:  # noqa: S310
            body = json.loads(resp.read().decode("utf-8"))
        if provider == "anthropic":
            text = body["content"][0]["text"]
        else:
            text = body["choices"][0]["message"]["content"]
        # Strip Markdown fences if the model emitted them anyway.
        text = re.sub(r"^```(?:json)?\s*|\s*```$", "", text.strip(), flags=re.M)
        return json.loads(text)
    except Exception as exc:  # pragma: no cover - external API
        logger.warning("Vision LLM OCR failed: {}", exc)
        return None


# ---------------------------------------------------------------------------
# Regex-based field extraction from OCR text
# ---------------------------------------------------------------------------
_RX_CHEQUE_NO = re.compile(
    r"(?:cheque|check|chq|cqe)\s*(?:no\.?|number|#)?[:\s]*([A-Z0-9-]{4,})",
    re.IGNORECASE,
)
_RX_AMOUNT = re.compile(
    r"(?:amount|amt|sum|total)[:\s]*(?:AED|USD|SAR|QAR|OMR|BHD|KWD|INR|\$|€|£)?\s*"
    r"([0-9]{1,3}(?:[,\s][0-9]{3})*(?:\.[0-9]{1,2})?)",
    re.IGNORECASE,
)
_RX_DATE_ISO = re.compile(r"\b(\d{4}-\d{2}-\d{2})\b")
_RX_DATE_SLASH = re.compile(r"\b(\d{1,2}[/\-.]\d{1,2}[/\-.]\d{2,4})\b")
_RX_REASON = re.compile(
    r"(?:reason|cause|remark)\s*(?:for\s+return)?[:\s]*([^\n\r]{4,200})",
    re.IGNORECASE,
)
_RX_BANK_HINT = re.compile(
    r"\b(?:emirates\s+nbd|first\s+abu\s+dhabi\s+bank|fab\b|adcb|hsbc|"
    r"mashreq|rakbank|adib|noor\s+bank|cbd|enbd)\b",
    re.IGNORECASE,
)


def _parse_amount(s: str) -> Decimal | None:
    cleaned = s.replace(",", "").replace(" ", "")
    try:
        v = Decimal(cleaned)
        if v <= 0:
            return None
        return v
    except InvalidOperation:
        return None


def _parse_date(s: str) -> date | None:
    from datetime import datetime

    for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y", "%d.%m.%Y", "%m/%d/%Y", "%d/%m/%y"):
        try:
            return datetime.strptime(s, fmt).date()
        except ValueError:
            continue
    return None


def _match_bank(db: Session, hint: str | None) -> tuple[int | None, str | None]:
    """Best-effort fuzzy match of the OCR'd bank name onto a Bank
    master row. Returns ``(bank_id, canonical_name)`` or ``(None, hint)``."""
    if not hint:
        return None, None
    needle = hint.lower().strip()
    if not needle:
        return None, hint
    banks = db.query(Bank).all()
    # First: exact code or name match.
    for b in banks:
        if b.code.lower() == needle or b.name.lower() == needle:
            return b.id, b.name
    # Second: substring match either way.
    for b in banks:
        if needle in b.name.lower() or b.name.lower() in needle:
            return b.id, b.name
        if needle in b.code.lower() or b.code.lower() in needle:
            return b.id, b.name
    return None, hint


def _extract_from_text(
    db: Session, text: str, *, engine: str
) -> ChequeOcrResult:
    res = ChequeOcrResult(raw_text=text, engine=engine)
    if not text or not text.strip():
        res.warnings.append("OCR produced no text")
        return res

    m = _RX_CHEQUE_NO.search(text)
    if m:
        res.cheque_number = m.group(1).strip().upper()

    m = _RX_AMOUNT.search(text)
    if m:
        amt = _parse_amount(m.group(1))
        if amt is not None:
            res.amount = amt

    m = _RX_DATE_ISO.search(text) or _RX_DATE_SLASH.search(text)
    if m:
        d = _parse_date(m.group(1))
        if d is not None:
            res.cheque_date = d

    m = _RX_REASON.search(text)
    if m:
        res.bounce_reason = m.group(1).strip().rstrip(".")

    m = _RX_BANK_HINT.search(text)
    bank_hint = m.group(0) if m else None
    bid, bname = _match_bank(db, bank_hint)
    res.bank_id = bid
    res.bank_name = bname

    # Cheque type defaults to Normal per the spec - that's what the
    # row would be set to anyway. We surface it so the UI shows the
    # "auto-filled" hint on this field too.
    res.cheque_type = "Normal"

    res.success = any(
        v is not None
        for v in (
            res.cheque_number,
            res.amount,
            res.cheque_date,
            res.bounce_reason,
            res.bank_id,
        )
    )
    if not res.success:
        res.warnings.append("No fields matched from OCR text")
    return res


def _from_llm_json(
    db: Session, data: dict[str, Any]
) -> ChequeOcrResult:
    res = ChequeOcrResult(engine="vision-llm")
    cn = data.get("cheque_number")
    if isinstance(cn, str) and cn.strip():
        res.cheque_number = cn.strip().upper()
    amt = data.get("amount")
    if isinstance(amt, (str, int, float)):
        parsed = _parse_amount(str(amt))
        if parsed is not None:
            res.amount = parsed
    d = data.get("cheque_date")
    if isinstance(d, str):
        res.cheque_date = _parse_date(d)
    rsn = data.get("bounce_reason")
    if isinstance(rsn, str) and rsn.strip():
        res.bounce_reason = rsn.strip()
    bn = data.get("bank_name")
    bid, bname = _match_bank(db, bn if isinstance(bn, str) else None)
    res.bank_id = bid
    res.bank_name = bname
    res.cheque_type = "Normal"
    res.success = any(
        v is not None
        for v in (
            res.cheque_number,
            res.amount,
            res.cheque_date,
            res.bounce_reason,
            res.bank_id,
        )
    )
    return res


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------
def extract_fields(
    db: Session, *, blob: bytes, mime: str
) -> ChequeOcrResult:
    """Try the configured engines in order and return the first
    successful extraction. Never raises - on total failure returns
    a clean ``ChequeOcrResult(success=False)``."""
    # Vision LLM first when configured - it's almost always better
    # than Tesseract on real bank letters.
    llm = _vision_llm_extract(blob, mime)
    if llm is not None:
        return _from_llm_json(db, llm)

    text = _tesseract_text(blob, mime)
    if text is None:
        return ChequeOcrResult(
            success=False,
            engine="none",
            warnings=["No OCR engine available on this host"],
        )
    return _extract_from_text(db, text, engine="tesseract")
