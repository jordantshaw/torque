"""The request-level protections in `app.security`, and how the app uses them."""

import base64

import pytest
from fastapi.testclient import TestClient

from app.main import create_app
from app.models import Bike
from app.security import CONTENT_SECURITY_POLICY, host_allowed, hostname_of


def _app_client(bike_models_dir, tmp_path, **options):
    app = create_app(bike_models_dir, f"sqlite:///{tmp_path / 'sec.db'}", **options)
    return TestClient(app, base_url="http://localhost")


def _basic(user, password):
    return {"Authorization": "Basic " + base64.b64encode(f"{user}:{password}".encode()).decode()}


@pytest.fixture
def bike(db_session):
    bike = Bike(nickname="Race Bike", model_key="test-bike")
    db_session.add(bike)
    db_session.commit()
    return bike


# ---------- host check (DNS rebinding) ----------

@pytest.mark.parametrize("host", [
    "localhost", "localhost:8000", "LOCALHOST", "app.localhost", "127.0.0.1", "127.0.0.1:8000",
    "[::1]:8000", "192.168.1.5:8000", "10.0.0.2",
])
def test_localhost_and_ip_addresses_are_always_served(host):
    assert host_allowed(host, ())


@pytest.mark.parametrize("host", ["attacker.example", "attacker.example:8000", "evil.com", "localhost.evil.com", "", "  "])
def test_other_names_are_refused_by_default(host):
    assert not host_allowed(host, ())


def test_extra_hosts_can_be_exact_patterns_or_everything():
    assert host_allowed("nas.local:8000", ["nas.local"])
    assert host_allowed("garage.lan", ["*.lan"])
    assert not host_allowed("garage.lan.evil.com", ["*.lan"])
    assert not host_allowed("evil.com", ["nas.local", "*.lan"])
    assert host_allowed("anything.example", ["*"])


def test_hostname_parsing_ignores_port_and_brackets():
    assert hostname_of("Example.COM:8000") == "example.com"
    assert hostname_of("[::1]:8000") == "::1"


def test_a_spoofed_host_header_gets_a_400(client):
    response = client.get("/", headers={"Host": "attacker.example"})
    assert response.status_code == 400
    assert "ALLOWED_HOSTS" in response.text


def test_allowed_hosts_setting_lets_a_name_through(bike_models_dir, tmp_path):
    client = _app_client(bike_models_dir, tmp_path, allowed_hosts=["nas.local"])
    assert client.get("/", headers={"Host": "nas.local:8000"}).status_code == 200
    assert client.get("/", headers={"Host": "other.example"}).status_code == 400


# ---------- cross-site requests (CSRF) ----------

def test_a_cross_site_post_cannot_delete_data(client, db_session, bike):
    for headers in (
        {"Sec-Fetch-Site": "cross-site"},
        {"Sec-Fetch-Site": "same-site"},
        {"Origin": "http://evil.example"},
        {"Origin": "null"},
        {"Referer": "http://evil.example/page"},
        {"Origin": "http://localhost:9999"},  # same host name, different port: another site
    ):
        response = client.post(f"/bikes/{bike.id}/delete", headers=headers, follow_redirects=False)
        assert response.status_code == 403, headers
    db_session.expire_all()
    assert db_session.get(Bike, bike.id) is not None


@pytest.mark.parametrize("path", ["/bulk/bikes", "/bikes", "/bikes/1/clear-history", "/bikes/1/hours", "/bikes/1/rides"])
def test_every_post_route_is_protected(client, path):
    assert client.post(path, headers={"Sec-Fetch-Site": "cross-site"}, data={"action": "delete"}).status_code == 403


@pytest.mark.parametrize("headers", [
    {},  # curl, scripts and tests send neither header
    {"Sec-Fetch-Site": "same-origin"},
    {"Sec-Fetch-Site": "none"},
    {"Origin": "http://localhost"},
    {"Referer": "http://localhost/bikes/1"},
])
def test_same_origin_and_non_browser_posts_work(client, db_session, bike, headers):
    response = client.post(f"/bikes/{bike.id}/clear-history", headers=headers, follow_redirects=False)
    assert response.status_code == 303


def test_cross_site_reads_are_not_blocked(client):
    assert client.get("/", headers={"Sec-Fetch-Site": "cross-site"}).status_code == 200


# ---------- optional password ----------

def test_with_a_password_every_request_needs_it(bike_models_dir, tmp_path):
    client = _app_client(bike_models_dir, tmp_path, username="rider", password="s3cret")
    for path in ("/", "/static/style.css", "/bikes/1"):
        response = client.get(path)
        assert response.status_code == 401, path
        assert "Basic" in response.headers["www-authenticate"]
    assert client.post("/bikes", data={"nickname": "x", "model_key": "test-bike"}).status_code == 401
    assert client.get("/", headers=_basic("rider", "s3cret")).status_code == 200
    assert client.get("/static/style.css", headers=_basic("rider", "s3cret")).status_code == 200


