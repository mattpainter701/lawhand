"""Where a request's caller address comes from, and when we refuse to claim one.

Issue #488: a signing evidence certificate recorded an internal proxy address
as the signer's. The application read ``request.client.host`` — the immediate
peer, which behind nginx is our own infrastructure — while nginx had already
done the work of resolving the real client and forwarding it.
"""

import pytest

from app.middleware.rate_limit import _client_ip
from app.utils import client_address
from app.utils.client_address import attributable_client_ip, client_ip


class _Client:
    def __init__(self, host):
        self.host = host


class _Request:
    """The two things either resolver reads off a request."""

    def __init__(self, peer=None, forwarded_for=None):
        self.client = _Client(peer) if peer else None
        self.headers = {}
        if forwarded_for is not None:
            self.headers["x-forwarded-for"] = forwarded_for


@pytest.fixture
def hops(monkeypatch):
    """Set TRUSTED_PROXY_HOPS for both resolvers, which share one settings object."""

    def _set(value):
        monkeypatch.setattr(client_address.settings, "TRUSTED_PROXY_HOPS", value)

    return _set


# ── The address we are willing to put on a certificate ───────────────────────


def test_records_the_client_our_proxy_resolved_not_the_proxy(hops):
    hops(1)
    # nginx resolves the real client into $remote_addr (set_real_ip_from for the
    # Cloudflare ranges and the container network) and appends it as the last
    # X-Forwarded-For entry. The peer it connects from is the Docker bridge.
    request = _Request(peer="172.18.0.4", forwarded_for="203.0.113.7")
    assert attributable_client_ip(request) == "203.0.113.7"


def test_ignores_a_forwarded_for_the_caller_wrote_themselves(hops):
    hops(1)
    # A caller can send any X-Forwarded-For they like; it lands to the LEFT of
    # what our own proxy appends, so only the rightmost entry is ours.
    request = _Request(peer="172.18.0.4", forwarded_for="1.2.3.4, 203.0.113.7")
    assert attributable_client_ip(request) == "203.0.113.7"


def test_refuses_to_attribute_the_peer_when_a_proxy_is_expected(hops):
    hops(1)
    # No forwarded chain, but the deployment says one hop sits in front: this
    # request did not reach us the way we believe it does, so the peer is our
    # own infrastructure and we say nothing rather than claim it is the signer.
    request = _Request(peer="172.18.0.4")
    assert attributable_client_ip(request) is None


def test_refuses_to_attribute_a_chain_shorter_than_the_trusted_hops(hops):
    hops(2)
    request = _Request(peer="172.18.0.4", forwarded_for="203.0.113.7")
    assert attributable_client_ip(request) is None


def test_reads_past_the_inner_hop_when_two_proxies_are_configured(hops):
    hops(2)
    request = _Request(peer="10.0.0.9", forwarded_for="203.0.113.7, 10.0.0.8")
    assert attributable_client_ip(request) == "203.0.113.7"


def test_uses_the_peer_when_nothing_is_deployed_in_front(hops):
    hops(0)
    request = _Request(peer="203.0.113.7")
    assert attributable_client_ip(request) == "203.0.113.7"


def test_does_not_trust_a_forwarded_header_with_no_proxy_in_front(hops):
    hops(0)
    # With no trusted hop, X-Forwarded-For is entirely caller-controlled.
    request = _Request(peer="203.0.113.7", forwarded_for="1.2.3.4")
    assert attributable_client_ip(request) == "203.0.113.7"


def test_has_no_address_at_all_when_there_is_no_peer(hops):
    hops(0)
    assert attributable_client_ip(_Request()) is None


def test_tolerates_whitespace_and_empty_entries_in_the_chain(hops):
    hops(1)
    request = _Request(peer="172.18.0.4", forwarded_for=" 1.2.3.4 , , 203.0.113.7 ")
    assert attributable_client_ip(request) == "203.0.113.7"


# ── Rate limiting keeps its fallback ─────────────────────────────────────────


def test_rate_limiting_still_falls_back_to_the_peer(hops):
    hops(1)
    # A shared bucket is a far cheaper failure than no bucket, so this resolver
    # answers even where the evidence one declines to.
    request = _Request(peer="172.18.0.4")
    assert client_ip(request) == "172.18.0.4"
    assert attributable_client_ip(request) is None


def test_rate_limiting_reports_unknown_rather_than_nothing(hops):
    hops(1)
    assert client_ip(_Request()) == "unknown"


def test_rate_limiter_delegates_to_the_shared_resolver(hops):
    hops(1)
    # One definition of the caller address, so the two cannot drift apart.
    request = _Request(peer="172.18.0.4", forwarded_for="1.2.3.4, 203.0.113.7")
    assert _client_ip(request) == client_ip(request) == "203.0.113.7"


def test_rate_limiting_ignores_a_spoofed_chain_it_cannot_vouch_for(hops):
    hops(2)
    request = _Request(peer="172.18.0.4", forwarded_for="1.2.3.4")
    assert _client_ip(request) == "172.18.0.4"
