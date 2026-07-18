import argparse
import json
import os
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path


class Handler(BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        return

    def respond(self, key, default):
        action = self.server.scenario.get(key, {})
        if action.get("delay"):
            time.sleep(action["delay"])
        status = action.get("status", 200)
        body = action.get("body", default)
        if action.get("malformed"):
            payload = b"{"
        else:
            payload = json.dumps(body, sort_keys=True, separators=(",", ":")).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        try:
            self.wfile.write(payload)
        except BrokenPipeError:
            pass
        if action.get("die"):
            os._exit(0)

    def do_GET(self):
        if self.path == "/health":
            self.respond("health", {"status": "ok"})
        elif self.path == "/v1/models":
            self.respond("models", {"data": [{"id": self.server.scenario["served_model"]}]})
        else:
            self.respond("unknown", {"error": "not found"})

    def do_POST(self):
        length = int(self.headers.get("Content-Length", 0))
        body = json.loads(self.rfile.read(length) or b"{}")
        if self.path == "/v1/chat/completions":
            self.respond("chat", {"choices": [{"message": {"content": "chat-ok"}}]})
        elif self.path == "/v1/completions":
            key = "long_prefix" if len(body.get("prompt", "")) > 1000 else "completion"
            self.respond(key, {"choices": [{"text": "completion-ok"}]})
        else:
            self.respond("unknown", {"error": "not found"})


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--scenario", required=True, type=Path)
    parser.add_argument("--ready-file", required=True, type=Path)
    arguments = parser.parse_args()
    scenario = json.loads(arguments.scenario.read_text())
    time.sleep(scenario.get("startup_delay", 0))
    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    server.scenario = scenario
    arguments.ready_file.write_text(str(server.server_port))
    server.serve_forever()


if __name__ == "__main__":
    main()
