"""Share links: public read of one scrim by token, and the captain-side create/list/revoke."""

from typing import cast

from django.conf import settings
from django.http import HttpRequest
from django.shortcuts import get_object_or_404
from ninja import Router, Schema
from ninja.errors import HttpError

from apps.accounts import permissions
from apps.accounts.models import User

from . import sessions, share
from .api import SessionOut, session_document
from .models import Session, ShareLink
from .roster import ScrimError

public_router = Router(tags=["share"], auth=None)  # the token is the credential
router = Router(tags=["scrims"])


class ShareLinkOut(Schema):
    id: int
    token: str
    url: str
    created_by_name: str
    created_at: str
    expires_at: str
    revoked_at: str | None
    is_live: bool


class ShareCreateIn(Schema):
    days: int = share.DEFAULT_DAYS


def _link_out(request: HttpRequest, link: ShareLink) -> dict:
    return {
        "id": link.pk,
        "token": link.token,
        "url": (
            f"{settings.PUBLIC_ORIGIN}/share/{link.token}"
            if settings.PUBLIC_ORIGIN
            else request.build_absolute_uri(f"/share/{link.token}")
        ),
        "created_by_name": link.created_by.display_name if link.created_by else "",
        "created_at": link.created_at.isoformat(),
        "expires_at": link.expires_at.isoformat(),
        "revoked_at": link.revoked_at.isoformat() if link.revoked_at else None,
        "is_live": share.is_live(link),
    }


@public_router.get("/{token}", response=SessionOut)
def shared_session(request: HttpRequest, token: str):
    session = share.resolve(token)
    if session is None:
        raise HttpError(404, "this share link is not valid")
    session = get_object_or_404(sessions.queryset(), pk=session.pk)
    return session_document(session, None, shared=True)


def _manager(request: HttpRequest, session_id: int) -> tuple[User, Session]:
    session = get_object_or_404(Session, pk=session_id)
    permissions.require_view_session(request.user, session)
    permissions.require_manage_scrims(request.user)
    return cast(User, request.user), session


@router.get("/{session_id}/share", response=list[ShareLinkOut])
def list_shares(request: HttpRequest, session_id: int):
    _, session = _manager(request, session_id)
    links = (
        ShareLink.objects.filter(session=session)
        .select_related("created_by")
        .order_by("-created_at")
    )
    return [_link_out(request, link) for link in links]


@router.post("/{session_id}/share", response={201: ShareLinkOut})
def create_share(request: HttpRequest, session_id: int, payload: ShareCreateIn):
    user, session = _manager(request, session_id)
    try:
        link = share.create_share(user, session, payload.days)
    except ScrimError as exc:
        raise HttpError(exc.status, str(exc)) from exc
    return 201, _link_out(request, link)


@router.delete("/{session_id}/share/{link_id}", response=ShareLinkOut)
def revoke_share(request: HttpRequest, session_id: int, link_id: int):
    user, session = _manager(request, session_id)
    link = get_object_or_404(
        ShareLink.objects.select_related("session", "created_by"), pk=link_id, session=session
    )
    return _link_out(request, share.revoke_share(user, link))