@pytest.mark.parametrize("headers", [
    _basic("rider", "wrong"),
    _basic("someone", "s3cret"),
    _basic("", ""),
    {"Authorization": "Basic !!!not-base64!!!"},
    {"Authorization": "Bearer s3cret"},
    {"Authorization": "Basic"},
    {"Authorization": "Basic " + base64.b64encode(b"\xff\xfe:x").decode()},
])
def test_wrong_or_malformed_credentials_are_refused(bike_models_dir, tmp_path, headers):
    client = _app_client(bike_models_dir, tmp_path, username="rider", password="s3cret")
    assert client.get("/", headers=headers).status_code == 401


def test_passwords_with_colons_and_unicode_work(bike_models_dir, tmp_path):
    client = _app_client(bike_models_dir, tmp_path, username="rider", password="pä:ss:wörd")
    assert client.get("/", headers=_basic("rider", "pä:ss:wörd")).status_code == 200


def test_username_and_password_must_be_set_together(bike_models_dir, tmp_path):
    with pytest.raises(ValueError, match="both"):
        create_app(bike_models_dir, f"sqlite:///{tmp_path / 'x.db'}", username="rider")
    with pytest.raises(ValueError, match="both"):
        create_app(bike_models_dir, f"sqlite:///{tmp_path / 'y.db'}", password="s3cret")


def test_a_host_check_comes_before_the_password_prompt(bike_models_dir, tmp_path):
    client = _app_client(bike_models_dir, tmp_path, username="rider", password="s3cret")
    assert client.get("/", headers={"Host": "evil.example", **_basic("rider", "s3cret")}).status_code == 400


# ---------- size cap ----------

def test_oversized_and_malformed_bodies_are_refused(client):
    assert client.post("/bikes", content=b"x", headers={"Content-Length": "1000001"}).status_code == 413
    assert client.post("/bikes", content=b"x", headers={"Content-Length": "abc"}).status_code == 400


# ---------- headers ----------

def test_security_headers_are_on_every_kind_of_response(client, bike):
    for response in (
        client.get("/"),
        client.get(f"/bikes/{bike.id}"),
        client.get("/bikes/999"),  # the 404 page
        client.get("/static/style.css"),
        client.get("/", headers={"Host": "evil.example"}),  # a refusal
        client.post(f"/bikes/{bike.id}/delete", headers={"Sec-Fetch-Site": "cross-site"}),
    ):
        h = response.headers
        assert h["content-security-policy"] == CONTENT_SECURITY_POLICY
        assert h["x-frame-options"] == "DENY"
        assert h["x-content-type-options"] == "nosniff"
        assert h["referrer-policy"] == "same-origin"
        assert h["cross-origin-opener-policy"] == "same-origin"


def test_the_csp_allows_no_inline_or_remote_scripts():
    directives = dict(d.strip().split(" ", 1) for d in CONTENT_SECURITY_POLICY.split(";"))
    assert directives["script-src"] == "'self'"
    assert "unsafe" not in CONTENT_SECURITY_POLICY
    assert directives["frame-ancestors"] == "'none'"
    assert directives["object-src"] == "'none'"
    assert directives["base-uri"] == "'none'"
    assert directives["form-action"] == "'self'"


def test_pages_are_not_cached_but_static_files_may_be(client):
    assert client.get("/").headers["cache-control"] == "no-store"
    assert "no-store" not in client.get("/static/style.css").headers.get("cache-control", "")


# ---------- no generated API docs ----------

@pytest.mark.parametrize("path", ["/docs", "/redoc", "/openapi.json"])
def test_generated_api_docs_are_off(client, path):
    assert client.get(path).status_code == 404


# ---------- streaming body cap and content types ----------

FORM = {"Content-Type": "application/x-www-form-urlencoded"}


def _chunks(total, size=65_536):
    sent = 0
    while sent < total:
        piece = min(size, total - sent)
        yield b"a" * piece
        sent += piece


def test_a_streamed_body_is_capped_even_without_a_content_length(client):
    # A generator body is sent chunked, so there is no Content-Length to check.
    response = client.post("/bikes", content=_chunks(3_000_000), headers=FORM)
    assert response.status_code == 413


def test_a_streamed_body_under_the_cap_is_accepted(client):
    body = b"nickname=Trail&model_key=test-bike"
    response = client.post("/bikes", content=iter([body[:10], body[10:]]), headers=FORM, follow_redirects=False)
    assert response.status_code == 303


@pytest.mark.parametrize("content_type", [
    "multipart/form-data; boundary=x", "application/json", "text/plain", "application/xml",
])
def test_posts_only_accept_plain_form_data(client, content_type):
    response = client.post("/bikes", content=b"nickname=x&model_key=test-bike", headers={"Content-Type": content_type})
    assert response.status_code == 415


def test_form_posts_and_bodiless_posts_still_work(client, bike):
    assert client.post("/bikes", data={"nickname": "A", "model_key": "test-bike"}, follow_redirects=False).status_code == 303
    assert client.post(f"/bikes/{bike.id}/clear-history", follow_redirects=False).status_code == 303
    charset = {"Content-Type": "application/x-www-form-urlencoded; charset=UTF-8"}
    assert client.post("/bikes", content=b"nickname=B&model_key=test-bike", headers=charset, follow_redirects=False).status_code == 303


