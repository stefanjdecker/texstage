"""Spike S1 logging server: serves the probe add-in and appends every report to log.jsonl."""
import json
import sys
import time
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

HERE = Path(__file__).parent
LOG = HERE / "log.jsonl"


class Handler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(HERE / "www"), **kwargs)

    def do_POST(self):
        body = self.rfile.read(int(self.headers.get("content-length", 0)))
        try:
            entry = json.loads(body)
        except ValueError:
            entry = {"raw": body.decode("utf-8", "replace")}
        entry["recv"] = time.time()
        with LOG.open("a", encoding="utf-8") as f:
            f.write(json.dumps(entry) + "\n")
        print(entry.get("iid"), entry.get("slide"), entry.get("ev"), json.dumps(entry.get("data"))[:160], flush=True)
        self.send_response(204)
        self.end_headers()

    def log_message(self, fmt, *args):
        if self.command != "POST":
            print("HTTP", self.command, self.path, flush=True)
            with LOG.open("a", encoding="utf-8") as f:
                f.write(json.dumps({"ev": "http", "path": self.path, "recv": time.time()}) + "\n")


if __name__ == "__main__":
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8471
    ThreadingHTTPServer(("127.0.0.1", port), Handler).serve_forever()
