"""One definition of "who sent this request", shared by rate limiting and evidence.

X-Forwarded-For is a left-to-right chain: each proxy *appends* the address it
received the request from. The LEFTMOST entries are therefore fully
client-controlled — a caller can send ``X-Forwarded-For: 1.2.3.4`` and it will
sit at the head of the list — so only the rightmost entries, the ones appended
by our own infrastructure, are trustworthy. With ``N =
settings.TRUSTED_PROXY_HOPS`` trusted proxies in front of the app, the genuine
client address is ``N`` positions from the RIGHT (``parts[-N]``).

``TRUSTED_PROXY_HOPS`` MUST match the number of reverse proxies between the
public internet and this app. In the deployed topology that is **one**: nginx
resolves the real client itself (``set_real_ip_from`` for the Cloudflare ranges
and the container network, ``real_ip_header X-Forwarded-For``,
``real_ip_recursive on`` — see ``nginx/nginx.conf``), which collapses the
Cloudflare hops into ``$remote_addr``, and then appends that single resolved
value via ``proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for``. Too
small a hop count and a spoofed value leaks through; too large and one of our
own proxy addresses is used instead of the client's.

Two callers want different things from a missing or malformed chain:

* **Rate limiting** wants a key, always, and the immediate peer is a safe
  fallback: the worst case is that one bucket is shared.
* **Signing evidence** must not invent one. A certificate that prints our own
  infrastructure address as the signer's is weaker than one that says the
  address could not be attributed, so :func:`attributable_client_ip` returns
  ``None`` rather than fall back to the peer.
"""

from fastapi import Request

from app.config import get_settings

settings = get_settings()


def _forwarded_parts(request: Request) -> list[str]:
    forwarded_for = request.headers.get("x-forwarded-for")
    if not forwarded_for:
        return []
    return [part.strip() for part in forwarded_for.split(",") if part.strip()]


def _peer(request: Request) -> str | None:
    return request.client.host if request.client else None


def client_ip(request: Request, *, default: str = "unknown") -> str:
    """Best-effort caller address, falling back to the immediate peer.

    Used for rate limiting, where having *a* key always beats having none.
    """

    peer = _peer(request) or default
    parts = _forwarded_parts(request)
    if not parts:
        return peer

    hops = settings.TRUSTED_PROXY_HOPS
    if hops >= 1 and len(parts) >= hops:
        return parts[-hops]
    return peer


def attributable_client_ip(request: Request) -> str | None:
    """The caller's address, or ``None`` when it cannot be attributed to them.

    Never falls back to the immediate peer when a proxy is configured in front
    of the app: behind a proxy the peer *is* our own infrastructure, and
    recording that as the signer's address is what made evidence certificates
    misleading in the first place.
    """

    hops = settings.TRUSTED_PROXY_HOPS
    if hops < 1:
        # Nothing is expected in front of the app, so the peer is the client.
        return _peer(request)

    parts = _forwarded_parts(request)
    if len(parts) >= hops:
        return parts[-hops]

    # A proxy hop is configured but the chain is absent or shorter than it
    # should be, so this request did not reach us the way we believe it does.
    # We do not know who sent it, and saying so is the honest answer.
    return None
