EXPECTED_HEADERS = {
    "Content-Security-Policy": "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; "
                                "img-src 'self'; frame-ancestors 'none'; base-uri 'self'; form-action 'self'",
    "X-Content-Type-Options": "nosniff",
    "Referrer-Policy": "same-origin",
    "X-Frame-Options": "DENY",
}


def assert_security_headers(response):
    for header, value in EXPECTED_HEADERS.items():
        assert response.headers.get(header) == value, f"{header} missing or wrong on {response.request.path}"


def test_security_headers_on_page_route(client):
    assert_security_headers(client.get("/"))


def test_security_headers_on_api_route(client):
    assert_security_headers(client.get("/api/vehicles"))


def test_security_headers_on_404(client):
    assert_security_headers(client.get("/this-route-does-not-exist"))


def test_csp_forbids_inline_scripts_by_declaring_self_only():
    # characterizes the policy string itself: script-src must not include
    # 'unsafe-inline' or 'unsafe-eval', since every page's <script> tags were
    # moved to external files specifically so this could be strict.
    csp = EXPECTED_HEADERS["Content-Security-Policy"]
    script_src = next(part for part in csp.split(";") if part.strip().startswith("script-src"))
    assert "unsafe-inline" not in script_src
    assert "unsafe-eval" not in script_src
