"""Run the website locally with its two live functions, so the venue page works end to end without deploying.

    python scripts/web_sync_server.py      # refresh web/api/_unseen from server/ and scripts/live.py first
    python scripts/dev_server.py [--port 8800]

Serves web/ as static files and routes POST /api/describe and /api/notes to the same handler classes Vercel runs
(web/api/describe.py, web/api/notes.py). The Gemini key comes from the repo's .env, read by the code; it isn't sent
anywhere but Gemini. Binds to 127.0.0.1 only.
"""
import argparse
import importlib.util
import os
import sys
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WEB = ROOT / "web"

from dotenv import load_dotenv  # noqa: E402

load_dotenv(ROOT / ".env")
sys.path.insert(0, str(WEB / "api"))


def load_handler(name):
    spec = importlib.util.spec_from_file_location(f"api_{name}", WEB / "api" / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.handler


API = {"/api/describe": load_handler("describe"), "/api/notes": load_handler("notes")}


class Site(SimpleHTTPRequestHandler):
    def do_POST(self):
        handler = API.get(self.path.split("?")[0])
        if not handler:
            self.send_error(404)
            return
        # Hand this request to the function's own handler class, as Vercel does.
        handler.do_POST(self)

    def send_head(self):  # cleanUrls, as on Vercel: /listen serves listen.html
        path = self.translate_path(self.path)
        if not os.path.exists(path) and os.path.exists(path + ".html"):
            self.path = self.path.split("?")[0] + ".html"
        return super().send_head()

    def log_message(self, fmt, *args):
        if "/api/" in self.path:
            sys.stderr.write("%s %s\n" % (self.path, fmt % args))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=8800)
    args = parser.parse_args()
    server = ThreadingHTTPServer(("127.0.0.1", args.port), partial(Site, directory=str(WEB)))
    print(f"http://127.0.0.1:{args.port}/listen.html (Ctrl+C to stop)")
    server.serve_forever()


if __name__ == "__main__":
    main()