def test_uploads_are_refused_before_anything_is_parsed(client, db_session):
    files = {"nickname": (None, "x"), "model_key": (None, "test-bike"), "f": ("a.txt", b"hello")}
    assert client.post("/bikes", files=files).status_code == 415
    assert db_session.query(Bike).count() == 0


# ---------- login throttle ----------

def test_throttle_locks_out_a_client_after_repeated_wrong_passwords(monkeypatch):
    from app import security

    now = [1000.0]
    monkeypatch.setattr(security.time, "monotonic", lambda: now[0])
    throttle = security.LoginThrottle(max_failures=3, window=60)
    for _ in range(2):
        throttle.record_failure("10.0.0.9")
    assert throttle.retry_after("10.0.0.9") == 0
    throttle.record_failure("10.0.0.9")
    assert throttle.retry_after("10.0.0.9") > 0
    assert throttle.retry_after("10.0.0.10") == 0  # other clients are unaffected
    now[0] += 61  # the window passes
    assert throttle.retry_after("10.0.0.9") == 0


def test_throttle_forgets_old_clients_instead_of_growing_forever():
    from app.security import LoginThrottle

    throttle = LoginThrottle(max_clients=3)
    for n in range(10):
        throttle.record_failure(f"10.0.0.{n}")
    assert len(throttle._failures) == 3


def test_repeated_wrong_passwords_lock_the_client_out_even_for_the_right_one(bike_models_dir, tmp_path):
    client = _app_client(bike_models_dir, tmp_path, username="rider", password="s3cret")
    for _ in range(10):
        assert client.get("/", headers=_basic("rider", "wrong")).status_code == 401
    locked = client.get("/", headers=_basic("rider", "s3cret"))
    assert locked.status_code == 429
    assert int(locked.headers["retry-after"]) > 0


def test_the_browsers_first_unauthenticated_request_is_not_a_failure(bike_models_dir, tmp_path):
    client = _app_client(bike_models_dir, tmp_path, username="rider", password="s3cret")
    for _ in range(30):  # a browser asks without credentials before prompting
        assert client.get("/").status_code == 401
    assert client.get("/", headers=_basic("rider", "s3cret")).status_code == 200


# ---------- crash pages ----------

def test_a_crash_shows_no_detail_and_still_has_the_security_headers(client):
    def boom():
        raise RuntimeError("secret internal detail /etc/passwd")

    client.app.add_api_route("/boom", boom)
    crashing = TestClient(client.app, base_url="http://localhost", raise_server_exceptions=False)
    response = crashing.get("/boom")
    assert response.status_code == 500
    assert response.text == "Internal Server Error"
    assert "secret" not in response.text and "Traceback" not in response.text
    assert response.headers["content-security-policy"] == CONTENT_SECURITY_POLICY
    assert response.headers["x-frame-options"] == "DENY"


# ---------- nothing comes from another site ----------

def test_the_policy_names_no_other_site():
    assert "http" not in CONTENT_SECURITY_POLICY
    assert "data:" not in CONTENT_SECURITY_POLICY


def test_pages_and_styles_reference_no_external_hosts(client):
    from pathlib import Path

    root = Path(__file__).parent.parent / "app"
    for file in [*root.glob("templates/*.html"), root / "static" / "style.css", *root.glob("static/*.js")]:
        if file.name == "htmx.min.js":
            continue  # the vendored library mentions URLs in its own comments
        text = file.read_text()
        assert "http://" not in text and "https://" not in text, file.name
        assert "//fonts." not in text, file.name


def test_the_typeface_is_bundled_and_served(client):
    for name in ("manrope-latin.woff2", "manrope-latin-ext.woff2", "OFL.txt"):
        assert client.get(f"/static/fonts/{name}").status_code == 200, name
    font = client.get("/static/fonts/manrope-latin.woff2")
    assert font.content[:4] == b"wOF2"
    assert font.headers["content-type"] == "font/woff2"
    assert "/static/fonts/manrope-latin.woff2" in client.get("/static/style.css").text


@pytest.mark.parametrize("host", [
    "localhost@evil.com",
    "evil.com#@localhost",
    "evil.com\\@localhost",
    "evil.com/localhost",
    "evil.com localhost",
    "localhost:8000@evil.com",
    "evil.com?localhost",
    "localhost\r\nX-Injected: 1",
])
def test_smuggled_host_headers_are_refused_even_when_every_name_is_allowed(host):
    assert not host_allowed(host, ())
    assert not host_allowed(host, ("*",))  # "*" allows any *name*, never a malformed header


@pytest.mark.parametrize("host", ["localhost.", "127.0.0.1."])
def test_a_trailing_dot_is_a_different_name_and_refused_by_default(host):
    assert not host_allowed(host, ())


@pytest.mark.parametrize("origin", [
    "http://localhost.evil.com",
    "http://localhost:8000@evil.com",
    "http://evil.com#localhost",
    "http://evil.com/localhost",
])
def test_lookalike_origins_are_cross_site(client, bike, origin):
    response = client.post(f"/bikes/{bike.id}/clear-history", headers={"Origin": origin})
    assert response.status_code == 403
