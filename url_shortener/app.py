"""Minimal URL shortener.

POST /shorten   {"url": "https://example.com"}  -> 201 {"code": "...", "short_url": "..."}
                                                   (200 with the same code if the URL was shortened before)
GET  /                                          -> web form for pasting a long URL
GET  /<code>                                   -> 302 redirect to the original URL
"""
import json
import os
import secrets
import sqlite3
import string
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import quote, urlparse

ALPHABET = string.ascii_letters + string.digits
CODE_LEN = 7
MAX_BODY = 8 * 1024
MAX_URL = 2048


class Store:
    def __init__(self, path=":memory:"):
        self.db = sqlite3.connect(path, check_same_thread=False)
        self.db.execute("CREATE TABLE IF NOT EXISTS links (code TEXT PRIMARY KEY, url TEXT NOT NULL)")
        self.db.execute("CREATE INDEX IF NOT EXISTS links_url ON links (url)")
        self.lock = threading.Lock()

    def add(self, url):
        """Return (code, created). Re-shortening a known URL returns its existing code."""
        with self.lock:
            row = self.db.execute("SELECT code FROM links WHERE url = ? ORDER BY rowid LIMIT 1", (url,)).fetchone()
            if row:
                return row[0], False
            while True:
                code = "".join(secrets.choice(ALPHABET) for _ in range(CODE_LEN))
                try:
                    self.db.execute("INSERT INTO links VALUES (?, ?)", (code, url))
                    self.db.commit()
                    return code, True
                except sqlite3.IntegrityError:  # code collision, try again
                    continue

    def get(self, code):
        with self.lock:
            row = self.db.execute("SELECT url FROM links WHERE code = ?", (code,)).fetchone()
        return row[0] if row else None


