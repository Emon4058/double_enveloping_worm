"""Globoidal worm gearset calculator.

Run:  python app.py              opens the desktop window (Tkinter)
      python app.py --web        runs the dashboard in the default browser instead
      python app.py --web [--port 8000] [--no-browser]
Uses only the Python standard library.
"""

import argparse                                  # parses the command-line switches (--web, --port, ...)
import json                                       # encodes/decodes the JSON traffic of the web API
import sys                                        # used to detect a PyInstaller bundle (sys._MEIPASS)
import threading                                  # lets the browser be opened on a timer, off the main thread
import webbrowser                                 # opens the dashboard in the user's default browser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer  # tiny built-in web server
from pathlib import Path                          # OS-independent file paths

# Pull the three public entry points of the calculation package:
#   DesignError  - raised with a list of human-readable input problems
#   DesignInput  - dataclass holding one complete set of design inputs
#   calculate    - turns a DesignInput into the result dictionary
#   format_equations - renders that result as a SolidWorks equation file
from globoid import DesignError, DesignInput, calculate, format_equations

# When packaged with PyInstaller, bundled files live under sys._MEIPASS.
# Outside a bundle that attribute does not exist, so fall back to this file's folder.
BASE_DIR = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent))
INDEX_HTML = BASE_DIR / "static" / "index.html"   # the single-page dashboard served at "/"


class Handler(BaseHTTPRequestHandler):
    """Handles the few HTTP routes the dashboard needs (one page + two POST endpoints)."""

    def _send(self, status: int, body: bytes, content_type: str) -> None:
        """Write a complete HTTP response: status line, headers, then the body bytes."""
        self.send_response(status)                                  # e.g. "HTTP/1.0 200 OK"
        self.send_header("Content-Type", content_type)              # tells the browser how to read the body
        self.send_header("Content-Length", str(len(body)))          # byte count, so the browser knows the end
        self.end_headers()                                          # blank line that closes the header block
        self.wfile.write(body)                                      # the payload itself

    def _send_json(self, status: int, payload: dict) -> None:
        """Convenience wrapper: serialise a dict and send it as application/json."""
        self._send(status, json.dumps(payload).encode(), "application/json")

    def do_GET(self):
        """GET: only the dashboard page is served; everything else is a 404."""
        if self.path in ("/", "/index.html"):
            # Read the HTML fresh on every request, so editing it needs no restart.
            self._send(200, INDEX_HTML.read_bytes(), "text/html; charset=utf-8")
        else:
            self._send(404, b"Not found", "text/plain")

    def do_POST(self):
        """POST: run a calculation and return either JSON results or an equation file."""
        # /api/equations returns the same design as a SolidWorks equation file.
        if self.path not in ("/api/calculate", "/api/equations"):
            self._send(404, b"Not found", "text/plain")
            return
        try:
            length = int(self.headers.get("Content-Length", 0))     # how many body bytes to read
            data = json.loads(self.rfile.read(length) or b"{}")     # parse the body ("{}" if empty)
            if not isinstance(data, dict):
                # A JSON array or bare value cannot describe a design.
                raise DesignError(["Request body must be a JSON object"])
            result = calculate(DesignInput.from_dict(data))         # validate the inputs, then compute
        except json.JSONDecodeError:
            # Malformed JSON: report it in the same {"errors": [...]} shape the page expects.
            self._send_json(400, {"errors": ["Request body is not valid JSON"]})
        except DesignError as exc:
            # Valid JSON but impossible inputs: hand back the list of complaints.
            self._send_json(400, {"errors": exc.errors})
        else:
            # No exception: choose the output format from the route that was called.
            if self.path == "/api/equations":
                # SolidWorks expects Windows line endings in the equation file.
                body = format_equations(result).replace("\n", "\r\n").encode("utf-8")
                self._send(200, body, "text/plain; charset=utf-8")
            else:
                self._send_json(200, result)

    def log_message(self, fmt, *args):
        """Silence the default per-request console logging (keeps the window readable)."""
        pass


def make_server(host: str, port: int) -> ThreadingHTTPServer:
    """Bind to the requested port, or to any free port if it is taken."""
    try:
        return ThreadingHTTPServer((host, port), Handler)   # preferred port
    except OSError:
        return ThreadingHTTPServer((host, 0), Handler)      # port 0 = let the OS pick a free one


def main() -> None:
    """Command-line entry point: start either the desktop window or the web dashboard."""
    # Build the argument parser; __doc__ (the module docstring above) becomes the help text.
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--web", action="store_true", help="run the dashboard in a browser instead of the desktop window")
    parser.add_argument("--host", default="127.0.0.1")         # loopback only: not reachable from the network
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--no-browser", action="store_true", help="with --web, do not open a browser")
    args = parser.parse_args()                                 # read sys.argv

    if not args.web:
        # Default mode: the Tkinter window. Imported here so the web mode never needs Tkinter.
        from gui import run as run_window
        run_window()                                           # blocks until the window is closed
        return

    # --web mode from here on.
    server = make_server(args.host, args.port)
    # server_address[1] is the port actually bound, which may differ from the requested one.
    url = f"http://{args.host}:{server.server_address[1]}/"
    print("Double-Enveloping Worm Gearset Designer", flush=True)
    print(f"Dashboard: {url}", flush=True)
    print("Keep this window open while using the dashboard. Close it (or press Ctrl+C) to quit.", flush=True)
    if not args.no_browser:
        # Half a second's delay gives the server time to accept the first request.
        threading.Timer(0.5, webbrowser.open, args=(url,)).start()
    try:
        server.serve_forever()                                 # main loop: handle requests until interrupted
    except KeyboardInterrupt:
        pass                                                   # Ctrl+C is the normal way to stop
    finally:
        server.server_close()                                  # always release the TCP port


if __name__ == "__main__":
    # Only run main() when executed as a script, not when imported as a module.
    main()
