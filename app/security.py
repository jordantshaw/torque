"""Request-level protections for an app that has no user accounts.

`SecurityMiddleware` runs on every request, in this order:

1. **Host check.** Only localhost, IP addresses and names listed in
   `ALLOWED_HOSTS` are served. This stops DNS-rebinding, where a web page on
   some other domain re-points its name at your machine to talk to the app.
2. **Optional password** (HTTP Basic). With one set, every request needs it, and
   a client that keeps guessing wrong is locked out for a while.
3. **Cross-site requests.** A state-changing request (POST and friends) that a
   browser marks as coming from another site is refused, so a page you merely
   visit can't make your browser delete your bikes.
4. **Body rules.** State-changing requests may only send plain form data, and
   no more than 1 MB of it, counted as it streams in.

Every response, including the refusals above and a crash page, carries browser
security headers (a strict Content-Security-Policy among them).
"""

import base64
import binascii
import fnmatch
import hmac
import ipaddress
import re
import time
from collections import deque
from collections.abc import Iterable
from urllib.parse import urlsplit

from starlette.datastructures import MutableHeaders
from starlette.requests import Request
from starlette.responses import PlainTextResponse, Response

# What a real Host header can contain: a name or IP, brackets for IPv6, a port.
_HOST_CHARS = re.compile(r"[A-Za-z0-9._:\-\[\]]+")

SAFE_METHODS = frozenset({"GET", "HEAD", "OPTIONS"})
MAX_BODY_BYTES = 1_000_000

# Everything (scripts, styles, the typeface) is served from this app. No inline
# scripts or styles, and nothing from another site.
CONTENT_SECURITY_POLICY = "; ".join([
    "default-src 'self'",
    "script-src 'self'",
    "style-src 'self'",
    "font-src 'self'",
    "img-src 'self'",
    "connect-src 'self'",
    "object-src 'none'",
    "base-uri 'none'",
    "form-action 'self'",
    "frame-ancestors 'none'",
])

FORM_CONTENT_TYPE = "application/x-www-form-urlencoded"

SECURITY_HEADERS = {
    "Content-Security-Policy": CONTENT_SECURITY_POLICY,
    "X-Frame-Options": "DENY",
    "X-Content-Type-Options": "nosniff",
    "Referrer-Policy": "same-origin",
    "Permissions-Policy": "camera=(), microphone=(), geolocation=(), payment=(), usb=()",
    "Cross-Origin-Opener-Policy": "same-origin",
    "Cross-Origin-Resource-Policy": "same-origin",
}


def hostname_of(host_header: str) -> str:
    """The lowercase host name from a Host header (port and brackets removed)."""
    return (urlsplit("//" + host_header.strip()).hostname or "").lower()


def host_allowed(host_header: str, extra_hosts: Iterable[str]) -> bool:
    """Whether to serve a request addressed to `host_header`.

    Allowed: localhost, any IP address (an IP can't be rebound), and names that
    match `extra_hosts` (exact, or a pattern such as `*.example.com`; `*` allows
    every name)."""
    if not _HOST_CHARS.fullmatch(host_header.strip()):
        return False  # no userinfo ('@'), fragments, slashes, spaces ...
    host = hostname_of(host_header)
    if not host:
        return False
    if host == "localhost" or host.endswith(".localhost"):
        return True
    try:
        ipaddress.ip_address(host)
        return True
    except ValueError:
        pass
    return any(fnmatch.fnmatchcase(host, pattern.lower()) for pattern in extra_hosts)


def is_cross_site(request: Request) -> bool:
    """Whether a browser says this request was triggered from another site."""
    site = request.headers.get("sec-fetch-site")
    if site is not None:
        return site not in ("same-origin", "none")
    source = request.headers.get("origin") or request.headers.get("referer")
    if source is None:
        return False  # not a browser (curl, scripts, tests)
    host = request.headers.get("host", "").lower()
    return urlsplit(source).netloc.lower() != host  # "null" and foreign origins land here


def credentials_ok(request: Request, username: str, password: str) -> bool:
    """Whether the request carries the right HTTP Basic credentials."""
    scheme, _, token = request.headers.get("authorization", "").partition(" ")
    if scheme.lower() != "basic":
        return False
    try:
        decoded = base64.b64decode(token, validate=True).decode("utf-8")
    except (binascii.Error, UnicodeDecodeError):
        return False
    given_user, _, given_password = decoded.partition(":")
    # Compare both, in constant time, so timing doesn't reveal which was wrong.
    user_ok = hmac.compare_digest(given_user.encode(), username.encode())
    password_ok = hmac.compare_digest(given_password.encode(), password.encode())
    return user_ok and password_ok


class BodyTooLarge(Exception):
    """Raised while reading a request body that has grown past the limit."""


