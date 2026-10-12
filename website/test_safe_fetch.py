import socket
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from unittest import mock

from django.test import SimpleTestCase

from website import safe_fetch
from website.safe_fetch import UnsafeURL, build_safe_session, check_scheme_and_host, fetch_text, is_public_ip, public_addresses

PUBLIC_IP = "93.184.216.34"


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path == "/redirect":
            self.send_response(302)
            self.send_header("Location", f"http://127.0.0.1:{self.server.server_port}/secret")
            self.end_headers()
            return
        body = b"x" * 5000 if self.path == "/big" else b"<html>hello</html>"
        self.send_response(200)
        self.send_header("Content-Type", "text/html")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *args):
        pass


class SafeFetchTests(SimpleTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.server = HTTPServer(("127.0.0.1", 0), Handler)
        cls.port = cls.server.server_port
        threading.Thread(target=cls.server.serve_forever, daemon=True).start()

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        super().tearDownClass()

    def pretend_public(self):
        """Make good.test resolve to a public address but really connect to the local server."""
        def resolve(host, port, *args, **kwargs):
            address = PUBLIC_IP if host == "good.test" else host
            return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", (address, port))]

        def connect(address, timeout=None, **kwargs):
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(timeout)
            sock.connect(("127.0.0.1", self.port))
            return sock

        for patcher in (
            mock.patch.object(safe_fetch.socket, "getaddrinfo", side_effect=resolve),
            mock.patch.object(safe_fetch.urllib3_connection, "create_connection", side_effect=connect),
        ):
            patcher.start()
            self.addCleanup(patcher.stop)

    def test_non_public_addresses_are_rejected(self):
        for address in ("127.0.0.1", "10.0.0.5", "172.16.0.1", "192.168.1.1", "169.254.169.254",
                        "0.0.0.0", "::1", "fe80::1", "fd00::1", "::ffff:127.0.0.1", "224.0.0.1"):
            self.assertFalse(is_public_ip(address), address)
        self.assertTrue(is_public_ip(PUBLIC_IP))

    def test_only_http_and_https_urls(self):
        for url in ("file:///etc/passwd", "ftp://example.com/x", "gopher://example.com", "//example.com", "http://"):
            with self.assertRaises(UnsafeURL):
                check_scheme_and_host(url)
        check_scheme_and_host("https://example.com/feed")

    def test_hostname_resolving_to_private_address_is_rejected(self):
        with mock.patch.object(safe_fetch.socket, "getaddrinfo",
                               return_value=[(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("10.0.0.5", 80))]):
            with self.assertRaises(UnsafeURL):
                public_addresses("sneaky.example.com", 80)

    def test_one_private_answer_among_public_ones_is_rejected(self):
        infos = [(socket.AF_INET, socket.SOCK_STREAM, 6, "", (a, 80)) for a in (PUBLIC_IP, "127.0.0.1")]
        with mock.patch.object(safe_fetch.socket, "getaddrinfo", return_value=infos):
            with self.assertRaises(UnsafeURL):
                public_addresses("mixed.example.com", 80)

    def test_direct_request_to_loopback_is_blocked(self):
        session = build_safe_session(retries=0)
        for url in (f"http://127.0.0.1:{self.port}/", f"http://localhost:{self.port}/",
                    "http://169.254.169.254/latest/meta-data/", f"http://[::1]:{self.port}/"):
            with self.assertRaises(UnsafeURL, msg=url):
                fetch_text(session, url, timeout=2)

    def test_public_url_is_fetched(self):
        self.pretend_public()
        text, final_url = fetch_text(build_safe_session(retries=0), "http://good.test/page", timeout=2)
        self.assertEqual(text, "<html>hello</html>")
        self.assertEqual(final_url, "http://good.test/page")

    def test_redirect_to_internal_address_is_blocked(self):
        self.pretend_public()
        with self.assertRaises(UnsafeURL):
            fetch_text(build_safe_session(retries=0), "http://good.test/redirect", timeout=2)

    def test_response_size_is_capped(self):
        self.pretend_public()
        with self.assertRaises(UnsafeURL):
            fetch_text(build_safe_session(retries=0), "http://good.test/big", timeout=2, max_bytes=1000)
