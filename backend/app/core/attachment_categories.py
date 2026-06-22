"""Phase 36: fixed attachment category list.

The original Phase 1 schema kept ``CaseAttachment.category`` as a
free-form ``String(50)`` so we don't need a migration to introduce
the new tiles - we just constrain the API to a known set. Legacy
rows with ``"Supporting Document"`` (and any other historical
values) keep rendering: they fall through to the "Other Docs"
tile in the UI but their original category text is preserved on
disk and in the DB.
"""

from __future__ import annotations

# Display order matters - this is how the tiles render on the form.
CATEGORY_CREDIT_APP = "Credit Application"
CATEGORY_CR_COPY = "CR Copy"
CATEGORY_COMPT_CARD = "Computer Card"
CATEGORY_PARTNERS_ID = "Partners ID"
CATEGORY_SHOP_ADDRESS = "Shop Address"
CATEGORY_INVOICES = "Invoices"
CATEGORY_OTHER = "Other Docs"

# Legacy default. New uploads must pick one of the constants above,
# but rows already in the DB with this value still render under
# "Other Docs".
LEGACY_DEFAULT = "Supporting Document"

ATTACHMENT_CATEGORIES: tuple[str, ...] = (
    CATEGORY_CREDIT_APP,
    CATEGORY_CR_COPY,
    CATEGORY_COMPT_CARD,
    CATEGORY_PARTNERS_ID,
    CATEGORY_SHOP_ADDRESS,
    CATEGORY_INVOICES,
    CATEGORY_OTHER,
)

_ALLOWED: frozenset[str] = frozenset(ATTACHMENT_CATEGORIES) | {LEGACY_DEFAULT}


def is_valid_category(value: str) -> bool:
    return value in _ALLOWED


def normalise_category(value: str | None) -> str:
    """Coerce a category from the request into the canonical list.

    Unknown strings collapse to ``Other Docs`` so a misbehaving
    client can't silently invent custom categories that the UI
    can't render.
    """
    if not value:
        return CATEGORY_OTHER
    if value in _ALLOWED:
        return value
    return CATEGORY_OTHER