INDEX_HTML = b"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>URL Shortener</title>
<style>
  *, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }

  :root {
    --bg: #0f1117;
    --surface: #1a1d27;
    --surface2: #22263a;
    --border: #2e3350;
    --accent: #6c63ff;
    --accent-hover: #8880ff;
    --text: #e8eaf6;
    --muted: #8892b0;
    --error: #ff5e7d;
    --success: #43e97b;
    --radius: 12px;
    --radius-sm: 8px;
  }

  body {
    font-family: system-ui, -apple-system, sans-serif;
    background: var(--bg);
    color: var(--text);
    min-height: 100vh;
    display: flex;
    flex-direction: column;
    align-items: center;
    padding: 2rem 1rem 4rem;
  }

  .hero {
    text-align: center;
    margin-bottom: 2.5rem;
  }
  .hero h1 {
    font-size: clamp(1.8rem, 5vw, 2.8rem);
    font-weight: 800;
    background: linear-gradient(135deg, #a78bfa, #6c63ff, #38bdf8);
    -webkit-background-clip: text;
    -webkit-text-fill-color: transparent;
    background-clip: text;
    letter-spacing: -0.02em;
    margin-bottom: .5rem;
  }
  .hero p { color: var(--muted); font-size: 1rem; }

  .card {
    width: 100%;
    max-width: 600px;
    background: var(--surface);
    border: 1px solid var(--border);
    border-radius: var(--radius);
    padding: 1.75rem;
  }

  .input-row {
    display: flex;
    gap: .5rem;
  }
  .input-row input {
    flex: 1;
    background: var(--surface2);
    border: 1.5px solid var(--border);
    border-radius: var(--radius-sm);
    color: var(--text);
    font-size: .95rem;
    padding: .75rem 1rem;
    outline: none;
    transition: border-color .2s;
    min-width: 0;
  }
  .input-row input:focus { border-color: var(--accent); }
  .input-row input::placeholder { color: var(--muted); }

  .btn {
    background: var(--accent);
    color: #fff;
    border: none;
    border-radius: var(--radius-sm);
    font-size: .95rem;
    font-weight: 600;
    padding: .75rem 1.4rem;
    cursor: pointer;
    transition: background .2s, transform .1s;
    white-space: nowrap;
    flex-shrink: 0;
  }
  .btn:hover { background: var(--accent-hover); }
  .btn:active { transform: scale(.97); }
  .btn.secondary {
    background: var(--surface2);
    border: 1.5px solid var(--border);
    color: var(--text);
    font-weight: 500;
  }
  .btn.secondary:hover { border-color: var(--accent); color: var(--accent); background: var(--surface2); }
  .btn.copied { background: var(--success); color: #000; }

  #error-msg {
    color: var(--error);
    font-size: .875rem;
    margin-top: .75rem;
    min-height: 1.2em;
    display: flex;
    align-items: center;
    gap: .4rem;
  }
  #error-msg:empty { display: none; }

  #result-card {
    margin-top: 1.25rem;
    background: var(--surface2);
    border: 1.5px solid var(--accent);
    border-radius: var(--radius-sm);
    padding: 1rem 1.25rem;
    animation: slideIn .25s ease;
  }
  #result-card.hidden { display: none; }
  @keyframes slideIn {
    from { opacity: 0; transform: translateY(-8px); }
    to   { opacity: 1; transform: translateY(0); }
  }
  .result-label { font-size: .75rem; text-transform: uppercase; letter-spacing: .08em; color: var(--muted); margin-bottom: .5rem; }
  .result-row { display: flex; gap: .5rem; align-items: center; }
  .result-row input {
    flex: 1;
    background: transparent;
    border: none;
    color: var(--accent-hover);
    font-size: 1rem;
    font-weight: 600;
    padding: 0;
    outline: none;
    cursor: text;
    min-width: 0;
  }

  .section-title {
    width: 100%;
    max-width: 600px;
    display: flex;
    align-items: center;
    justify-content: space-between;
    margin: 2rem 0 .75rem;
  }
  .section-title h2 { font-size: .85rem; text-transform: uppercase; letter-spacing: .1em; color: var(--muted); font-weight: 600; }
  .section-title button { font-size: .8rem; color: var(--muted); background: none; border: none; cursor: pointer; padding: 0; }
  .section-title button:hover { color: var(--error); }

  #history {
    width: 100%;
    max-width: 600px;
    display: flex;
    flex-direction: column;
    gap: .5rem;
  }
  #history.empty { display: none; }

  .hist-item {
    background: var(--surface);
    border: 1px solid var(--border);
    border-radius: var(--radius-sm);
    padding: .75rem 1rem;
    display: flex;
    align-items: center;
    gap: .75rem;
    animation: slideIn .2s ease;
  }
  .hist-info { flex: 1; min-width: 0; }
  .hist-short { font-size: .9rem; font-weight: 600; color: var(--accent-hover); }
  .hist-long {
    font-size: .75rem;
    color: var(--muted);
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
    margin-top: .15rem;
  }
  .hist-actions { display: flex; gap: .4rem; flex-shrink: 0; }
  .hist-actions .btn { padding: .35rem .75rem; font-size: .8rem; }

  .empty-state {
    width: 100%;
    max-width: 600px;
    text-align: center;
    color: var(--muted);
    font-size: .9rem;
    padding: 2rem;
    border: 1.5px dashed var(--border);
    border-radius: var(--radius);
    display: none;
  }

  footer {
    margin-top: auto;
    padding-top: 3rem;
    color: var(--muted);
    font-size: .8rem;
    text-align: center;
  }
</style>
</head>
<body>

<div class="hero">
  <h1>URL Shortener</h1>
  <p>Paste a long URL and get a short link instantly.</p>
</div>

<div class="card">
  <form id="f" novalidate>
    <div class="input-row">
      <input id="url" type="text" inputmode="url"
             placeholder="https://example.com/very/long/link"
             autofocus aria-describedby="error-msg">
      <button class="btn" type="submit">Shorten</button>
    </div>
  </form>
  <div id="error-msg" role="alert"></div>
  <div id="result-card" class="hidden">
    <div class="result-label">Your short link</div>
    <div class="result-row">
      <input id="short" readonly aria-label="Short URL">
      <a id="visit" class="btn secondary" target="_blank" rel="noopener">Visit</a>
      <button id="copy" class="btn">Copy</button>
    </div>
  </div>
