"""Warp-in labels at /api/warp-labels: the vocabulary the set headers' four warp calls pick from."""

from typing import cast

from django.db import IntegrityError, transaction
from django.http import HttpRequest
from django.shortcuts import get_object_or_404
from ninja import Router, Schema
from ninja.errors import HttpError

from apps.accounts import permissions
from apps.accounts.models import User
from apps.audit.services import record

from .models import Set, WarpInLabel

router = Router(tags=["scrims"])


class WarpLabelOut(Schema):
    id: int
    label: str
    sort_order: int
    is_active: bool
    in_use: int


class WarpLabelIn(Schema):
    label: str
    sort_order: int = 0


class WarpLabelPatch(Schema):
    label: str | None = None
    sort_order: int | None = None
    is_active: bool | None = None


def _uses(label: str) -> int:
    return Set.all_objects.filter(warp_calls__contains=[label]).count()


def _out(row: WarpInLabel) -> dict:
    return {
        "id": row.pk,
        "label": row.label,
        "sort_order": row.sort_order,
        "is_active": row.is_active,
        "in_use": _uses(row.label),
    }


@router.get("", response=list[WarpLabelOut])
def list_labels(request: HttpRequest):
    """Every label, active or not; the scrim vocabulary endpoint serves only the active ones."""
    permissions.require_scrim_access(request.user)
    return [_out(r) for r in WarpInLabel.objects.all()]


@router.post("", response={201: WarpLabelOut})
def create_label(request: HttpRequest, payload: WarpLabelIn):
    permissions.require_perm(request.user, "manage_team")
    label = payload.label.strip()[:40]
    if not label:
        raise HttpError(422, "a label needs text")
    try:
        with transaction.atomic():
            row = WarpInLabel.objects.create(label=label, sort_order=payload.sort_order)
    except IntegrityError as exc:
        raise HttpError(409, f"label {label!r} already exists") from exc
    record(actor=cast(User, request.user), action="warp_label.created", target=row)
    return 201, _out(row)


@router.patch("/{label_id}", response=WarpLabelOut)
def patch_label(request: HttpRequest, label_id: int, payload: WarpLabelPatch):
    permissions.require_perm(request.user, "manage_team")
    row = get_object_or_404(WarpInLabel, pk=label_id)
    changes = payload.dict(exclude_unset=True)
    before = {k: getattr(row, k) for k in changes}
    if "label" in changes:
        changes["label"] = changes["label"].strip()[:40]
        if not changes["label"]:
            raise HttpError(422, "a label needs text")
    for field, value in changes.items():
        setattr(row, field, value)
    try:
        with transaction.atomic():
            row.save()
    except IntegrityError as exc:
        raise HttpError(409, f"label {row.label!r} already exists") from exc
    record(
        actor=cast(User, request.user),
        action="warp_label.updated",
        target=row,
        before=before,
        after=changes,
    )
    return _out(row)


@router.delete("/{label_id}", response={204: None})
def delete_label(request: HttpRequest, label_id: int):
    permissions.require_perm(request.user, "manage_team")
    row = get_object_or_404(WarpInLabel, pk=label_id)
    uses = _uses(row.label)
    if uses:
        raise HttpError(409, f"{uses} set(s) use this label; deactivate it instead")
    record(actor=cast(User, request.user), action="warp_label.deleted", target=row)
    row.delete()
    return 204, None
