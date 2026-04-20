"""Tiny auto-refreshing HTML viewer for live translation minutes.

Usage:
    python3 tools/minutes_viewer.py [path_to_md]  # default: newest minutes_*.md
Opens http://127.0.0.1:8765 in your browser.
"""
from __future__ import annotations

import http.server
import socketserver
import sys
import webbrowser
from pathlib import Path

PORT = 8770
ROOT = Path(__file__).resolve().parents[1]
LOGS = ROOT / "logs"


def latest_md() -> Path:
    files = sorted(LOGS.glob("minutes_*.md"), key=lambda p: p.stat().st_mtime, reverse=True)
    if not files:
        sys.exit(f"No minutes_*.md found in {LOGS}")
    return files[0]


EXPLICIT_TARGET = Path(sys.argv[1]) if len(sys.argv) > 1 else None


def current_target() -> Path:
    """Resolve the target file on each request so we always show the newest log."""
    return EXPLICIT_TARGET if EXPLICIT_TARGET is not None else latest_md()


TARGET = current_target()

HTML = """<!doctype html>
<html lang="ja"><head><meta charset="utf-8">
<title>Live Translation Minutes</title>
<style>
  :root { --bg:#0f1419; --fg:#e6edf3; --accent:#58a6ff; --muted:#8b949e; --row:#161b22; --border:#30363d; }
  * { box-sizing: border-box; }
  body { margin:0; font-family:-apple-system,BlinkMacSystemFont,"Hiragino Sans","Yu Gothic",sans-serif;
         background:var(--bg); color:var(--fg); }
  header { position:sticky; top:0; background:var(--bg); padding:16px 24px; border-bottom:1px solid var(--border);
           display:flex; justify-content:space-between; align-items:center; z-index:10; }
  h1 { margin:0; font-size:18px; color:var(--accent); }
  .meta { color:var(--muted); font-size:13px; }
  table { width:100%; border-collapse:collapse; }
  th, td { padding:12px 16px; text-align:left; vertical-align:top; border-bottom:1px solid var(--border); }
  th { background:var(--row); color:var(--muted); font-weight:500; font-size:13px;
       position:sticky; top:56px; }
  td.time { white-space:nowrap; color:var(--muted); font-variant-numeric:tabular-nums; font-size:13px; width:90px; }
  td.zh { color:#d29922; font-size:15px; }
  td.ja { color:#e6edf3; font-size:15px; line-height:1.5; }
  tr.new { animation: flash 1.2s ease; }
  @keyframes flash { from { background:#1f6feb33 } to { background:transparent } }
  .pulse { display:inline-block; width:8px; height:8px; border-radius:50%; background:#2ea043; margin-right:6px;
           animation: pulse 1.5s infinite; }
  @keyframes pulse { 0%,100% { opacity:1 } 50% { opacity:.3 } }
</style></head>
<body>
<header>
  <h1>🔴 Live Translation Minutes</h1>
  <div class="meta"><span class="pulse"></span>auto-refresh 2s · <span id="count">0</span> lines · <span id="file"></span></div>
</header>
<table>
  <thead><tr><th>時刻</th><th>中文</th><th>日本語</th></tr></thead>
  <tbody id="rows"></tbody>
</table>
<script>
let lastCount = 0;
async function tick() {
  try {
    const r = await fetch('/data', { cache: 'no-store' });
    const { rows, file } = await r.json();
    document.getElementById('file').textContent = file;
    document.getElementById('count').textContent = rows.length;
    const tbody = document.getElementById('rows');
    const existing = tbody.children.length;
    for (let i = existing; i < rows.length; i++) {
      const [t, zh, ja] = rows[i];
      const tr = document.createElement('tr');
      tr.className = 'new';
      tr.innerHTML = `<td class="time">${t}</td><td class="zh">${escape(zh)}</td><td class="ja">${escape(ja)}</td>`;
      tbody.appendChild(tr);
    }
    if (rows.length > lastCount) window.scrollTo(0, document.body.scrollHeight);
    lastCount = rows.length;
  } catch (e) { console.warn(e); }
}
function escape(s) { return s.replace(/[&<>]/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;'}[c])); }
setInterval(tick, 2000); tick();
</script>
</body></html>
"""


class Handler(http.server.BaseHTTPRequestHandler):
    def log_message(self, *a, **k):  # noqa: ARG002
        return

    def do_GET(self):  # noqa: N802
        if self.path == "/":
            self._send(200, "text/html; charset=utf-8", HTML.encode("utf-8"))
            return
        if self.path == "/data":
            target = current_target()
            rows = []
            if target.exists():
                for line in target.read_text(encoding="utf-8").splitlines():
                    if not line.startswith("|"):
                        continue
                    parts = [p.strip() for p in line.strip("|").split("|")]
                    if len(parts) >= 3 and parts[0] and parts[0] != "時刻" and not parts[0].startswith("---"):
                        rows.append(parts[:3])
            import json
            payload = json.dumps({"rows": rows, "file": target.name}, ensure_ascii=False).encode("utf-8")
            self._send(200, "application/json; charset=utf-8", payload)
            return
        self._send(404, "text/plain", b"not found")

    def _send(self, code: int, ctype: str, body: bytes) -> None:
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


if __name__ == "__main__":
    print(f"[viewer] serving {TARGET.name} on http://127.0.0.1:{PORT}")
    webbrowser.open(f"http://127.0.0.1:{PORT}")
    socketserver.TCPServer.allow_reuse_address = True
    with socketserver.TCPServer(("127.0.0.1", PORT), Handler) as httpd:
        httpd.serve_forever()
