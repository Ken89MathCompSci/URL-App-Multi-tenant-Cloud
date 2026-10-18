import http.client
import json
import threading
import unittest

from app import make_server


class TestShortener(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = make_server(port=0, db_path=":memory:")
        cls.port = cls.server.server_address[1]
        threading.Thread(target=cls.server.serve_forever, daemon=True).start()

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()

    def request(self, method, path, body=None, raw=None, headers=None):
        conn = http.client.HTTPConnection("127.0.0.1", self.port)
        data = raw if raw is not None else (json.dumps(body) if body is not None else None)
        conn.request(method, path, body=data, headers={"Content-Type": "application/json", **(headers or {})})
        resp = conn.getresponse()
        payload = resp.read()
        conn.close()
        return resp, payload

    def shorten(self, url):
        resp, payload = self.request("POST", "/shorten", {"url": url})
        return resp.status, json.loads(payload)

    def test_shorten_then_redirect(self):
        status, body = self.shorten("https://example.com/a?b=1")
        self.assertEqual(status, 201)
        self.assertEqual(len(body["code"]), 7)
        resp, _ = self.request("GET", "/" + body["code"])
        self.assertEqual(resp.status, 302)
        self.assertEqual(resp.getheader("Location"), "https://example.com/a?b=1")

    def test_redirect_ignores_query_string_and_trailing_slash(self):
        code = self.shorten("https://example.com/page")[1]["code"]
        for path in (f"/{code}?fbclid=abc", f"/{code}/", f"/{code}/?utm_source=x"):
            with self.subTest(path=path):
                resp, _ = self.request("GET", path)
                self.assertEqual(resp.status, 302)
                self.assertEqual(resp.getheader("Location"), "https://example.com/page")

    def test_redirect_preserves_original_url_exactly(self):
        url = "https://example.com/a%20b?q=1&r=2#frag"
        code = self.shorten(url)[1]["code"]
        self.assertEqual(self.request("GET", "/" + code)[0].getheader("Location"), url)

    def test_redirect_with_non_ascii_url(self):
        code = self.shorten("https://example.com/café?q=日本")[1]["code"]
        resp, _ = self.request("GET", "/" + code)
        self.assertEqual(resp.status, 302)
        self.assertEqual(resp.getheader("Location"), "https://example.com/caf%C3%A9?q=%E6%97%A5%E6%9C%AC")

    def test_same_url_returns_same_code(self):
        s1, b1 = self.shorten("https://example.com/dupe")
        s2, b2 = self.shorten("https://example.com/dupe")
        self.assertEqual((s1, s2), (201, 200))
        self.assertEqual(b1, b2)

    def test_different_urls_get_different_codes(self):
        codes = {self.shorten(f"https://example.com/{i}")[1]["code"] for i in range(50)}
        self.assertEqual(len(codes), 50)

    def test_concurrent_requests_for_same_url_share_one_code(self):
        results = []
        threads = [threading.Thread(target=lambda: results.append(self.shorten("https://example.com/race")[1]["code"]))
                   for _ in range(20)]
        for t in threads: t.start()
        for t in threads: t.join()
        self.assertEqual(len(set(results)), 1)

    def test_bad_urls_get_a_specific_error(self):
        cases = [
            ("", "enter a URL"),
            ("   ", "enter a URL"),
            (None, "Missing"),
            (123, "must be text"),
            ("example.com", "Did you mean https://example.com?"),
            ("www.example.com/path", "Did you mean https://www.example.com/path?"),
            ("ftp://x.com", "not \"ftp://\""),
            ("javascript:alert(1)", "missing its start"),
            ("http://", "no website name"),
            ("https:///path", "no website name"),
            ("http://a b.com", "spaces"),
            ("http://example.com:abc", "port"),
            ("http://example.com:99999", "port"),
            ("https://example.com/" + "a" * 2048, "too long"),
        ]
        for bad, expected in cases:
            with self.subTest(url=bad[:40] if isinstance(bad, str) else bad):
                status, body = self.shorten(bad)
                self.assertEqual(status, 400)
                self.assertIn(expected, body["error"])

    def test_surrounding_whitespace_is_trimmed(self):
        status, body = self.shorten("  https://example.com/trim  ")
        self.assertIn(status, (200, 201))
        resp, _ = self.request("GET", "/" + body["code"])
        self.assertEqual(resp.getheader("Location"), "https://example.com/trim")

    def test_rejects_bad_bodies(self):
        self.assertEqual(self.request("POST", "/shorten", raw="not json")[0].status, 400)
        self.assertEqual(self.request("POST", "/shorten", raw="[1,2]")[0].status, 400)
        self.assertEqual(self.request("POST", "/shorten")[0].status, 400)

    def test_home_page_serves_form(self):
        resp, payload = self.request("GET", "/")
        self.assertEqual(resp.status, 200)
        self.assertIn("text/html", resp.getheader("Content-Type"))
        self.assertIn(b'id="f"', payload)

    def test_unknown_code_returns_json_error_for_api_clients(self):
        resp, payload = self.request("GET", "/nope123")
        self.assertEqual(resp.status, 404)
        self.assertIn("application/json", resp.getheader("Content-Type"))
        self.assertIn("Short link not found", json.loads(payload)["error"])

    def test_unknown_code_returns_readable_page_for_browsers(self):
        browser = {"Accept": "text/html,application/xhtml+xml,*/*;q=0.8"}
        for path in ("/nope123", "/nope123?fbclid=x", "/nope123/"):
            with self.subTest(path=path):
                resp, payload = self.request("GET", path, headers=browser)
                self.assertEqual(resp.status, 404)
                self.assertIn("text/html", resp.getheader("Content-Type"))
                self.assertIn(b"Link not found", payload)
                self.assertIn(b'href="/"', payload)

    def test_not_found_page_does_not_echo_the_requested_path(self):
        resp, payload = self.request("GET", "/%3Cscript%3Ealert(1)%3C/script%3E", headers={"Accept": "text/html"})
        self.assertEqual(resp.status, 404)
        self.assertNotIn(b"alert(1)", payload)

    def test_unknown_code_and_paths(self):
        self.assertEqual(self.request("GET", "/nope123")[0].status, 404)
        self.assertEqual(self.request("POST", "/other", {"url": "https://a.com"})[0].status, 404)


if __name__ == "__main__":
    unittest.main()