</div>

<div class="section-title" id="hist-header" style="display:none">
  <h2>Recent links</h2>
  <button id="clear-hist" title="Clear history">Clear all</button>
</div>
<div id="history"></div>

<footer>Runs on your machine &mdash; links stored locally in SQLite.</footer>

<script>
const $ = id => document.getElementById(id);
const STORAGE_KEY = "url_shortener_history";

function loadHistory() {
  try { return JSON.parse(localStorage.getItem(STORAGE_KEY)) || []; }
  catch { return []; }
}

function saveHistory(items) {
  localStorage.setItem(STORAGE_KEY, JSON.stringify(items.slice(0, 20)));
}

function renderHistory() {
  const items = loadHistory();
  const hist = $("hist-header");
  const container = $("history");
  if (!items.length) {
    hist.style.display = "none";
    container.innerHTML = "";
    return;
  }
  hist.style.display = "flex";
  container.innerHTML = items.map((item, i) => `
    <div class="hist-item" data-i="${i}">
      <div class="hist-info">
        <div class="hist-short">${escHtml(item.short_url)}</div>
        <div class="hist-long" title="${escHtml(item.url)}">${escHtml(item.url)}</div>
      </div>
      <div class="hist-actions">
        <a class="btn secondary" href="${escHtml(item.short_url)}" target="_blank" rel="noopener">Visit</a>
        <button class="btn secondary hist-copy" data-url="${escHtml(item.short_url)}">Copy</button>
      </div>
    </div>
  `).join("");

  container.querySelectorAll(".hist-copy").forEach(btn => {
    btn.addEventListener("click", async () => {
      await navigator.clipboard.writeText(btn.dataset.url);
      btn.textContent = "Copied!"; btn.classList.add("copied");
      setTimeout(() => { btn.textContent = "Copy"; btn.classList.remove("copied"); }, 1500);
    });
  });
}

