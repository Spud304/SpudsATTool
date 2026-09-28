"""Share links: a random token that lets anyone with the URL watch one scrim read-only, fit text hidden."""

import copy
import secrets
from datetime import timedelta

from django.utils import timezone

from apps.accounts.models import User
from apps.audit.services import record

from .models import Session, ShareLink
from .roster import ScrimError
from .sessions import scope

DEFAULT_DAYS = 7
MAX_DAYS = 90


def new_token() -> str:
    return secrets.token_urlsafe(24)


def create_share(actor: User, session: Session, days: int = DEFAULT_DAYS) -> ShareLink:
    if not 1 <= days <= MAX_DAYS:
        raise ScrimError(422, f"a share link lasts between 1 and {MAX_DAYS} days")
    link = ShareLink.objects.create(
        session=session,
        token=new_token(),
        created_by=actor,
        expires_at=timezone.now() + timedelta(days=days),
    )
    record(
        actor=actor,
        scope=scope(session),
        action="share.created",
        target=link,
        target_label=f"{session.title} share link",
        after={"expires_at": link.expires_at.isoformat()},
    )
    return link


def revoke_share(actor: User, link: ShareLink) -> ShareLink:
    if link.revoked_at is None:
        link.revoked_at = timezone.now()
        link.save(update_fields=["revoked_at"])
        record(
            actor=actor,
            scope=scope(link.session),
            action="share.revoked",
            target=link,
            target_label=f"{link.session.title} share link",
        )
    return link


def is_live(link: ShareLink) -> bool:
    return link.revoked_at is None and link.expires_at > timezone.now()


def resolve(token: str) -> Session | None:
    """The session behind a token, or None when the link is unknown, expired, revoked or the scrim archived."""
    link = ShareLink.objects.select_related("session").filter(token=token).first()
    if link is None or not is_live(link) or link.session.is_archived:
        return None
    return link.session


def strip_fit_text(set_doc: dict) -> dict:
    """Shared viewers see hulls and fit names, never the EFT text."""
    for rnd in set_doc.get("rounds", []):
        for side in ("us", "opp"):
            for slot in rnd[side]["slots"]:
                slot["fit_text"] = ""
    return set_doc


def strip_fit_text_from_message(message: dict) -> dict:
    """A stripped copy: the broker may hand the same message object to member streams too."""
    payload = message.get("payload") or {}
    if message.get("kind") == "set" and isinstance(payload.get("set"), dict):
        message = {
            **message,
            "payload": {**payload, "set": strip_fit_text(copy.deepcopy(payload["set"]))},
        }
    return message
