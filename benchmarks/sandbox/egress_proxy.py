#!/usr/bin/env python3
"""CONNECT proxy for Bash tasks: model API on 443 only, everything else 403."""
import select
import socket
import socketserver

ALLOW = {"api.anthropic.com"}


class Handler(socketserver.StreamRequestHandler):
    def handle(self):
        line = self.rfile.readline(4096).decode("latin-1").split()
        while self.rfile.readline(4096).strip():
            pass
        host, _, port = (line[1] if len(line) > 1 else "").partition(":")
        if line[:1] != ["CONNECT"] or host not in ALLOW or port != "443":
            print("DENY", " ".join(line[:2]), flush=True)
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


Server(("0.0.0.0", 3128), Handler).serve_forever()