function escHtml(s) {
  return s.replace(/&/g,"&amp;").replace(/</g,"&lt;").replace(/>/g,"&gt;").replace(/"/g,"&quot;");
}

$("f").addEventListener("submit", async e => {
  e.preventDefault();
  $("error-msg").textContent = "";
  $("result-card").classList.add("hidden");
  const raw = $("url").value.trim();
  try {
    const r = await fetch("/shorten", {
      method: "POST",
      headers: {"Content-Type": "application/json"},
      body: JSON.stringify({url: raw})
    });
    const data = await r.json();
    if (!r.ok) throw new Error(data.error);

    $("short").value = data.short_url;
    $("visit").href = data.short_url;
    $("result-card").classList.remove("hidden");
    $("short").select();

    const history = loadHistory().filter(h => h.short_url !== data.short_url);
    history.unshift({url: raw, short_url: data.short_url, ts: Date.now()});
    saveHistory(history);
    renderHistory();
  } catch (err) {
    $("error-msg").textContent = err instanceof TypeError
      ? "Could not reach the server. Please try again."
      : err.message;
    $("url").focus();
  }
});

$("copy").addEventListener("click", async () => {
  await navigator.clipboard.writeText($("short").value);
  $("copy").textContent = "Copied!"; $("copy").classList.add("copied");
  setTimeout(() => { $("copy").textContent = "Copy"; $("copy").classList.remove("copied"); }, 1500);
});

$("clear-hist").addEventListener("click", () => {
  localStorage.removeItem(STORAGE_KEY);
  renderHistory();
});

renderHistory();
</script>
</body>
</html>"""


NOT_FOUND_HTML = b"""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Link not found</title>
<style>
  body { font-family: system-ui, sans-serif; max-width: 36rem; margin: 4rem auto; padding: 0 1rem; }
</style></head><body>
<h1>Link not found</h1>
<p>This short link doesn't exist. It may have been mistyped or copied incompletely.
Check the link and try again, or ask the person who sent it to share it again.</p>
<p><a href="/">Create a new short link</a></p>
</body></html>"""

NOT_FOUND_MESSAGE = "Short link not found. Check that the link was copied completely."


def check_url(url):
    """Return None if url is acceptable, otherwise a message explaining what is wrong."""
    if url is None:
        return 'Missing "url" field. Send JSON like {"url": "https://example.com"}.'
    if not isinstance(url, str):
        return "The URL must be text."
    if not url:
        return "Please enter a URL."
    if len(url) > MAX_URL:
        return f"That URL is too long (maximum {MAX_URL} characters)."
    if any(c.isspace() for c in url):
        return "The URL must not contain spaces. Encode them as %20."
    p = urlparse(url)
    if not p.scheme or "://" not in url:
        return f"The URL is missing its start. Did you mean https://{url}?"
    if p.scheme not in ("http", "https"):
        return f'Only http:// and https:// links are supported, not "{p.scheme}://".'
    if not p.hostname:
        return "The URL has no website name after http(s)://, e.g. https://example.com."
    try:
        p.port
    except ValueError:
        return "The port number in the URL is not valid."
    return None


def make_handler(store):
    class Handler(BaseHTTPRequestHandler):
        def _json(self, status, body, headers=None):
            data = json.dumps(body).encode()
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(data)))
            for k, v in (headers or {}).items():
                self.send_header(k, v)
            self.end_headers()
            self.wfile.write(data)

        def _not_found(self):
            # Browsers get a readable page; API clients get JSON. The requested code is never echoed back.
            if "text/html" in self.headers.get("Accept", ""):
                self.send_response(404)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Content-Length", str(len(NOT_FOUND_HTML)))
                self.end_headers()
                return self.wfile.write(NOT_FOUND_HTML)
            self._json(404, {"error": NOT_FOUND_MESSAGE})

        def do_POST(self):
            if self.path != "/shorten":
                return self._json(404, {"error": "Not found. To create a short link, POST to /shorten."})
            try:
                length = int(self.headers.get("Content-Length", 0))
            except ValueError:
                length = -1
            if not 0 < length <= MAX_BODY:
                return self._json(400, {"error": "The request body is missing or too large."})
            try:
                url = json.loads(self.rfile.read(length)).get("url")
            except (ValueError, AttributeError):
                return self._json(400, {"error": 'The request body must be JSON like {"url": "https://example.com"}.'})
            if isinstance(url, str):
                url = url.strip()
            problem = check_url(url)
            if problem:
                return self._json(400, {"error": problem})
            code, created = store.add(url)
            host = self.headers.get("Host", "localhost")
            self._json(201 if created else 200, {"code": code, "short_url": f"http://{host}/{code}"})

        def do_GET(self):
            path = urlparse(self.path).path  # ignore ?tracking=params added when sharing
            if path == "/":
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Content-Length", str(len(INDEX_HTML)))
                self.end_headers()
                return self.wfile.write(INDEX_HTML)
            code = path.strip("/")
            url = store.get(code) if code else None
            if url is None:
                return self._not_found()
            self.send_response(302)
            # Percent-encode non-ASCII (headers are latin-1); leave existing escapes and delimiters alone.
            self.send_header("Location", quote(url, safe=":/?#[]@!$&'()*+,;=%~-._"))
            self.send_header("Content-Length", "0")
            self.end_headers()

        def log_message(self, fmt, *args):
            pass

    return Handler


def make_server(host="0.0.0.0", port=8000, db_path=None):
    if db_path is None:
        db_path = os.environ.get("DB_PATH", "links.db")
    return ThreadingHTTPServer((host, port), make_handler(Store(db_path)))


if __name__ == "__main__":
    server = make_server()
    print("Listening on http://0.0.0.0:8000")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
