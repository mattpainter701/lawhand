from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
NGINX = (ROOT / "nginx" / "nginx.conf").read_text(encoding="utf-8")


def test_oauth_rate_limit_keeps_429_and_renders_branded_recovery_page():
    assert NGINX.count("error_page 429 =429 /oauth-rate-limited.html;") == 2
    assert NGINX.count("location = /oauth-rate-limited.html {") == 2
    assert "map $status $retry_after_header" in NGINX
    assert "add_header Retry-After $retry_after_header always;" in NGINX
    page = (ROOT / "nginx" / "oauth-rate-limited.html").read_text(encoding="utf-8")
    assert "Sign-in is briefly paused" in page
    assert "Too many sign-in requests" in page
    assert 'href="/login"' in page
    assert 'integration=cloud' in page


def test_oauth_rate_limit_zone_strength_is_unchanged_for_both_servers():
    assert NGINX.count("limit_req zone=oauth burst=15 nodelay;") == 2
    assert NGINX.count("limit_req_zone $binary_remote_addr zone=oauth:10m rate=30r/m;") == 1
