"""Per-request context carried via contextvars.

Populated by the HTTP middleware with IP + User-Agent; the
``get_current_user`` dep fills in the actor fields once the JWT is
resolved.
"""

from contextvars import ContextVar
from dataclasses import dataclass, field


@dataclass
class RequestContext:
    user_id: int | None = None
    user_email: str = ""
    user_role: str = ""
    ip: str = ""
    user_agent: str = ""
    extra: dict = field(default_factory=dict)


_ctx: ContextVar[RequestContext | None] = ContextVar("request_ctx", default=None)


def set_ctx(ctx: RequestContext):
    return _ctx.set(ctx)


def reset_ctx(token) -> None:
    _ctx.reset(token)


def get_ctx() -> RequestContext | None:
    return _ctx.get()


def attach_user(user_id: int, email: str, role: str) -> None:
    ctx = _ctx.get()
    if ctx is None:
        ctx = RequestContext()
        _ctx.set(ctx)
    ctx.user_id = user_id
    ctx.user_email = email
    ctx.user_role = role
