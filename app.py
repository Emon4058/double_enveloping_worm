"""Globoidal worm gearset calculator.

Run:  python app.py              opens the desktop window (Tkinter)
      python app.py --web        runs the dashboard in the default browser instead
      python app.py --web [--port 8000] [--no-browser]
Uses only the Python standard library.
"""

import argparse
import json
import sys
import threading
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from globoid import DesignError, DesignInput, calculate

# When packaged with PyInstaller, bundled files live under sys._MEIPASS.
BASE_DIR = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent))
INDEX_HTML = BASE_DIR / "static" / "index.html"


class Handler(BaseHTTPRequestHandler):
    def _send(self, status: int, body: bytes, content_type: str) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _send_json(self, status: int, payload: dict) -> None:
        self._send(status, json.dumps(payload).encode(), "application/json")

    def do_GET(self):
        if self.path in ("/", "/index.html"):
            self._send(200, INDEX_HTML.read_bytes(), "text/html; charset=utf-8")
        else:
            self._send(404, b"Not found", "text/plain")

    def do_POST(self):
        if self.path != "/api/calculate":
            self._send(404, b"Not found", "text/plain")
            return
        try:
            length = int(self.headers.get("Content-Length", 0))
            data = json.loads(self.rfile.read(length) or b"{}")
            if not isinstance(data, dict):
                raise DesignError(["Request body must be a JSON object"])
            result = calculate(DesignInput.from_dict(data))
        except json.JSONDecodeError:
            self._send_json(400, {"errors": ["Request body is not valid JSON"]})
        except DesignError as exc:
            self._send_json(400, {"errors": exc.errors})
        else:
            self._send_json(200, result)

    def log_message(self, fmt, *args):
        pass


def make_server(host: str, port: int) -> ThreadingHTTPServer:
    """Bind to the requested port, or to any free port if it is taken."""
    try:
        return ThreadingHTTPServer((host, port), Handler)
    except OSError:
        return ThreadingHTTPServer((host, 0), Handler)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--web", action="store_true", help="run the dashboard in a browser instead of the desktop window")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--no-browser", action="store_true", help="with --web, do not open a browser")
    args = parser.parse_args()
    if not args.web:
        from gui import run as run_window
        run_window()
        return
    server = make_server(args.host, args.port)
    url = f"http://{args.host}:{server.server_address[1]}/"
    print("Double-Enveloping Worm Gearset Designer", flush=True)
    print(f"Dashboard: {url}", flush=True)
    print("Keep this window open while using the dashboard. Close it (or press Ctrl+C) to quit.", flush=True)
    if not args.no_browser:
        threading.Timer(0.5, webbrowser.open, args=(url,)).start()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
