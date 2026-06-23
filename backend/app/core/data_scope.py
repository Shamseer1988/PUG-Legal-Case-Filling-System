"""Phase 37: shared data-scope helper.

Every list / dashboard / inbox query that filters by ``user.divisions``
goes through ``allowed_division_ids`` so the rules stay consistent:

  - ``is_super`` users see everything
  - users with ``"*"`` in their role perms see everything
  - ``is_all_divisions`` users see everything (Phase 37)
  - everyone else sees only the divisions they're mapped to;
    an empty mapping means an empty result set
"""

from __future__ import annotations

from app.models.user import User

WILDCARD = "*"


def is_cross_division(user: User) -> bool:
    """True if ``user`` should bypass the division filter entirely."""
    if user.is_super or user.is_all_divisions:
        return True
    perms = user.role.permissions if user.role else []
    return WILDCARD in perms


def allowed_division_ids(user: User) -> list[int] | None:
    """Return the list of division ids the user is scoped to, or
    ``None`` for "no filter / all divisions".

    Callers use the None case to skip the filter entirely. An empty
    list means "scoped to nothing" - the caller should produce an
    empty result set rather than a no-filter query.
    """
    if is_cross_division(user):
        return None
    return [d.id for d in user.divisions]
