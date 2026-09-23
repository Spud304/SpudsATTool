import logging
import secrets
from typing import cast

from django.conf import settings
from django.contrib.auth import login as auth_login
from django.contrib.auth import logout as auth_logout
from django.http import Http404, HttpRequest, HttpResponse, HttpResponseBadRequest
from django.shortcuts import redirect, render
from django.urls import reverse
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.http import require_http_methods

from . import services, sso
from .models import MembershipSource, TeamRole, User

log = logging.getLogger(__name__)
BACKEND = "django.contrib.auth.backends.ModelBackend"


def _safe_next(request: HttpRequest, candidate: str | None) -> str:
    if candidate and url_has_allowed_host_and_scheme(
        candidate, allowed_hosts={request.get_host()}, require_https=request.is_secure()
    ):
        return candidate
    return "/"


def _callback_uri(request: HttpRequest) -> str:
    return settings.EVE_CALLBACK_URL or request.build_absolute_uri(reverse("accounts:callback"))


def _denied(request: HttpRequest, character, outcome: str) -> HttpResponse:
    return render(
        request,
        "accounts/not_member.html",
        {"character": character, "outcome": outcome},
        status=403,
    )


@require_http_methods(["GET"])
def login_view(request: HttpRequest) -> HttpResponse:
    if not settings.EVE_CLIENT_ID:
        return HttpResponse(
            "EVE SSO is not configured: set EVE_CLIENT_ID and EVE_CLIENT_SECRET.", status=503
        )
    verifier, challenge = sso.make_pkce()
    state = secrets.token_urlsafe(24)
    request.session["sso"] = {
        "state": state,
        "verifier": verifier,
        "next": _safe_next(request, request.GET.get("next")),
        "mode": "link" if request.GET.get("mode") == "link" else "login",
    }
    try:
        url = sso.build_authorize_url(
            state=state,
            code_challenge=challenge,
            redirect_uri=_callback_uri(request),
            scopes=settings.EVE_SSO_SCOPES,
        )
    except sso.SsoError as exc:
        log.warning("sso failure: %s", exc)
        return render(request, "accounts/sso_error.html", {"error": str(exc)}, status=503)
    return redirect(url)


@require_http_methods(["GET"])
def callback_view(request: HttpRequest) -> HttpResponse:
    pending = request.session.pop("sso", None)
    if not pending or request.GET.get("state") != pending.get("state"):
        return HttpResponseBadRequest("login state mismatch; start again")
    if request.GET.get("error"):
        error = request.GET.get("error_description") or request.GET["error"]
        return render(request, "accounts/sso_error.html", {"error": error}, status=400)
    code = request.GET.get("code")
    if not code:
        return HttpResponseBadRequest("missing code")
    try:
        tokens = sso.exchange_code(
            code=code, code_verifier=pending["verifier"], redirect_uri=_callback_uri(request)
        )
        identity = sso.validate_access_token(tokens["access_token"])
    except sso.SsoError as exc:
        log.warning("sso failure: %s", exc)
        return render(request, "accounts/sso_error.html", {"error": str(exc)}, status=400)

    character = services.upsert_character(
        identity, services.fetch_affiliation(identity.character_id)
    )
    next_url = pending.get("next") or "/"
    if pending.get("mode") == "link" and request.user.is_authenticated:
        try:
            services.link_character(cast(User, request.user), character)
        except ValueError as exc:
            return render(request, "accounts/sso_error.html", {"error": str(exc)}, status=409)
        return redirect(next_url)

    result = services.admit(character, invite_token=request.session.pop("invite_token", None))
    if not result.admitted:
        log.info(
            "login denied for %s (%s): %s", character.name, character.character_id, result.outcome
        )
        return _denied(request, character, result.outcome)
    auth_login(request, result.user, backend=BACKEND)
    return redirect(next_url)


@require_http_methods(["GET", "POST"])
def logout_view(request: HttpRequest) -> HttpResponse:
    auth_logout(request)
    return redirect("/")


@require_http_methods(["GET"])
def join_view(request: HttpRequest, token: str) -> HttpResponse:
    request.session["invite_token"] = token
    return redirect(f"{reverse('accounts:login')}?next=/")


@require_http_methods(["GET"])
def dev_login_view(request: HttpRequest) -> HttpResponse:
    """Local-only shortcut: /auth/dev-login?character_id=1&name=Test[&role=captain][&corporation_id=..]."""
    if not settings.DEV_LOGIN_ENABLED:
        raise Http404
    try:
        character_id = int(request.GET["character_id"])
    except (KeyError, ValueError):
        return HttpResponseBadRequest("character_id required")
    identity = sso.SsoIdentity(
        character_id=character_id,
        name=request.GET.get("name", f"Dev Character {character_id}"),
        owner_hash=request.GET.get("owner", "dev-owner"),
        scopes=("publicData",),
    )
    affiliation = {
        "corporation_id": int(request.GET["corporation_id"])
        if request.GET.get("corporation_id")
        else None,
        "alliance_id": int(request.GET["alliance_id"]) if request.GET.get("alliance_id") else None,
    }
    character = services.upsert_character(identity, affiliation)
    role = request.GET.get("role")
    if role:
        if not TeamRole.objects.filter(slug=role).exists():
            return HttpResponseBadRequest("unknown role")
        user = services.ensure_user(character)
        membership = services._set_membership(
            user, role=role, source=MembershipSource.EXPLICIT, note="dev login"
        )
        result = services.AdmitResult(user, membership, "existing")
    else:
        result = services.admit(character, invite_token=request.session.pop("invite_token", None))
    if not result.admitted:
        return _denied(request, character, result.outcome)
    auth_login(request, result.user, backend=BACKEND)
    return redirect(_safe_next(request, request.GET.get("next")))
