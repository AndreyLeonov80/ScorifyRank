#!/usr/bin/env python3
"""Small HTTP relay for Windows Docker Desktop LAN access.

Docker Desktop on Windows can publish the app only on 127.0.0.1 while browsers
from other LAN machines need 0.0.0.0:8001. A raw TCP relay is fragile with HTTP
keep-alive, so this relay proxies every HTTP request as a short one-shot request
to the loopback-published Docker port.
"""

from __future__ import annotations

import argparse
import http.client
import http.server
import socketserver
from contextlib import suppress
from urllib.parse import urlsplit


HOP_BY_HOP_HEADERS = {
    "connection",
    "keep-alive",
    "proxy-authenticate",
    "proxy-authorization",
    "proxy-connection",
    "te",
    "trailers",
    "transfer-encoding",
    "upgrade",
}


class RelayHandler(http.server.BaseHTTPRequestHandler):
    target_host = "127.0.0.1"
    target_port = 18001
    protocol_version = "HTTP/1.1"
    server_version = "XFilesRelay/1.0"

    def log_message(self, format: str, *args: object) -> None:  # noqa: A002
        print(f"{self.client_address[0]} - {format % args}", flush=True)

    def do_GET(self) -> None:
        self._proxy()

    def do_HEAD(self) -> None:
        self._proxy()

    def do_POST(self) -> None:
        self._proxy()

    def do_PUT(self) -> None:
        self._proxy()

    def do_PATCH(self) -> None:
        self._proxy()

    def do_DELETE(self) -> None:
        self._proxy()

    def do_OPTIONS(self) -> None:
        self._proxy()

    def _proxy(self) -> None:
        body = self._read_body()
        path = self._target_path()
        headers = self._forward_headers(body)

        try:
            conn = http.client.HTTPConnection(self.target_host, self.target_port, timeout=60)
            conn.request(self.command, path, body=body, headers=headers)
            response = conn.getresponse()
            response_body = b"" if self.command == "HEAD" else response.read()
            self.send_response(response.status, response.reason)
            for key, value in response.getheaders():
                if key.lower() not in HOP_BY_HOP_HEADERS and key.lower() != "content-length":
                    self.send_header(key, value)
            self.send_header("Content-Length", str(len(response_body)))
            self.send_header("Connection", "close")
            self.end_headers()
            if response_body:
                self.wfile.write(response_body)
        except Exception as exc:  # pragma: no cover - defensive relay branch
            message = f"x-files relay upstream error: {exc}".encode("utf-8", errors="replace")
            self.send_response(502, "Bad Gateway")
            self.send_header("Content-Type", "text/plain; charset=utf-8")
            self.send_header("Content-Length", str(len(message)))
            self.send_header("Connection", "close")
            self.end_headers()
            self.wfile.write(message)
        finally:
            with suppress(Exception):
                conn.close()  # type: ignore[name-defined]
            self.close_connection = True

    def _read_body(self) -> bytes:
        length = int(self.headers.get("Content-Length") or 0)
        if length <= 0:
            return b""
        return self.rfile.read(length)

    def _target_path(self) -> str:
        parsed = urlsplit(self.path)
        path = parsed.path or "/"
        if parsed.query:
            path = f"{path}?{parsed.query}"
        return path

    def _forward_headers(self, body: bytes) -> dict[str, str]:
        headers: dict[str, str] = {}
        for key, value in self.headers.items():
            lower = key.lower()
            if lower in HOP_BY_HOP_HEADERS or lower == "host":
                continue
            headers[key] = value
        headers["Host"] = f"{self.target_host}:{self.target_port}"
        headers["Connection"] = "close"
        if body:
            headers["Content-Length"] = str(len(body))
        return headers


class ThreadingHTTPServer(socketserver.ThreadingMixIn, http.server.HTTPServer):
    allow_reuse_address = True
    daemon_threads = True


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--listen", default="0.0.0.0")
    parser.add_argument("--port", type=int, default=8001)
    parser.add_argument("--target-host", default="127.0.0.1")
    parser.add_argument("--target-port", type=int, default=18001)
    args = parser.parse_args()

    RelayHandler.target_host = args.target_host
    RelayHandler.target_port = args.target_port
    with ThreadingHTTPServer((args.listen, args.port), RelayHandler) as server:
        print(
            f"x-files HTTP relay listening on {args.listen}:{args.port} -> "
            f"{args.target_host}:{args.target_port}",
            flush=True,
        )
        server.serve_forever()


if __name__ == "__main__":
    main()
