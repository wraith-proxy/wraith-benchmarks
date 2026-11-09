#!/usr/bin/env python3
"""CONNECT proxy for Bash tasks: allowlisted hosts on 443 only, else 403.

The allowlist is env BENCH_EGRESS_ALLOW (comma-separated hosts); it defaults
to the Claude API host.
"""
import os
import select
import socket
import socketserver
import sys

DEFAULT_ALLOW = "api.anthropic.com"


def allowed(host, env=os.environ):
    hosts = env.get("BENCH_EGRESS_ALLOW") or DEFAULT_ALLOW
    return host in {h.strip() for h in hosts.split(",") if h.strip()}


class Handler(socketserver.StreamRequestHandler):
    def handle(self):
        line = self.rfile.readline(4096).decode("latin-1").split()
        while self.rfile.readline(4096).strip():
            pass
        host, _, port = (line[1] if len(line) > 1 else "").partition(":")
        if line[:1] != ["CONNECT"] or not allowed(host) or port != "443":
            print("DENY", " ".join(line[:2]), file=sys.stderr, flush=True)
            self.wfile.write(b"HTTP/1.1 403 Forbidden\r\n\r\n")
            return
        up = socket.create_connection((host, 443), timeout=30)
        self.wfile.write(b"HTTP/1.1 200 OK\r\n\r\n")
        self.wfile.flush()
        pair = [self.connection, up]
        try:
            while True:
                ready, _, _ = select.select(pair, [], [], 900)
                if not ready:
                    return
                for s in ready:
                    data = s.recv(65536)
                    if not data:
                        return
                    (up if s is self.connection else self.connection).sendall(data)
        finally:
            up.close()


class Server(socketserver.ThreadingTCPServer):
    allow_reuse_address = True
    daemon_threads = True


if __name__ == "__main__":
    Server(("0.0.0.0", 3128), Handler).serve_forever()
