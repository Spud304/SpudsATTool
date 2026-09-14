import base64
import hashlib

import jwt
import pytest

from apps.accounts import sso


def test_valid_token_yields_identity(make_token, rsa_keys):
    identity = sso.validate_access_token(
        make_token(character_id=123, name="Spud", owner="abc"), key=rsa_keys[1]
    )
    assert identity.character_id == 123 and identity.name == "Spud" and identity.owner_hash == "abc"
    assert identity.scopes == ("publicData",)


@pytest.mark.parametrize("iss", ["https://login.eveonline.com", "login.eveonline.com"])
def test_both_issuer_forms_accepted(make_token, rsa_keys, iss):
    assert sso.validate_access_token(make_token(iss=iss), key=rsa_keys[1]).character_id == 90000001


def test_unknown_issuer_rejected(make_token, rsa_keys):
    with pytest.raises(sso.SsoError):
        sso.validate_access_token(make_token(iss="https://evil.example"), key=rsa_keys[1])


def test_wrong_audience_rejected(make_token, rsa_keys):
    with pytest.raises(sso.SsoError):
        sso.validate_access_token(make_token(aud=["someone-else"]), key=rsa_keys[1])


def test_expired_token_rejected(make_token, rsa_keys):
    with pytest.raises(sso.SsoError):
        sso.validate_access_token(make_token(exp_offset=-30), key=rsa_keys[1])


def test_single_scope_string_normalised(make_token, rsa_keys):
    assert sso.validate_access_token(make_token(scp="publicData"), key=rsa_keys[1]).scopes == (
        "publicData",
    )


def test_non_character_subject_rejected(make_token, rsa_keys):
    claims = jwt.decode(make_token(), options={"verify_signature": False})
    bad = jwt.encode({**claims, "sub": "CORP:EVE:1"}, rsa_keys[0], algorithm="RS256")
    with pytest.raises(sso.SsoError):
        sso.validate_access_token(bad, key=rsa_keys[1])


def test_pkce_pair_is_s256():
    verifier, challenge = sso.make_pkce()
    expected = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b"=")
    assert challenge == expected.decode() and "=" not in verifier
