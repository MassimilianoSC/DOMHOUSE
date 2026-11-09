"""Stand-in for the VM's metadata server and for Secret Manager, on the bench only: serves the secrets from files."""
import base64
import json
import pathlib
import re
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

FOLDER = pathlib.Path(sys.argv[1])


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def answer(self, code: int, body: bytes):
        self.send_response(code)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        match = re.fullmatch(r"/v1/projects/[^/]+/secrets/([^/]+)/versions/latest:access", self.path)
        if self.path.endswith("/service-accounts/default/token"):
            self.answer(200, json.dumps({"access_token": "banco"}).encode())
        elif self.path.endswith("/project/project-id"):
            self.answer(200, b"progetto-banco")
        elif match and (FOLDER / match[1]).exists():
            data = base64.b64encode((FOLDER / match[1]).read_bytes()).decode()
            self.answer(200, json.dumps({"payload": {"data": data}}).encode())
        else:
            self.answer(404, b"{}")


ThreadingHTTPServer(("127.0.0.1", 18090), Handler).serve_forever()
