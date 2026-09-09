"""A bureau that is slow sometimes, down sometimes and wrong sometimes.

    python -m integrations.fake_bureau 8001

Then `./manage.py run_pipeline lending examples/lending.json --ruleset-version 2 --enrich`.
"""

import json
import random
import sys
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        reference = self.path.rsplit("/", 1)[-1]
        roll = random.random()
        if roll < 0.15:
            time.sleep(5)
        elif roll < 0.30:
            return self.reply(503, b"")
        elif roll < 0.40:
            return self.reply(200, b"<html>upstream error</html>")
        elif roll < 0.50:
            return self.reply(200, json.dumps({"reference": reference}).encode())
        score = random.randint(300, 800)
        self.reply(200, json.dumps({"reference": reference, "score": score}).encode())

    def reply(self, status, body):
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, fmt, *args):
        sys.stderr.write(f"bureau: {fmt % args}\n")


if __name__ == "__main__":
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8001
    server = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    print(f"fake bureau on http://127.0.0.1:{port}", flush=True)
    server.serve_forever()
