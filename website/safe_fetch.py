"""
Fetching URLs that come from untrusted sources (RSS feed addresses, article links).

Stops the server being tricked into calling internal addresses (SSRF):
  - only http and https URLs are allowed
  - the hostname is resolved and every address must be public (no loopback, private,
    link-local, reserved or multicast ranges, which includes cloud metadata addresses)
  - the check happens on the exact address the connection is made to, so a hostname
    that changes its answer between a check and the fetch (DNS rebinding) can't get through
  - every redirect hop opens a new connection, so each hop gets the same check
  - redirects are capped, proxies from the environment are ignored
  - the response size is capped

Examples:
    from website.safe_fetch import build_safe_session, fetch_text, UnsafeURL

    session = build_safe_session(user_agent="reconnect-bot/1.0")
    content, final_url = fetch_text(session, "https://example.com/feed", timeout=10)
"""
import ipaddress
import socket
from socket import timeout as SocketTimeout
from urllib.parse import urlsplit

import requests
from requests.adapters import HTTPAdapter
from urllib3.connection import HTTPConnection, HTTPSConnection
from urllib3.connectionpool import HTTPConnectionPool, HTTPSConnectionPool
from urllib3.exceptions import ConnectTimeoutError, NameResolutionError, NewConnectionError
from urllib3.util import connection as urllib3_connection
from urllib3.util.retry import Retry

ALLOWED_SCHEMES = ("http", "https")
MAX_REDIRECTS = 5
MAX_BYTES = 5 * 1024 * 1024


class UnsafeURL(ValueError):
    """The URL points somewhere the server must not fetch from."""


def is_public_ip(address):
    """True only for addresses on the public internet."""
    ip = ipaddress.ip_address(address)
    # An IPv4 address wrapped in IPv6 (::ffff:127.0.0.1) is judged as the IPv4 address
    if getattr(ip, "ipv4_mapped", None):
        ip = ip.ipv4_mapped
    return ip.is_global and not ip.is_multicast


def check_scheme_and_host(url):
    """Reject non-http(s) URLs and URLs with no hostname. Returns the parsed URL."""
    parts = urlsplit((url or "").strip())
    if parts.scheme.lower() not in ALLOWED_SCHEMES:
        raise UnsafeURL(f"Scheme {parts.scheme!r} is not allowed")
    if not parts.hostname:
        raise UnsafeURL("URL has no hostname")
    return parts


def public_addresses(host, port):
    """Resolve a host and return its addresses, raising UnsafeURL if any isn't public."""
    infos = socket.getaddrinfo(host, port, type=socket.SOCK_STREAM)
    addresses = [info[4][0] for info in infos]
    if not addresses:
        raise UnsafeURL(f"{host} did not resolve")
    for address in addresses:
        if not is_public_ip(address.split("%")[0]):
            raise UnsafeURL(f"{host} resolves to a non-public address")
    return addresses


class SafeConnectionMixin:
    """Opens the socket itself, only to an address that passed the public check."""

    def _new_conn(self):
        try:
            addresses = public_addresses(self._dns_host, self.port)
            return urllib3_connection.create_connection(
                (addresses[0], self.port),
                self.timeout,
                source_address=self.source_address,
                socket_options=self.socket_options,
            )
        except socket.gaierror as exc:
            raise NameResolutionError(self.host, self, exc) from exc
        except SocketTimeout as exc:
            raise ConnectTimeoutError(self, f"Connection to {self.host} timed out") from exc
        except OSError as exc:
            raise NewConnectionError(self, f"Failed to establish a new connection: {exc}") from exc


class SafeHTTPConnection(SafeConnectionMixin, HTTPConnection):
    pass


class SafeHTTPSConnection(SafeConnectionMixin, HTTPSConnection):
    pass


class SafeHTTPConnectionPool(HTTPConnectionPool):
    ConnectionCls = SafeHTTPConnection


class SafeHTTPSConnectionPool(HTTPSConnectionPool):
    ConnectionCls = SafeHTTPSConnection


class SafeAdapter(HTTPAdapter):
    def init_poolmanager(self, *args, **kwargs):
        super().init_poolmanager(*args, **kwargs)
        self.poolmanager.pool_classes_by_scheme = {
            "http": SafeHTTPConnectionPool,
            "https": SafeHTTPSConnectionPool,
        }


def build_safe_session(retries=2, backoff=0.5, user_agent=None):
    """A requests session that can only reach public addresses."""
    session = requests.Session()
    session.trust_env = False
    session.max_redirects = MAX_REDIRECTS
    retry = Retry(
        total=retries, read=retries, connect=retries, backoff_factor=backoff,
        status_forcelist=(429, 500, 502, 503, 504), allowed_methods=frozenset(["GET", "HEAD"]),
    )
    adapter = SafeAdapter(max_retries=retry)
    session.mount("http://", adapter)
    session.mount("https://", adapter)
    if user_agent:
        session.headers.update({"User-Agent": user_agent})
    return session


def fetch(session, url, timeout=10.0, max_bytes=MAX_BYTES):
    """Download a URL. Returns (bytes, response). Raises UnsafeURL or requests exceptions."""
    check_scheme_and_host(url)
    try:
        response = session.get(url, timeout=timeout, allow_redirects=True, stream=True)
    except requests.exceptions.ConnectionError as exc:
        # The connection check raises UnsafeURL inside the library, find it
        reason = exc
        while reason is not None:
            if isinstance(reason, UnsafeURL):
                raise reason
            reason = reason.__cause__ or reason.__context__
        raise
    with response:
        response.raise_for_status()
        check_scheme_and_host(response.url)
        body = bytearray()
        for chunk in response.iter_content(chunk_size=16384):
            body.extend(chunk)
            if len(body) > max_bytes:
                raise UnsafeURL(f"Response is larger than {max_bytes} bytes")
        response._content = bytes(body)
        return bytes(body), response


def fetch_text(session, url, timeout=10.0, max_bytes=MAX_BYTES):
    """Like fetch, but returns (text, final_url)."""
    body, response = fetch(session, url, timeout=timeout, max_bytes=max_bytes)
    encoding = response.encoding or response.apparent_encoding or "utf-8"
    return body.decode(encoding, errors="replace"), response.url