class LoginThrottle:
    """Locks a client out after too many wrong passwords.

    Failures are counted per client address over a sliding window. While locked
    out, even the right password is refused, which is what makes guessing
    pointless. Other clients are unaffected, so an attacker can't lock *you*
    out (unless a proxy makes everyone share one address)."""

    def __init__(self, max_failures: int = 10, window: float = 300.0, max_clients: int = 1000):
        self.max_failures = max_failures
        self.window = window
        self.max_clients = max_clients
        self._failures: dict[str, deque[float]] = {}

    def _recent(self, client: str) -> deque[float]:
        failures = self._failures.get(client)
        if failures is None:
            return deque()
        cutoff = time.monotonic() - self.window
        while failures and failures[0] < cutoff:
            failures.popleft()
        if not failures:
            del self._failures[client]
        return failures

    def retry_after(self, client: str) -> int:
        """Seconds until `client` may try again (0 if it isn't locked out)."""
        failures = self._recent(client)
        if len(failures) < self.max_failures:
            return 0
        return max(1, int(self.window - (time.monotonic() - failures[0])) + 1)

    def record_failure(self, client: str) -> None:
        if client not in self._failures and len(self._failures) >= self.max_clients:
            self._failures.pop(next(iter(self._failures)))  # forget the oldest client
        self._failures.setdefault(client, deque()).append(time.monotonic())


class SecurityMiddleware:
    """Pure ASGI, so it can see (and cap) a request body as it streams in and
    add headers to every response."""

    def __init__(
        self,
        app,
        allowed_hosts: Iterable[str] = (),
        username: str | None = None,
        password: str | None = None,
        throttle: LoginThrottle | None = None,
    ):
        self.app = app
        self.allowed_hosts = tuple(allowed_hosts)
        self.username = username
        self.password = password
        self.throttle = throttle or LoginThrottle()

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        started = False

        async def send_with_headers(message):
            nonlocal started
            if message["type"] == "http.response.start":
                started = True
                headers = MutableHeaders(scope=message)
                for name, value in SECURITY_HEADERS.items():
                    headers.setdefault(name, value)
                if headers.get("content-type", "").startswith("text/html"):
                    headers.setdefault("Cache-Control", "no-store")
            await send(message)

        request = Request(scope)
        refusal = self._refusal(request)
        if refusal is not None:
            await refusal(scope, receive, send_with_headers)
            return

        if request.method not in SAFE_METHODS:
            receive = self._capped(receive)
        try:
            await self.app(scope, receive, send_with_headers)
        except BodyTooLarge:
            if started:
                raise
            await PlainTextResponse("Request too large.", status_code=413)(scope, receive, send_with_headers)

    @staticmethod
    def _capped(receive):
        total = 0

        async def capped_receive():
            nonlocal total
            message = await receive()
            if message["type"] == "http.request":
                total += len(message.get("body", b""))
                if total > MAX_BODY_BYTES:
                    raise BodyTooLarge
            return message

        return capped_receive

    def _refusal(self, request: Request) -> Response | None:
        if not host_allowed(request.headers.get("host", ""), self.allowed_hosts):
            return PlainTextResponse(
                "Unknown host name. To allow it, add it to ALLOWED_HOSTS "
                "(see docs/deploying.md).",
                status_code=400,
            )
        if self.username and self.password:
            refusal = self._check_login(request)
            if refusal is not None:
                return refusal
        if request.method not in SAFE_METHODS:
            if is_cross_site(request):
                return PlainTextResponse("Cross-site request blocked.", status_code=403)
            content_type = request.headers.get("content-type", "")
            if content_type and not content_type.lower().startswith(FORM_CONTENT_TYPE):
                return PlainTextResponse("Unsupported content type.", status_code=415)
            length = request.headers.get("content-length")
            if length is not None:
                if not (length.isascii() and length.isdigit()):
                    return PlainTextResponse("Bad request.", status_code=400)
                if int(length) > MAX_BODY_BYTES:
                    return PlainTextResponse("Request too large.", status_code=413)
        return None

    def _check_login(self, request: Request) -> Response | None:
        client = request.client.host if request.client else "unknown"
        wait = self.throttle.retry_after(client)
        if wait:
            return PlainTextResponse(
                "Too many failed logins. Try again later.",
                status_code=429,
                headers={"Retry-After": str(wait)},
            )
        if credentials_ok(request, self.username, self.password):
            return None
        if request.headers.get("authorization"):  # a wrong guess, not the first prompt
            self.throttle.record_failure(client)
        return PlainTextResponse(
            "Authentication required.",
            status_code=401,
            headers={"WWW-Authenticate": 'Basic realm="Torque", charset="UTF-8"'},
        )
