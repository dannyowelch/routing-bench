#!/usr/bin/env python3
"""Serve the Prometheus text file written by analyze.py --prom.

The file is the hidden-test summary (pass rate, cost per passing task).
Claude Code does not emit those series.
"""

from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

METRICS = Path("/data/metrics.prom")


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path.split("?", 1)[0] != "/metrics":
            self.send_response(404)
            self.end_headers()
            return
        if METRICS.is_file():
            body = METRICS.read_bytes()
        else:
            body = b"# benchmark summary not written yet\n"
        self.send_response(200)
        self.send_header("Content-Type", "text/plain; version=0.0.4")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, _format, *_args):
        return


if __name__ == "__main__":
    ThreadingHTTPServer(("0.0.0.0", 9100), Handler).serve_forever()
