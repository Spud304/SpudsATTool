import time

import jwt
import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa

from apps.accounts import services
from apps.accounts.models import Membership, User
from apps.accounts.sso import SsoIdentity
from apps.core.models import Team

ADMIN_ID = 90000001


def admitted(result) -> tuple[User, Membership]:
    """Narrow an AdmitResult that must have succeeded."""
    assert result.user is not None and result.membership is not None, result.outcome
    return result.user, result.membership


@pytest.fixture
def team(db):
    return Team.get_solo()


@pytest.fixture
def admins(settings):
    settings.ADMIN_CHARACTER_IDS = [ADMIN_ID]
    return [ADMIN_ID]


@pytest.fixture(scope="session")
def rsa_keys():
    private = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    public_pem = private.public_key().public_bytes(
        serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo
    )
    private_pem = private.private_bytes(
        serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption()
    )
    return private_pem, public_pem


@pytest.fixture
def make_token(rsa_keys, settings):
    private_pem, _ = rsa_keys

    def _make(
        character_id=ADMIN_ID,
        name="Spud",
        owner="owner-hash-1",
        iss="https://login.eveonline.com",
        aud=None,
        scp=("publicData",),
        exp_offset=600,
        **extra,
    ):
        claims = {
            "sub": f"CHARACTER:EVE:{character_id}",
            "name": name,
            "owner": owner,
            "iss": iss,
            "aud": aud if aud is not None else [settings.EVE_CLIENT_ID, "EVE Online"],
            "exp": int(time.time()) + exp_offset,
            "iat": int(time.time()),
            "scp": list(scp) if isinstance(scp, list | tuple) else scp,
            **extra,
        }
        return jwt.encode(claims, private_pem, algorithm="RS256", headers={"kid": "test"})

    return _make


@pytest.fixture
def make_character(db):
    def _make(
        character_id=ADMIN_ID, name="Spud", owner="owner-1", corporation_id=None, alliance_id=None
    ):
        identity = SsoIdentity(
            character_id=character_id, name=name, owner_hash=owner, scopes=("publicData",)
        )
        return services.upsert_character(
            identity, {"corporation_id": corporation_id, "alliance_id": alliance_id}
        )

    return _make


@pytest.fixture
def login_as(db, client):
    """Log the test client in through dev-login. role=None goes through normal admission."""

    def _login(character_id=ADMIN_ID, name="Spud", role="admin", **params):
        query = {"character_id": character_id, "name": name, **params}
        if role:
            query["role"] = role
        resp = client.get("/auth/dev-login", query)
        assert resp.status_code in (302, 403), resp.content[:200]
        return resp

    return _login
