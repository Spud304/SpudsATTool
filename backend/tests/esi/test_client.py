import httpx
import pytest
from django.core.cache import cache

from apps.esi.client import EsiClient, EsiError, EsiUnavailable


@pytest.fixture(autouse=True)
def clear_cache():
    cache.clear()
    yield
    cache.clear()


def test_transport_failure_is_an_esi_error():
    def refuse(request):
        raise httpx.ConnectError("no route", request=request)

    client = EsiClient(base_url="https://esi.test", transport=httpx.MockTransport(refuse))
    with pytest.raises(EsiUnavailable):
        client.character_public(1)


def test_non_json_body_is_an_esi_error():
    def html(request):
        return httpx.Response(200, text="<html>maintenance</html>")

    client = EsiClient(base_url="https://esi.test", transport=httpx.MockTransport(html))
    with pytest.raises(EsiError):
        client.character_public(1)
